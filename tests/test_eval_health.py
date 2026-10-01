import json
from pathlib import Path

import pytest

from evalarc.cli import main
from evalarc.eval_health import health
from evalarc.results_diff import load_results

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples/results-diff"


def inspect_log(path, outcomes, task="demo"):
    """outcomes: case id -> list of True/False/None (None = sample error)."""
    samples = []
    for case_id, passes in outcomes.items():
        for epoch, passed in enumerate(passes, start=1):
            sample = {"id": case_id, "epoch": epoch, "input": "q", "target": "a"}
            if passed is None:
                sample["error"] = {"message": "timeout"}
            else:
                sample["scores"] = {"match": {"value": "C" if passed else "I"}}
            samples.append(sample)
    path.write_text(
        json.dumps({"status": "success", "eval": {"task": task, "config": {}}, "samples": samples})
    )
    return load_results(path)


def ids(result):
    return {finding["id"]: finding["severity"] for finding in result["findings"]}


def test_saturated_evaluation_warns_about_headroom(tmp_path):
    run = inspect_log(tmp_path / "r.json", {f"c{i}": [True, True] for i in range(20)})
    result = health([run])
    assert ids(result) == {"saturated": "warning"}
    assert not result["healthy"]
    assert health([run], saturation=1.0)["findings"][0]["id"] == "saturated"


def test_always_failing_flaky_and_unassessed_checks(tmp_path):
    run = inspect_log(
        tmp_path / "r.json",
        {
            "never": [False, False, False],
            "flaky": [True, False, True],
            "stable": [True, True, True],
            "broken": [True, None, True],
        },
    )
    result = health([run])
    assert ids(result) == {
        "always_failing": "warning",
        "flaky_checks": "warning",
        "unassessed_attempts": "warning",
    }
    findings = {finding["id"]: finding for finding in result["findings"]}
    assert [item["case_id"] for item in findings["always_failing"]["items"]] == ["never"]
    assert [item["case_id"] for item in findings["flaky_checks"]["items"]] == ["flaky"]
    assert findings["unassessed_attempts"]["items"][0]["case_id"] == "broken"
    assert findings["unassessed_attempts"]["value"] == pytest.approx(1 / 12)


def test_always_failing_needs_every_file_to_fail(tmp_path):
    first = inspect_log(tmp_path / "a.json", {"x": [False, False], "y": [True, True]})
    second = inspect_log(tmp_path / "b.json", {"x": [True, True], "y": [True, True]})
    assert "always_failing" in ids(health([first]))
    assert "always_failing" not in ids(health([first, second]))


def test_single_attempts_are_noted(tmp_path):
    run = inspect_log(tmp_path / "r.json", {"a": [True], "b": [False], "c": [True]})
    assert ids(health([run])) == {"single_attempt": "info"}


def test_noise_versus_minimum_effect(tmp_path):
    run = inspect_log(tmp_path / "r.json", {f"c{i}": [i % 2 == 0] * 2 for i in range(20)})
    result = health([run], min_effect=0.05)
    assert result["noise"]["assessed_attempts"] == 40
    # 2 * 1.96 * sqrt(0.25 / 40) = 0.31
    assert result["noise"]["resolvable_change"] == pytest.approx(0.30990, abs=1e-4)
    assert result["noise"]["attempts_for_min_effect"] == 1537
    assert ids(result)["noise_exceeds_min_effect"] == "warning"
    assert "noise_exceeds_min_effect" not in ids(health([run], min_effect=0.5))


def test_capability_inversion_when_ordered(tmp_path):
    weaker = inspect_log(tmp_path / "w.json", {f"c{i}": [True] * 5 for i in range(10)})
    stronger = inspect_log(tmp_path / "s.json", {f"c{i}": [i < 3] * 5 for i in range(10)})
    result = health([weaker, stronger], ordered=True, saturation=1.0)
    assert result["capability_order"][0]["delta"] == pytest.approx(-0.7)
    assert result["capability_order"][0]["within_sampling_noise"] is False
    assert ids(result)["capability_inversion"] == "warning"
    assert "capability_inversion" not in ids(health([weaker, stronger], saturation=1.0))


def test_recorded_examples():
    inspect = [load_results(EXAMPLES / f"inspect/{n}.json") for n in ("baseline", "current")]
    result = health(inspect, min_effect=0.05, ordered=True)
    assert ids(result) == {"flaky_checks": "info", "noise_exceeds_min_effect": "warning"}
    assert result["noise"]["attempts_for_min_effect"] == 811
    junit = health([load_results(EXAMPLES / "junit/current.xml")])
    assert ids(junit) == {"unassessed_attempts": "warning", "single_attempt": "info"}


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"saturation": 0}, "saturation"),
        ({"min_effect": 1.5}, "min-effect"),
        ({"ordered": True}, "at least two"),
    ],
)
def test_invalid_options(tmp_path, kwargs, message):
    run = inspect_log(tmp_path / "r.json", {"a": [True]})
    with pytest.raises(ValueError, match=message):
        health([run], **kwargs)


def test_incomparable_inputs(tmp_path):
    first = inspect_log(tmp_path / "a.json", {"a": [True]}, task="one")
    second = inspect_log(tmp_path / "b.json", {"a": [True]}, task="two")
    with pytest.raises(ValueError, match="not comparable"):
        health([first, second])
    with pytest.raises(ValueError, match="different formats"):
        health([first, load_results(EXAMPLES / "junit/current.xml")])


def test_cli_writes_report_and_honours_require_healthy(tmp_path, capsys):
    output = tmp_path / "health"
    summary = tmp_path / "summary.md"
    summary.write_text("before\n")
    baseline, current = (str(EXAMPLES / f"inspect/{n}.json") for n in ("baseline", "current"))
    code = main(
        [
            "eval-health",
            baseline,
            current,
            "--ordered",
            "--min-effect",
            "0.05",
            "--output",
            str(output),
            "--markdown",
            str(summary),
        ]
    )
    assert code == 0
    printed = capsys.readouterr().out
    assert "Eval health: 1 warning(s)" in printed
    assert sorted(p.name for p in output.iterdir()) == [
        "cases.jsonl",
        "health.json",
        "index.html",
        "inputs",
        "summary.md",
    ]
    assert (output / "inputs/01.json").read_bytes() == Path(baseline).read_bytes()
    saved = json.loads((output / "health.json").read_text())
    assert saved["schema_version"] == "evalarc.eval-health.v1"
    assert saved["runs"][1]["source"]["sha256"]
    assert summary.read_text().startswith("before\n### EvalArc eval health: 1 warning(s)")
    assert "Content-Security-Policy" in (output / "index.html").read_text()
    assert main(["eval-health", current, "--min-effect", "0.05", "--require-healthy"]) == 1
    # current.json alone: refund-duplicate fails on every attempt.
    assert main(["eval-health", current, "--min-effect", "0.5", "--require-healthy"]) == 1
    assert "always_failing" in capsys.readouterr().out
    assert main(["eval-health", baseline, current, "--min-effect", "0.5", "--require-healthy"]) == 0
    assert main(["eval-health", current, "--output", str(output)]) == 2
    assert "already exists" in capsys.readouterr().err


def test_cli_json_and_bad_input(tmp_path, capsys):
    path = str(EXAMPLES / "junit/current.xml")
    assert main(["eval-health", path, "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["warnings"] == 1 and not result["healthy"]
    (tmp_path / "bad.json").write_text("[]")
    assert main(["eval-health", str(tmp_path / "bad.json")]) == 2
    assert main(["eval-health", path, "--saturation", "2"]) == 2


# --- thinking config, size and plan, per-case records ------------------------------


def _with_config(tmp_path, effort, reasoning):
    document = json.loads((EXAMPLES / "inspect/current.json").read_text())
    document["eval"]["model_generate_config"] = {"reasoning_effort": effort, "temperature": 0}
    for sample in document["samples"]:
        sample["model_usage"] = {
            "m": {"input_tokens": 100, "output_tokens": 10, "reasoning_tokens": reasoning}
        }
        sample["working_time"] = 2.0
    path = tmp_path / f"{effort}-{reasoning}.json"
    path.write_text(json.dumps(document))
    return load_results(path)


def test_requested_thinking_without_reasoning_tokens_is_flagged(tmp_path):
    report = health([_with_config(tmp_path, "high", 0)])
    finding = next(f for f in report["findings"] if f["id"] == "config_not_applied")
    assert "reasoning_effort=high" in finding["items"][0]["detail"]
    assert report["runs"][0]["generate_config"] == {"reasoning_effort": "high", "temperature": 0}
    assert "config_not_applied" not in ids(health([_with_config(tmp_path, "high", 500)]))
    assert "config_not_applied" not in ids(health([_with_config(tmp_path, "none", 0)]))


def test_size_plan_and_case_records(tmp_path, capsys):
    run = _with_config(tmp_path, "low", 10)
    report = health([run])
    assert report["size"]["cases"] == 8 and report["size"]["attempts_per_case"] == 2
    assert report["size"]["recorded_seconds_per_configuration"] == 32.0
    from evalarc.eval_health import case_lines, plan

    estimate = plan(report["size"], attempts=5, configurations=3)
    assert estimate["case_attempts"] == 120 and estimate["serial_seconds"] == 240.0
    lines = case_lines([run]).splitlines()
    assert len(lines) == 16
    first = json.loads(lines[0])
    assert first["case_id"] == "address-change" and first["verdicts"]["match"] is True
    assert first["usage"]["reasoning_tokens"] == 10
    output = tmp_path / "health"
    path = str(tmp_path / "low-10.json")
    code = main(
        [
            "eval-health",
            path,
            "--plan-attempts",
            "5",
            "--plan-configs",
            "3",
            "--output",
            str(output),
        ]
    )
    assert code == 0
    summary = (output / "summary.md").read_text()
    assert "Size: 8 cases × 2 attempt(s) × 1 configuration(s); 32.0 s recorded" in summary
    assert "Plan: 8 cases × 5 attempt(s) × 3 configuration(s) = 120 case attempts" in summary
    page = (output / "index.html").read_text()
    assert 'href="#case-0"' in page and "cases.jsonl" in page and "<details" in page
    assert len((output / "cases.jsonl").read_text().splitlines()) == 16
    assert main(["eval-health", path, "--plan-attempts", "0"]) == 2

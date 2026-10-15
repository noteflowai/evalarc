"""hillclimb-review / hillclimb-run --cases: roll back steps that break regression cases."""

import json
import shutil
from pathlib import Path

import pytest

from evalarc import provenance
from evalarc.cli import main
from evalarc.hillclimb import broken_regression_cases, render_markdown, review
from evalarc.results_diff import load_results
from tests.test_hillclimb import OFF, ON, inspect_log, split

ROOT = Path(__file__).resolve().parents[1]
RUN_EXAMPLE = ROOT / "examples/hillclimb-run"


def manifest(tmp_path, entries, name="cases.json"):
    path = tmp_path / name
    path.write_text(json.dumps({"schema_version": provenance.SCHEMA, "cases": entries}))
    return path


def regression(tmp_path, *cases):
    return provenance.load(
        manifest(
            tmp_path,
            [{"match": case, "source": "production", "suite": "regression"} for case in cases],
        )
    )


def outcomes(t1, t2, h1, h2, reg):
    return {"t1": t1, "t2": t2, "h1": h1, "h2": h2, "reg": reg}


def test_a_step_that_breaks_a_regression_case_is_rolled_back(tmp_path):
    base = inspect_log(tmp_path / "0.json", outcomes(OFF, OFF, OFF, OFF, ON))
    # Both partitions improve, so without suites the step is kept.
    step = inspect_log(tmp_path / "1.json", outcomes(ON, ON, ON, OFF, [True] * 7 + [False]))
    plain = review([base, step], split(tmp_path))
    assert plain["steps"][0]["decision"] == "keep"
    assert "suites" not in plain and "regression_suite_broken" not in plain["steps"][0]

    result = review([base, step], split(tmp_path), manifest=regression(tmp_path, "reg"))
    first = result["steps"][0]
    assert first["decision"] == "rollback_regression"
    assert first["reason"] == "1 regression-suite case(s) stopped succeeding on every trial"
    assert first["regression_suite_broken"] == [
        {"case_id": "reg", "trials": 8, "assessed": 8, "successes": 7}
    ]
    assert result["recommendation"] == "no_change_kept"
    assert result["suites"]["regression_cases"] == ["reg"]
    assert "step `1.json`: `reg` (7/8 trial(s) succeeded)" in render_markdown(result)


def test_a_preexisting_regression_failure_does_not_block_every_step(tmp_path):
    base = inspect_log(tmp_path / "0.json", outcomes(OFF, OFF, OFF, OFF, [True] + [False] * 7))
    step = inspect_log(tmp_path / "1.json", outcomes(ON, ON, ON, OFF, [False] * 8))
    result = review([base, step], split(tmp_path), manifest=regression(tmp_path, "reg"))
    assert result["steps"][0]["decision"] == "keep"
    assert result["steps"][0]["regression_suite_broken"] == []
    assert result["final"]["regression_suite_broken"] == []


def test_unassessed_and_errored_trials_count_as_broken(tmp_path):
    base = load_results(
        _write(tmp_path / "b.json", [("reg", e, "C") for e in (1, 2)] + [("t", 1, "I")])
    )
    cur = load_results(
        _write(tmp_path / "c.json", [("reg", 1, "C"), ("reg", 2, None), ("t", 1, "C")])
    )
    assert broken_regression_cases(base, cur, {"reg"}) == [
        {"case_id": "reg", "trials": 2, "assessed": 1, "successes": 1}
    ]


def _write(path, rows):
    samples = []
    for case, epoch, value in rows:
        sample = {"id": case, "epoch": epoch, "input": "q", "target": "a"}
        if value is None:
            sample["error"] = {"message": "timeout"}
        else:
            sample["scores"] = {"check": {"value": value}}
        samples.append(sample)
    path.write_text(
        json.dumps({"status": "success", "eval": {"task": "t", "config": {}}, "samples": samples})
    )
    return path


def test_final_comparison_flags_a_break_across_kept_steps(tmp_path):
    # Defense in depth: the step rule makes this unreachable today, so force a step
    # check that sees nothing and a final check that sees the loss.
    import evalarc.hillclimb as climb

    base = inspect_log(tmp_path / "0.json", outcomes(OFF, OFF, OFF, OFF, ON))
    step = inspect_log(tmp_path / "1.json", outcomes(ON, ON, ON, OFF, ON))
    original = climb.broken_regression_cases
    calls = []

    def fake(kept, candidate, cases):
        calls.append(kept["source"]["name"])
        if len(calls) == 1:  # the step check: pretend nothing broke
            return []
        return [{"case_id": "reg", "trials": 8, "assessed": 8, "successes": 7}]

    climb.broken_regression_cases = fake
    try:
        result = review([base, step], split(tmp_path), manifest=regression(tmp_path, "reg"))
    finally:
        climb.broken_regression_cases = original
    assert result["steps"][0]["decision"] == "keep"
    assert result["recommendation"] == "do_not_merge_regression_suite"
    assert result["merge_recommended"] is False


def test_manifest_without_regression_cases_is_rejected(tmp_path, capsys):
    base = inspect_log(tmp_path / "0.json", outcomes(OFF, OFF, OFF, OFF, ON))
    step = inspect_log(tmp_path / "1.json", outcomes(ON, ON, ON, OFF, ON))
    only_capability = provenance.load(
        manifest(tmp_path, [{"match": "*", "source": "production", "suite": "capability"}])
    )
    with pytest.raises(ValueError, match="no case in the regression suite"):
        review([base, step], split(tmp_path), manifest=only_capability)


def test_cli_folder_records_and_verifies_the_manifest(tmp_path, capsys):
    inspect_log(tmp_path / "0.json", outcomes(OFF, OFF, OFF, OFF, ON))
    inspect_log(tmp_path / "1.json", outcomes(ON, ON, ON, OFF, [True] * 7 + [False]))
    split(tmp_path)
    cases = manifest(tmp_path, [{"match": "reg", "source": "production", "suite": "regression"}])
    out = tmp_path / "review"
    args = ["hillclimb-review", str(tmp_path / "0.json"), str(tmp_path / "1.json")]
    args += ["--held-out", str(tmp_path / "split.json"), "--output", str(out)]
    assert main([*args, "--cases", str(cases)]) == 1
    assert "rollback_regression" in capsys.readouterr().out
    assert json.loads((out / "params.json").read_text())["cases"] == "cases.json"
    assert "<h2>Regression suite</h2>" in (out / "index.html").read_text()
    assert main(["verify", str(out), "--json"]) == 0
    capsys.readouterr()
    copied = json.loads((out / "cases.json").read_text())
    copied["cases"][0]["suite"] = "capability"
    (out / "cases.json").write_text(json.dumps(copied))
    assert main(["verify", str(out), "--json"]) == 2

    plain = tmp_path / "plain"
    assert main([*args[:-1], str(plain)]) == 0
    assert "cases" not in json.loads((plain / "params.json").read_text())
    assert "suites" not in json.loads((plain / "hillclimb.json").read_text())


def _breaking_example(target):
    """Copy of the run example whose first proposal (the refund rule) breaks t07."""
    shutil.copytree(RUN_EXAMPLE, target)
    evaluate = target / "workspace/evaluate.py"
    evaluate.write_text(
        evaluate.read_text().replace(
            "    for epoch in (1, 2):",
            '    if ticket["id"] == "t07" and "route refund" in rules:\n'
            '        route = "wrong"\n'
            "    for epoch in (1, 2):",
        )
    )
    manifest(
        target,
        [{"match": "t07", "source": "production", "suite": "regression"}],
        name="cases.manifest.json",
    )
    return target / "hillclimb.toml"


def test_hillclimb_run_rolls_back_a_step_that_breaks_a_regression_case(tmp_path, capsys):
    plain_out, suite_out = tmp_path / "plain", tmp_path / "suites"
    plain_config = _breaking_example(tmp_path / "plain-example")
    main(["hillclimb-run", str(plain_config), "--output", str(plain_out), "--trust-local"])
    plain = json.loads((plain_out / "loop.json").read_text())
    assert plain["steps"][0]["decision"] == "keep"
    assert "regression_suite_broken" not in plain["steps"][0]

    config = _breaking_example(tmp_path / "suite-example")
    config.write_text(config.read_text() + 'cases = "cases.manifest.json"\n')
    main(["hillclimb-run", str(config), "--output", str(suite_out), "--trust-local"])
    state = json.loads((suite_out / "loop.json").read_text())
    first = state["steps"][0]
    assert first["decision"] == "rollback_regression"
    assert [item["case_id"] for item in first["regression_suite_broken"]] == ["t07"]
    assert (suite_out / "cases.json").is_file()
    capsys.readouterr()
    assert main(["verify", str(suite_out), "--json"]) == 0

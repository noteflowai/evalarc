"""evalarc diff --cases: capability/regression suites and --require-regression-suite."""

import json
from pathlib import Path

import pytest

from evalarc import evidence, provenance
from evalarc.cli import main
from evalarc.results_diff import load_results, render_markdown

ROOT = Path(__file__).resolve().parents[1]
INSPECT = ROOT / "examples/results-diff/inspect"
PARAMS = {
    "format": "auto",
    "threshold": 1.0,
    "leak_min_chars": 24,
    "require_generalization": False,
    "max_cost_ratio": None,
    "cost_metric": "auto",
}


def log(path, outcomes):
    """outcomes: case -> list of True/False/None per epoch (None = sample error)."""
    samples = []
    for case, attempts in outcomes.items():
        for epoch, passed in enumerate(attempts, start=1):
            sample = {"id": case, "epoch": epoch, "input": "q", "target": "a"}
            if passed is None:
                sample["error"] = {"message": "timeout"}
            else:
                sample["scores"] = {"match": {"value": "C" if passed else "I"}}
            samples.append(sample)
    path.write_text(
        json.dumps({"status": "success", "eval": {"task": "t", "config": {}}, "samples": samples})
    )
    return path


def write_manifest(path, entries):
    path.write_text(json.dumps({"schema_version": provenance.SCHEMA, "cases": entries}))
    return path


MANIFEST = [
    {"match": "refund-*", "source": "support_ticket", "suite": "regression"},
    {"match": "cancel-*", "source": "bug_report", "suite": "capability"},
]


def test_recorded_example_suite_view(tmp_path):
    runs = [load_results(INSPECT / f"{n}.json") for n in ("baseline", "current")]
    manifest = provenance.load(write_manifest(tmp_path / "m.json", MANIFEST))
    result = evidence.compute_diff(runs, PARAMS, None, [], manifest)
    suites = result["suites"]
    assert set(suites["suites"]) == {"capability", "regression"}
    capability = {row["k"]: row for row in suites["suites"]["capability"]["current"]["by_k"]}
    assert capability[2] == {"k": 2, "cases": 2, "pass_at_k": 1.0, "pass_hat_k": 0.5}
    assert [item["case_id"] for item in suites["regression_failures"]] == ["refund-duplicate"]
    assert len(suites["undeclared_cases"]) == 3
    tags = {(row["case_id"], row.get("suite")) for row in result["changes"]}
    assert ("refund-duplicate", "regression") in tags and ("cancel-pending", "capability") in tags
    assert all(
        row.get("suite") is None for row in result["changes"] if row["case_id"] == "status-missing"
    )
    # Informational only without --require-regression-suite.
    assert "regression_suite_required" not in result
    assert evidence.diff_passed(result) is False  # checks regressed, as before
    assert "#### Suites (case-level trials)" in render_markdown(result)


def test_require_regression_suite_fails_on_a_preexisting_failure(tmp_path):
    # No check loses passes, so the default gate passes; the regression case failed before too.
    base = load_results(log(tmp_path / "b.json", {"r": [False, True], "c": [True, True]}))
    cur = load_results(log(tmp_path / "c.json", {"r": [False, True], "c": [True, True]}))
    manifest = provenance.load(
        write_manifest(
            tmp_path / "m.json",
            [
                {"match": "r", "source": "production", "suite": "regression"},
                {"match": "c", "source": "production", "suite": "capability"},
            ],
        )
    )
    informational = evidence.compute_diff([base, cur], PARAMS, None, [], manifest)
    assert informational["gate_passed"] and evidence.diff_passed(informational)
    required = evidence.compute_diff(
        [base, cur], {**PARAMS, "require_regression_suite": True}, None, [], manifest
    )
    assert required["gate_passed"] and required["regression_suite_passed"] is False
    assert evidence.diff_passed(required) is False


@pytest.mark.parametrize(
    "current,detail",
    [
        ({"c": [True]}, "not recorded in the current run"),
        ({"r": [True, None], "c": [True]}, "1/1 assessed trial(s) succeeded, 1 unassessed"),
        ({"r": [None], "c": [True]}, "0 of 1 trial(s) assessed"),
    ],
)
def test_missing_and_unassessed_regression_cases_fail_the_required_gate(tmp_path, current, detail):
    base = load_results(log(tmp_path / "b.json", {"r": [True], "c": [True]}))
    cur = load_results(log(tmp_path / "c.json", current))
    manifest = provenance.load(
        write_manifest(
            tmp_path / "m.json", [{"match": "r", "source": "production", "suite": "regression"}]
        )
    )
    result = evidence.compute_diff(
        [base, cur], {**PARAMS, "require_regression_suite": True}, None, [], manifest
    )
    assert [item["detail"] for item in result["suites"]["regression_failures"]] == [detail]
    assert result["regression_suite_passed"] is False


def test_required_regression_suite_passes_when_every_trial_succeeds(tmp_path):
    base = load_results(log(tmp_path / "b.json", {"r": [True, True], "c": [False]}))
    cur = load_results(log(tmp_path / "c.json", {"r": [True, True], "c": [True]}))
    manifest = provenance.load(
        write_manifest(
            tmp_path / "m.json", [{"match": "r", "source": "production", "suite": "regression"}]
        )
    )
    result = evidence.compute_diff(
        [base, cur], {**PARAMS, "require_regression_suite": True}, None, [], manifest
    )
    assert result["regression_suite_passed"] and evidence.diff_passed(result)


def test_option_errors(tmp_path, capsys):
    b, c = str(INSPECT / "baseline.json"), str(INSPECT / "current.json")
    assert main(["diff", b, c, "--require-regression-suite"]) == 2
    assert "requires --cases" in capsys.readouterr().err
    no_suite = write_manifest(tmp_path / "m.json", [{"match": "*", "source": "production"}])
    assert main(["diff", b, c, "--cases", str(no_suite)]) == 2
    assert "declares no suite" in capsys.readouterr().err
    runs = [load_results(INSPECT / f"{n}.json") for n in ("baseline", "current")]
    with pytest.raises(ValueError, match="require_regression_suite must be true or false"):
        evidence.compute_diff(runs, {**PARAMS, "require_regression_suite": "yes"}, None, [], None)
    with pytest.raises(ValueError, match="requires --cases"):
        evidence.compute_diff(runs, {**PARAMS, "require_regression_suite": True}, None, [], None)


def test_without_cases_output_and_params_are_unchanged(tmp_path, capsys):
    out = tmp_path / "plain"
    assert (
        main(
            [
                "diff",
                str(INSPECT / "baseline.json"),
                str(INSPECT / "current.json"),
                "--output",
                str(out),
            ]
        )
        == 1
    )
    params = json.loads((out / "params.json").read_text())
    assert "cases" not in params and "require_regression_suite" not in params
    report = json.loads((out / "diff.json").read_text())
    assert "suites" not in report and all("suite" not in row for row in report["changes"])
    assert "Suites" not in (out / "summary.md").read_text()
    assert "<h2>Suites</h2>" not in (out / "index.html").read_text()


def test_cli_folder_verifies_and_detects_tampering(tmp_path, capsys):
    manifest = write_manifest(tmp_path / "m.json", MANIFEST)
    out = tmp_path / "review"
    args = ["diff", str(INSPECT / "baseline.json"), str(INSPECT / "current.json")]
    code = main(
        [*args, "--cases", str(manifest), "--require-regression-suite", "--output", str(out)]
    )
    assert code == 1
    params = json.loads((out / "params.json").read_text())
    assert params["cases"] == "cases.json" and params["require_regression_suite"] is True
    assert "refund-duplicate" in capsys.readouterr().out
    assert "<h2>Suites</h2>" in (out / "index.html").read_text()
    assert main(["verify", str(out), "--json"]) == 0
    capsys.readouterr()

    # Moving the failing case out of the regression suite in the copy is detected.
    copied = json.loads((out / "cases.json").read_text())
    copied["cases"][0]["suite"] = "capability"
    (out / "cases.json").write_text(json.dumps(copied))
    assert main(["verify", str(out), "--json"]) == 2


def test_untrusted_case_ids_are_escaped(tmp_path):
    from evalarc.report import _esc
    from evalarc.suite_report import render_html
    from evalarc.suite_report import render_markdown as suite_markdown

    case = "<img src=x onerror=1>|\r### fake"
    base = load_results(log(tmp_path / "b.json", {case: [True]}))
    cur = load_results(log(tmp_path / "c.json", {case: [False]}))
    manifest = provenance.load(
        write_manifest(
            tmp_path / "m.json", [{"match": case, "source": "production", "suite": "regression"}]
        )
    )
    result = evidence.compute_diff([base, cur], PARAMS, None, [], manifest)
    html = render_html(result, _esc)
    assert "<img" not in html and "&lt;img" in html
    markdown = suite_markdown(result)
    assert "\r" not in markdown
    assert not any(line.lstrip("- ").startswith("### fake") for line in markdown.splitlines())
    assert "`<img src=x onerror=1>\\| ### fake`" in markdown

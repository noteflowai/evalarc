"""An unfinished baseline must fail the diff gate instead of reading as added coverage.

Inputs are synthetic edits of the recorded Inspect example (status set to 'error',
optionally with one case's samples removed).
"""

import json
from pathlib import Path

from evalarc import evidence
from evalarc.cli import main
from evalarc.results_diff import diff, load_results, render_markdown

INSPECT = Path(__file__).resolve().parents[1] / "examples/results-diff/inspect"


def unfinished(tmp_path, drop=None, name="unfinished.json"):
    document = json.loads((INSPECT / "baseline.json").read_text())
    document["status"] = "error"
    if drop:
        document["samples"] = [s for s in document["samples"] if s["id"] != drop]
    path = tmp_path / name
    path.write_text(json.dumps(document))
    return path


def rows(result):
    return sorted((r["kind"], r["case_id"], r["check"]) for r in result["changes"])


def test_unfinished_baseline_without_changes_fails_the_gate(tmp_path):
    result = diff(load_results(unfinished(tmp_path)), load_results(INSPECT / "baseline.json"))
    assert result["changes"] == []
    assert result["baseline_incomplete"] is True
    assert result["current_incomplete"] is False
    assert result["gate_passed"] is False
    markdown = render_markdown(result)
    assert "EvalArc: the baseline run is incomplete" in markdown
    assert "The baseline run did not finish (status `error`)" in markdown


def test_checks_missing_from_unfinished_baseline_do_not_pass_as_added(tmp_path):
    baseline = unfinished(tmp_path, drop="refund-duplicate")
    result = diff(load_results(baseline), load_results(INSPECT / "baseline.json"))
    assert rows(result) == [
        ("added", "refund-duplicate", "includes"),
        ("added", "refund-duplicate", "match"),
    ]
    assert result["blocking_changes"] == 0
    assert result["counts"]["added"] == 2
    assert result["gate_passed"] is False
    assert "2 check(s) appear only in the current run" in render_markdown(result)


def test_both_runs_unfinished_names_both(tmp_path):
    result = diff(
        load_results(unfinished(tmp_path)),
        load_results(unfinished(tmp_path, name="current.json")),
    )
    assert result["gate_passed"] is False
    assert "EvalArc: the baseline and current runs are incomplete" in render_markdown(result)


def test_finished_baseline_keeps_existing_result(tmp_path):
    result = diff(load_results(INSPECT / "baseline.json"), load_results(INSPECT / "current.json"))
    assert "baseline_incomplete" not in result
    assert result["blocking_changes"] == 3 and result["gate_passed"] is False
    same = diff(load_results(INSPECT / "baseline.json"), load_results(INSPECT / "baseline.json"))
    assert "baseline_incomplete" not in same and same["gate_passed"] is True
    assert "baseline run" not in render_markdown(same)


def test_cli_fails_explains_and_saves_a_verifiable_folder(tmp_path, capsys):
    baseline = unfinished(tmp_path, drop="refund-duplicate")
    output = tmp_path / "review"
    code = main(["diff", str(baseline), str(INSPECT / "baseline.json"), "--output", str(output)])
    assert code == 1
    printed = capsys.readouterr().out
    assert (
        "The baseline run is incomplete (status error); 2 check(s) appear only in the current run"
        in printed
    )
    assert "Rerun the baseline to completion" in printed
    saved = json.loads((output / "diff.json").read_text())
    assert saved["baseline_incomplete"] is True and saved["gate_passed"] is False
    html = (output / "index.html").read_text()
    assert "Gate failed" in html and "Gate passed" not in html
    assert "the baseline run is incomplete" in html.lower()
    assert "Rerun the baseline to completion and compare again" in html
    assert "EvalArc: the baseline run is incomplete" in (output / "summary.md").read_text()
    report = evidence.verify_report(output)
    assert report["verified"] is True and report["passed"] is False
    assert report["gate_passed"] is False


def test_cli_json_carries_the_new_key(tmp_path, capsys):
    code = main(["diff", str(unfinished(tmp_path)), str(INSPECT / "baseline.json"), "--json"])
    assert code == 1
    assert json.loads(capsys.readouterr().out)["baseline_incomplete"] is True

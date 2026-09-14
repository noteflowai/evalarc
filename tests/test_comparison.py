import copy
import json
from pathlib import Path

import pytest

from evalarc.cli import main
from evalarc.compare import compare
from evalarc.records import read_evaluation, validate_evaluation
from evalarc.report import render_comparison, render_evaluation


@pytest.fixture
def reports():
    path = Path(__file__).resolve().parents[1] / "examples/support-audit/audit.json"
    audit = json.loads(path.read_text())
    return {
        "reference": audit["reference"],
        **{row["name"]: row["evaluation"] for row in audit["mutants"]},
    }


def test_score_increase_does_not_hide_new_check_regression(reports):
    result = compare(reports["close-unresolved"], reports["new-key-on-retry"])
    assert result["score_delta"] > 0
    assert result["has_regressions"]
    assert result["regressions"] == [
        {"seed": 17, "case_id": "retry-after-commit", "check": "notes"}
    ]
    assert len(result["improvements"]) == 2
    assert result["current_failed_cases"] == 1


def test_no_regression_does_not_imply_resolution_and_order_is_irrelevant(reports):
    baseline = reports["duplicate-note"]
    current = copy.deepcopy(baseline)
    current["cases"].reverse()
    result = compare(baseline, current)
    assert not result["has_regressions"]
    assert not result["current"]["resolved"]
    assert result["current_failed_cases"] == 4
    assert not result["case_transitions"]


@pytest.mark.parametrize(
    "field,value",
    [("command", ["node", "agent.js"]), ("response_timeout_seconds", 99)],
)
def test_different_execution_conditions_rejected(reports, field, value):
    current = copy.deepcopy(reports["reference"])
    current["runtime"][field] = value
    with pytest.raises(ValueError, match="not comparable: runtime"):
        compare(reports["reference"], current)


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda r: r.update(score=1),
        lambda r: r.update(resolved=True),
        lambda r: r["cases"].append(copy.deepcopy(r["cases"][0])),
        lambda r: r["cases"][0]["checks"].update(notes=1),
        lambda r: r["dimensions"]["notes"].update(passed=4),
        lambda r: r["runtime"].update(response_timeout_seconds=True),
        lambda r: r["runtime"].update(response_timeout_seconds=10**500),
        lambda r: r.update(created_at=None),
    ],
)
def test_inconsistent_or_malformed_claims_rejected(reports, corrupt):
    report = reports["duplicate-note"]
    corrupt(report)
    with pytest.raises(ValueError, match="invalid evaluation"):
        validate_evaluation(report)


def test_unassessed_report_is_readable_but_cannot_be_compared(reports, tmp_path):
    report = reports["reference"]
    for case in report["cases"]:
        case.update(
            status="environment_error",
            passed=False,
            checks={name: None for name in case["checks"]},
            error="service unavailable",
        )
    for group in report["dimensions"].values():
        group.update(score=None, passed=0, assessed=0)
    report.update(score=None, valid=False, resolved=False, status="environment_error")
    validate_evaluation(report)
    with pytest.raises(ValueError, match="baseline evaluation is invalid"):
        compare(report, report)
    destination = tmp_path / "index.html"
    render_evaluation(report, destination)
    assert "UNASSESSED" in destination.read_text()
    assert "no assessed aggregate score" in destination.read_text()


@pytest.mark.parametrize("content", ['{"x":1,"x":2}', '{"x":1e999}', "[]", '{"x":NaN}'])
def test_bad_json_rejected_with_actionable_error(tmp_path, content):
    path = tmp_path / "bad.json"
    path.write_text(content)
    with pytest.raises(ValueError):
        read_evaluation(path)
    assert main(["compare", str(path), str(path), "--output", str(tmp_path / "out")]) == 2
    assert not (tmp_path / "out").exists()


def test_compare_cli_writes_portable_evidence_and_returns_regression_status(reports, tmp_path):
    baseline, current = tmp_path / "before.json", tmp_path / "after.json"
    baseline.write_text(json.dumps(reports["close-unresolved"]))
    current.write_text(json.dumps(reports["new-key-on-retry"]))
    output = tmp_path / "comparison"
    assert main(["compare", str(baseline), str(current), "--output", str(output)]) == 1
    assert json.loads((output / "baseline.json").read_text()) == reports["close-unresolved"]
    result = json.loads((output / "comparison.json").read_text())
    assert result["has_regressions"] and result["score_delta"] > 0
    assert "retry-after-commit" in (output / "index.html").read_text()
    assert "baseline.json" in (output / "index.html").read_text()


def test_html_escapes_case_evidence_and_comparison_labels(reports, tmp_path):
    script = '<script>alert("unsafe")</script>'
    report = reports["reference"]
    report["cases"][0]["case_id"] = script
    report["cases"][0]["trace"].append({"message": script})
    render_evaluation(report, tmp_path / "evaluation.html")
    comparison = compare(report, report)
    comparison["case_transitions"] = [
        {
            "case_id": script,
            "seed": 17,
            "before": script,
            "after": script,
            "regressed_checks": [script],
            "improved_checks": [],
        }
    ]
    render_comparison(comparison, tmp_path / "comparison.html")
    for path in tmp_path.glob("*.html"):
        assert "<script>" not in path.read_text()
        assert "&lt;script&gt;" in path.read_text()
        assert "Content-Security-Policy" in path.read_text()

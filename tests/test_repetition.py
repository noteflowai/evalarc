import copy
import json
from pathlib import Path

import pytest

from evalarc.audit import asset, write_candidate
from evalarc.cli import main
from evalarc.records import read_evaluation, validate_evaluation
from evalarc.repetition import repeat, summarize_attempts
from evalarc.report import render_repetition
from evalarc.runner import Runtime


@pytest.fixture
def observations():
    path = Path(__file__).resolve().parents[1] / "examples/support-audit/audit.json"
    audit = json.loads(path.read_text())
    # Synthetic repeated observations, not evidence that these distinct policies
    # actually share a candidate fingerprint.
    reports = [
        audit["reference"],
        next(row["evaluation"] for row in audit["mutants"] if row["name"] == "new-key-on-retry"),
    ]
    reports[1]["candidate_sha256"] = reports[0]["candidate_sha256"]
    return reports


def invalidate_case(report, index=0):
    case = report["cases"][index]
    case.update(status="environment_error", passed=False)
    case["checks"] = dict.fromkeys(case["checks"])
    report.update(valid=False, score=None, resolved=False, status="environment_error")
    for name, group in report["dimensions"].items():
        values = [case["checks"][name] for case in report["cases"] if name in case["checks"]]
        passed = sum(value is True for value in values)
        assessed = sum(value is not None for value in values)
        group.update(
            passed=passed, assessed=assessed, score=passed / assessed if assessed else None
        )
    validate_evaluation(report)


def test_summary_keeps_failures_and_check_variability(observations):
    summary = summarize_attempts(observations)
    assert summary["valid"] and not summary["all_attempts_resolved"]
    assert summary["status"] == "failed"
    assert summary["resolved_attempts"] == 1
    assert summary["assessed_resolution_rate"] == 0.5
    assert summary["mean_score"] == (1 + 0.9375) / 2
    assert summary["variable_checks"] == summary["variable_cases"] == 1
    case = next(row for row in summary["cases"] if row["case_id"] == "retry-after-commit")
    assert case["checks"]["notes"] == {
        "passed": 1,
        "assessed": 2,
        "pass_rate": 0.5,
        "variable": True,
    }
    assert "trace" not in json.dumps(summary)


def test_variation_is_visible_even_when_case_always_fails(observations):
    first, second = observations
    # Both fail notes; only the second fails protocol as well.
    first = copy.deepcopy(second)
    second["cases"][-1]["checks"]["protocol"] = False
    group = second["dimensions"]["protocol"]
    group.update(passed=group["passed"] - 1, score=(group["passed"] - 1) / group["assessed"])
    second["score"] = round(sum(g["score"] * g["weight"] for g in second["dimensions"].values()), 8)
    summary = summarize_attempts([first, second])
    assert summary["variable_cases"] == 0
    assert summary["variable_checks"] == 1
    assert summary["resolved_attempts"] == 0


def test_invalid_attempt_is_explicit_and_denominators_are_assessed(observations):
    invalidate_case(observations[1])
    summary = summarize_attempts(observations, requested_attempts=3)
    assert not summary["valid"] and not summary["complete"]
    assert summary["status"] == "environment_error"
    assert summary["completed_attempts"] == 2
    assert summary["assessed_attempts"] == summary["invalid_attempts"] == 1
    assert summary["mean_score"] == 1
    assert not summary["all_attempts_resolved"]
    identity = observations[1]["cases"][0]["case_id"]
    case = next(row for row in summary["cases"] if row["case_id"] == identity)
    assert case["passed"] == case["assessed"] == case["unassessed"] == 1
    assert case["pass_rate"] == 1
    assert not case["variable"]


@pytest.mark.parametrize("field", ["candidate_sha256", "grader_sha256", "cases_sha256"])
def test_mismatched_identities_rejected(observations, field):
    observations[1][field] = "a" * 64
    with pytest.raises(ValueError, match="must share"):
        summarize_attempts(observations)


def test_mismatched_runtime_and_coverage_rejected(observations):
    changed = copy.deepcopy(observations)
    changed[1]["runtime"]["case_timeout_seconds"] = 7
    with pytest.raises(ValueError, match="must share"):
        summarize_attempts(changed)
    observations[1]["cases"][0]["case_id"] = "different-case"
    with pytest.raises(ValueError, match="coverage"):
        summarize_attempts(observations)


@pytest.mark.parametrize("attempts", [True, 0, -1, 101, 1.5])
def test_bad_attempt_counts_fail_before_snapshot(tmp_path, attempts):
    with pytest.raises(ValueError, match="integer from 1 to 100"):
        repeat(tmp_path / "missing", Runtime(backend="local"), [17], attempts)


def test_repeat_freezes_candidate_and_callback_cannot_rewrite_aggregate(tmp_path):
    candidate = write_candidate(tmp_path / "candidate", asset("support_reference.py"))
    received = []
    events = []

    def save(index, result):
        received.append(copy.deepcopy(result))
        assert index == len(received)
        (candidate / "main.py").write_text("raise SystemExit(99)\n")
        # Callbacks receive evidence but cannot change repetition bookkeeping.
        result.update(valid=False, score=0, status="environment_error")
        result["cases"].clear()

    summary = repeat(
        candidate,
        Runtime(backend="local"),
        [17],
        2,
        "support-routing",
        on_event=events.append,
        on_attempt=save,
    )
    assert summary["all_attempts_resolved"]
    assert len(received) == 2 and all(report["resolved"] for report in received)
    assert len({report["candidate_sha256"] for report in received}) == 1
    assert all(case["trace"] for report in received for case in report["cases"])
    assert all(event["valid"] for event in events if event["event"] == "attempt_completed")
    assert events[0]["candidate_sha256"] == summary["candidate_sha256"]


def cli_arguments(candidate, output):
    return [
        "repeat",
        str(candidate),
        "--task",
        "support-routing",
        "--backend",
        "local",
        "--trust-local",
        "--seeds",
        "17",
        "--attempts",
        "2",
        "--output",
        str(output),
        "--progress",
    ]


def test_repeat_cli_writes_every_attempt_and_exact_progress_stream(tmp_path, capsys):
    candidate = write_candidate(tmp_path / "candidate", asset("support_reference.py"))
    output = tmp_path / "repeat"
    assert main(cli_arguments(candidate, output)) == 0
    stream = capsys.readouterr().err
    assert stream == (output / "events.jsonl").read_text()
    events = [json.loads(line) for line in stream.splitlines()]
    assert events[0]["event"] == "repetition_started"
    assert events[-1]["event"] == "repetition_completed"
    starts = [(e["attempt"], e["case_id"]) for e in events if e["event"] == "case_started"]
    ends = [(e["attempt"], e["case_id"]) for e in events if e["event"] == "case_completed"]
    assert starts == ends and len(ends) == 8
    for index in (1, 2):
        folder = output / "attempts" / f"{index:04d}"
        assert read_evaluation(folder / "evaluation.json")["resolved"]
        assert (folder / "index.html").exists()
    assert json.loads((output / "repetition.json").read_text())["all_attempts_resolved"]
    assert "attempts/0002/index.html" in (output / "index.html").read_text()


def test_missing_runtime_stops_after_first_invalid_attempt(tmp_path, capsys):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "evalarc.toml").write_text('command = ["evalarc-missing-runtime"]\n')
    output = tmp_path / "repeat"
    assert main(cli_arguments(candidate, output)) == 2
    summary = json.loads((output / "repetition.json").read_text())
    assert summary["completed_attempts"] == summary["invalid_attempts"] == 1
    assert summary["assessed_attempts"] == 0 and summary["mean_score"] is None
    assert not summary["complete"] and not summary["all_attempts_resolved"]
    assert not (output / "attempts/0002").exists()
    assert "Invalid or incomplete run" in (output / "index.html").read_text()


def test_failed_candidate_cli_returns_one_with_all_attempts(tmp_path):
    candidate = write_candidate(tmp_path / "candidate", "raise SystemExit(3)\n")
    output = tmp_path / "repeat"
    args = cli_arguments(candidate, output)
    args.remove("--progress")
    assert main(args) == 1
    summary = json.loads((output / "repetition.json").read_text())
    assert summary["complete"] and summary["valid"]
    assert summary["resolved_attempts"] == 0


def test_repetition_html_escapes_labels_and_marks_invalid_data(observations, tmp_path):
    invalidate_case(observations[1])
    result = summarize_attempts(observations, 3)
    result["cases"][0]["case_id"] = "<script>alert('x')</script>"
    path = tmp_path / "index.html"
    render_repetition(result, path)
    html = path.read_text()
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "Requested: 3. Completed: 2." in html
    assert "Invalid or incomplete run" in html
    assert "confidence interval" in html

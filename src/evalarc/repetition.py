"""Observed repeatability on fixed cases; never select only the best attempt."""

from __future__ import annotations

import copy
import statistics
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from evalarc import __version__
from evalarc.evaluate import evaluate
from evalarc.events import EventCallback, emit
from evalarc.records import validate_evaluation
from evalarc.runner import Runtime, snapshot
from evalarc.tasks import get_task


def summarize_attempts(reports: list[dict], requested_attempts: int | None = None) -> dict:
    if not isinstance(reports, list) or not reports:
        raise ValueError("at least one attempt is required")
    requested = len(reports) if requested_attempts is None else requested_attempts
    if type(requested) is not int or not len(reports) <= requested <= 100:
        raise ValueError("requested attempts must cover the recorded attempts and be at most 100")
    for report in reports:
        validate_evaluation(report)
    baseline = reports[0]
    fields = (
        "schema_version",
        "task",
        "candidate_sha256",
        "grader_sha256",
        "cases_sha256",
        "runtime",
        "seeds",
    )
    baseline_cases = {(case["seed"], case["case_id"]): case for case in baseline["cases"]}
    weights = {key: group["weight"] for key, group in baseline["dimensions"].items()}
    indexed = []
    for report in reports:
        if any(report[key] != baseline[key] for key in fields):
            raise ValueError(
                "attempts must share candidate, task, grader, cases, seeds, and runtime"
            )
        if {key: group["weight"] for key, group in report["dimensions"].items()} != weights:
            raise ValueError("attempts must use identical dimension weights")
        cases = {(case["seed"], case["case_id"]): case for case in report["cases"]}
        if cases.keys() != baseline_cases.keys() or any(
            cases[key]["checks"].keys() != baseline_cases[key]["checks"].keys() for key in cases
        ):
            raise ValueError("attempts must use identical case/check coverage")
        indexed.append(cases)
    rows = []
    for identity, case in sorted(baseline_cases.items()):
        observations = [cases[identity] for cases in indexed]
        assessed = [row for row in observations if row["status"] != "environment_error"]
        passed = sum(row["passed"] for row in assessed)
        checks = {}
        for name in case["checks"]:
            values = [row["checks"][name] for row in observations]
            checked = sum(value is not None for value in values)
            successful = sum(value is True for value in values)
            checks[name] = {
                "passed": successful,
                "assessed": checked,
                "pass_rate": successful / checked if checked else None,
                "variable": 0 < successful < checked,
            }
        rows.append(
            {
                "seed": identity[0],
                "case_id": identity[1],
                "passed": passed,
                "assessed": len(assessed),
                "failed": len(assessed) - passed,
                "unassessed": len(observations) - len(assessed),
                "pass_rate": passed / len(assessed) if assessed else None,
                "variable": 0 < passed < len(assessed),
                "checks": checks,
            }
        )
    assessed_reports = [report for report in reports if report["valid"]]
    scores = [report["score"] for report in assessed_reports]
    resolved = sum(report["resolved"] for report in assessed_reports)
    invalid = len(reports) - len(assessed_reports)
    complete = len(reports) == requested
    passed_all = complete and resolved == requested
    valid = complete and invalid == 0
    return {
        "schema_version": "evalarc.repetition.v1",
        "evalarc_version": __version__,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **{key: baseline[key] for key in fields if key != "schema_version"},
        "requested_attempts": requested,
        "completed_attempts": len(reports),
        "complete": complete,
        "valid": valid,
        "status": "passed" if passed_all else ("failed" if valid else "environment_error"),
        "all_attempts_resolved": passed_all,
        "assessed_attempts": len(assessed_reports),
        "invalid_attempts": invalid,
        "resolved_attempts": resolved,
        "assessed_resolution_rate": resolved / len(assessed_reports) if assessed_reports else None,
        "mean_score": statistics.fmean(scores) if scores else None,
        "min_score": min(scores) if scores else None,
        "max_score": max(scores) if scores else None,
        "variable_cases": sum(row["variable"] for row in rows),
        "variable_checks": sum(
            check["variable"] for row in rows for check in row["checks"].values()
        ),
        "cases": rows,
        "attempts": [
            {
                "attempt": index + 1,
                "valid": report["valid"],
                "status": report["status"],
                "score": report["score"],
                "resolved": report["resolved"],
                "created_at": report["created_at"],
            }
            for index, report in enumerate(reports)
        ],
        "interpretation": (
            "Descriptive outcomes on the same public cases. Invalid attempts are explicit; "
            "mean scores and resolution rates use assessed attempts only. "
            "No independence assumption, confidence interval, "
            "or population success rate is claimed."
        ),
    }


def repeat(
    candidate: Path,
    runtime: Runtime,
    seeds: list[int],
    attempts: int = 3,
    task_id: str = "durable-kv",
    *,
    on_event: EventCallback | None = None,
    on_attempt: Callable[[int, dict], None] | None = None,
) -> dict:
    if type(attempts) is not int or not 1 <= attempts <= 100:
        raise ValueError("attempts must be an integer from 1 to 100")
    task = get_task(task_id)
    runtime.prepare()
    reduced = []
    with tempfile.TemporaryDirectory(prefix="evalarc-repeat-") as temporary:
        frozen = Path(temporary) / "candidate"
        candidate_hash = snapshot(candidate, frozen)
        emit(
            on_event,
            "repetition_started",
            task=task.id,
            attempts=attempts,
            candidate_sha256=candidate_hash,
        )
        for index in range(1, attempts + 1):
            emit(on_event, "attempt_started", attempt=index, total_attempts=attempts)
            observer = (
                None if on_event is None else lambda event: on_event({**event, "attempt": index})
            )
            result = evaluate(frozen, runtime, seeds, task_id, on_event=observer)
            validate_evaluation(result)
            # Keep only summary inputs between attempts, not growing copies of large traces.
            compact = {key: value for key, value in result.items() if key != "cases"}
            compact["cases"] = [
                {
                    key: case[key]
                    for key in ("seed", "case_id", "checks", "status", "passed", "duration_seconds")
                }
                for case in result["cases"]
            ]
            reduced.append(copy.deepcopy(compact))
            if on_attempt is not None:
                on_attempt(index, result)
            emit(
                on_event,
                "attempt_completed",
                attempt=index,
                total_attempts=attempts,
                valid=compact["valid"],
                status=compact["status"],
                score=compact["score"],
            )
            if not compact["valid"]:
                break
    report = summarize_attempts(reduced, attempts)
    emit(
        on_event,
        "repetition_completed",
        status=report["status"],
        completed_attempts=report["completed_attempts"],
        requested_attempts=attempts,
    )
    return report

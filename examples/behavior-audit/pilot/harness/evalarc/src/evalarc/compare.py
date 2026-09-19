"""Compare matched evaluations without hiding regressions behind an average."""

from __future__ import annotations

from datetime import datetime, timezone

from evalarc.records import validate_evaluation


def compare(baseline: dict, current: dict) -> dict:
    for label, report in (("baseline", baseline), ("current", current)):
        validate_evaluation(report)
        if not report["valid"]:
            raise ValueError(f"{label} evaluation is invalid; compare only assessed runs")
    identity_fields = (
        "schema_version",
        "task",
        "grader_sha256",
        "cases_sha256",
        "runtime",
        "seeds",
    )
    mismatched = [key for key in identity_fields if baseline[key] != current[key]]
    before_weights = {name: group["weight"] for name, group in baseline["dimensions"].items()}
    after_weights = {name: group["weight"] for name, group in current["dimensions"].items()}
    if before_weights != after_weights:
        mismatched.append("dimension weights")
    before = {(case["seed"], case["case_id"]): case for case in baseline["cases"]}
    after = {(case["seed"], case["case_id"]): case for case in current["cases"]}
    if before.keys() != after.keys():
        mismatched.append("case identities")
    elif any(before[key]["checks"].keys() != after[key]["checks"].keys() for key in before):
        mismatched.append("case check coverage")
    if mismatched:
        raise ValueError(f"evaluations are not comparable: {', '.join(mismatched)}")
    regressions, improvements, transitions = [], [], []
    for identity in sorted(before):
        previous, following = before[identity], after[identity]
        regressed, improved = [], []
        for check in sorted(previous["checks"]):
            row = {"seed": identity[0], "case_id": identity[1], "check": check}
            if previous["checks"][check] and not following["checks"][check]:
                regressions.append(row)
                regressed.append(check)
            elif not previous["checks"][check] and following["checks"][check]:
                improvements.append(row)
                improved.append(check)
        if regressed or improved or previous["status"] != following["status"]:
            transitions.append(
                {
                    "seed": identity[0],
                    "case_id": identity[1],
                    "before": previous["status"],
                    "after": following["status"],
                    "regressed_checks": regressed,
                    "improved_checks": improved,
                }
            )
    summaries = {}
    for label, report in (("baseline", baseline), ("current", current)):
        summaries[label] = {
            key: report[key] for key in ("candidate_sha256", "score", "resolved", "created_at")
        }
    return {
        "schema_version": "evalarc.comparison.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "task": baseline["task"],
        "grader_sha256": baseline["grader_sha256"],
        "cases_sha256": baseline["cases_sha256"],
        "runtime": baseline["runtime"],
        "seeds": baseline["seeds"],
        **summaries,
        "score_delta": round(current["score"] - baseline["score"], 8),
        "regressions": regressions,
        "improvements": improvements,
        "case_transitions": transitions,
        "current_failed_cases": sum(not case["passed"] for case in current["cases"]),
        "has_regressions": bool(regressions),
        "interpretation": (
            "Matched observed checks only. No regression is not full task resolution. "
            "Scores and fingerprints do not authenticate a report's producer."
        ),
    }

"""Summarize caller-recorded checkpoints without confusing elapsed time with METR horizons."""

from __future__ import annotations

from evalarc.records import numeric


def summarize(checkpoints: list[dict], budget_seconds: float) -> dict:
    if not numeric(budget_seconds) or budget_seconds <= 0:
        raise ValueError("budget_seconds must be finite and positive")
    if not isinstance(checkpoints, list):
        raise ValueError("checkpoints must be an array")
    previous = 0.0
    score = 0.0
    area = 0.0
    regressions = []
    first_resolved = None
    identity = None
    for index, checkpoint in enumerate(checkpoints):
        if not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("evaluation"), dict):
            raise ValueError("each checkpoint must contain an evaluation object")
        t = checkpoint["elapsed_seconds"]
        report = checkpoint["evaluation"]
        if report.get("valid") is False or report.get("score") is None:
            raise ValueError("checkpoint must have a valid evaluated score")
        current_score = report["score"]
        if not numeric(t) or t < 0 or t > budget_seconds or (index and t <= previous):
            raise ValueError("checkpoint times must increase and stay within the budget")
        if not numeric(current_score) or not 0 <= current_score <= 1:
            raise ValueError("checkpoint scores must be finite and between zero and one")
        if type(report.get("resolved")) is not bool:
            raise ValueError("checkpoint resolution must be Boolean")
        current_identity = (
            report.get("schema_version"),
            report["task"],
            report["grader_sha256"],
            report["cases_sha256"],
            report["runtime"],
        )
        if identity is not None and current_identity != identity:
            raise ValueError("checkpoints must use the same task, grader, cases, and runtime")
        identity = current_identity
        area += (t - previous) * score
        if current_score < score:
            regressions.append({"elapsed_seconds": t, "from": score, "to": current_score})
        if report["resolved"] and first_resolved is None:
            first_resolved = t
        previous, score = t, current_score
    area += (budget_seconds - previous) * score
    return {
        "schema_version": "evalarc.trajectory.v1",
        "budget_seconds": budget_seconds,
        "normalized_score_area": area / budget_seconds,
        "final_score": score,
        "first_resolved_seconds": first_resolved,
        "regressions": regressions,
        "checkpoint_count": len(checkpoints),
        "clock_source": "caller-reported",
        "interpretation": (
            "Left-step integral; initial score is zero, last observation is held "
            "through the budget. Uses observed score, never best-so-far. "
            "This is not a human-calibrated task-completion time horizon."
        ),
    }

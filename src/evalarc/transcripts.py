"""Transcript counts and correlated errors for ``evalarc eval-health``.

Two opt-in diagnostics over saved results, both offline:

* ``--transcript-metrics`` summarizes the recorded Inspect transcripts of each file
  (assistant turns, tool calls, messages, error retries per attempt) and raises
  ``limit_reached`` for attempts stopped by a message, time, working-time or other
  non-token limit. Token limits stay with ``truncated_outputs``. An attempt that hit
  such a limit measures the budget, not the agent.
* ``--cluster-errors`` groups the error messages of unassessed attempts after removing
  numbers, hexadecimal IDs and UUIDs, and raises ``correlated_errors`` when one message
  spans several cases. Trials that failed for the same infrastructure reason are not
  independent, so counting them as separate agent outcomes distorts pass^k, noise
  estimates and triage; rerun them instead.
"""

from __future__ import annotations

import re

MIN_CLUSTER_CASES = 3
_VOLATILE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"  # UUIDs
    r"|0x[0-9a-f]+|\b[0-9a-f]{12,}\b"  # hexadecimal identifiers
    r"|\b(?=[a-z_-]*\d)[a-z0-9_-]{8,}\b"  # request IDs and tokens mixing letters and digits
    r"|\d+(?:\.\d+)?",  # numbers, ports, durations, timestamps
    re.IGNORECASE,
)
METRICS = ("n_turns", "n_tool_calls", "n_messages", "n_error_retries")


def summarize_transcripts(run: dict) -> dict:
    """Per-file transcript counts; attempts without recorded messages stay unknown."""
    attempts = recorded = 0
    totals = {name: 0 for name in METRICS}
    reported = {name: 0 for name in METRICS}
    for metas in (run.get("samples") or {}).values():
        for meta in metas:
            attempts += 1
            counts = meta.get("transcript")
            if counts is None:
                continue
            recorded += 1
            for name in METRICS:
                if name in counts:
                    totals[name] += counts[name]
                    reported[name] += 1
    return {
        "file": run["source"]["name"],
        "attempts": attempts,
        "attempts_with_transcript": recorded,
        "mean": {
            name: round(totals[name] / reported[name], 6) if reported[name] else None
            for name in METRICS
        },
        "max": {
            name: max(
                (
                    meta["transcript"][name]
                    for metas in (run.get("samples") or {}).values()
                    for meta in metas
                    if name in (meta.get("transcript") or {})
                ),
                default=None,
            )
            for name in METRICS
        },
    }


def limit_items(runs: list[dict]) -> list[dict]:
    """Attempts stopped by a recorded non-token limit, one row per file and case."""
    items = []
    for run in runs:
        for case_id, metas in sorted((run.get("samples") or {}).items()):
            kinds = [meta.get("limit") for meta in metas]
            hit = [kind for kind in kinds if kind and kind != "token"]
            if hit:
                items.append(
                    {
                        "file": run["source"]["name"],
                        "case_id": case_id,
                        "check": "(limit)",
                        "passed": 0,
                        "assessed": len(hit),
                        "attempts": len(metas),
                        "detail": f"{len(hit)}/{len(metas)} attempt(s) stopped by a "
                        f"{', '.join(sorted(set(hit)))} limit",
                    }
                )
    return items


def normalize_error(text: str) -> str:
    return " ".join(_VOLATILE.sub("#", text).split())[:200]


def error_clusters(run: dict) -> list[dict]:
    """Unassessed attempts grouped by normalized error message, largest first."""
    clusters: dict[str, dict] = {}
    for case_id, checks in run["cases"].items():
        for check, attempts in checks.items():
            for attempt in attempts:
                if attempt["passed"] is not None or not attempt.get("evidence"):
                    continue
                key = normalize_error(str(attempt["evidence"]))
                entry = clusters.setdefault(key, {"message": key, "cases": set(), "attempts": 0})
                entry["cases"].add(case_id)
                entry["attempts"] += 1
    rows = [
        {
            "message": entry["message"],
            "cases": sorted(entry["cases"]),
            "attempts": entry["attempts"],
        }
        for entry in clusters.values()
    ]
    return sorted(rows, key=lambda row: (-len(row["cases"]), -row["attempts"], row["message"]))


def correlated_items(runs: list[dict], min_cases: int = MIN_CLUSTER_CASES) -> list[dict]:
    items = []
    for run in runs:
        for cluster in error_clusters(run):
            if len(cluster["cases"]) >= min_cases:
                items.append(
                    {
                        "file": run["source"]["name"],
                        "case_id": f"{len(cluster['cases'])} cases",
                        "check": "(error)",
                        "passed": 0,
                        "assessed": 0,
                        "attempts": cluster["attempts"],
                        "detail": f"{cluster['attempts']} attempt(s) in "
                        f"{', '.join(cluster['cases'][:5])}"
                        + (" …" if len(cluster["cases"]) > 5 else "")
                        + f": {cluster['message']}",
                        "cases": cluster["cases"],
                        "message": cluster["message"],
                    }
                )
    return items

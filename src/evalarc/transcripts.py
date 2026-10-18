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
# Status and exit codes identify the failure, so they are kept: "code 137" and "code 1"
# are different errors, and so are HTTP 429 and 500.
_CODES = re.compile(
    r"\b(?i:code|status|errno|exit|http|error)\s*[:=]?\s*\d{1,4}\b"
    # A bare 3-digit status needs a capitalized reason phrase ("429 Too Many Requests").
    r"|\b[1-5]\d\d\b(?=\s+[A-Z][a-z])",
)
MAX_ERROR_CHARS = 4_000
_VOLATILE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"  # UUIDs
    r"|0x[0-9a-f]+|\b[0-9a-f]{12,}\b"  # hexadecimal identifiers
    r"|\b(?=[a-z_-]{0,64}\d)[a-z0-9_-]{8,}\b"  # request IDs, tokens, model names with digits
    r"|\d+(?:\.\d+)?(?:\s*(?:ms|s|sec|seconds|m|min|minutes)\b)?"  # numbers, durations
    r"|\d+(?:\.\d+)?",  # remaining numbers, ports, timestamps
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
            # Token limits and other cut-off outputs are already truncated_outputs.
            hit = [
                meta["limit"]
                for meta in metas
                if meta.get("limit") and meta["limit"] != "token" and not meta.get("truncated")
            ]
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
    """Error text with volatile parts replaced by ``#``; status and exit codes are kept.

    Input is cut at ``MAX_ERROR_CHARS`` so the patterns stay fast on any recorded text.
    """
    text = text[:MAX_ERROR_CHARS]
    kept: list[str] = []

    def protect(match: re.Match) -> str:
        kept.append(match.group(0))
        # Letters only, so the placeholder survives the number replacement below.
        index, label = len(kept) - 1, ""
        while True:
            index, rest = divmod(index, 26)
            label = chr(ord("a") + rest) + label
            if not index:
                break
        return f"\x00{label}\x00"

    def restore(match: re.Match) -> str:
        index = 0
        for char in match.group(1):
            index = index * 26 + ord(char) - ord("a")
        return kept[index]

    text = _VOLATILE.sub("#", _CODES.sub(protect, text))
    text = re.sub("\x00([a-z]+)\x00", restore, text)
    return " ".join(text.split())


def error_clusters(run: dict) -> list[dict]:
    """Unassessed attempts grouped by normalized error message, largest first."""
    clusters: dict[str, dict] = {}
    for case_id, checks in run["cases"].items():
        for check, attempts in checks.items():
            for attempt in attempts:
                evidence = attempt.get("evidence")
                if attempt["passed"] is not None or not evidence:
                    continue
                if str(evidence).startswith("skipped"):
                    # A skip is a declared decision (e.g. "requires GPU"), not a failure.
                    continue
                key = normalize_error(str(evidence))
                entry = clusters.setdefault(
                    key, {"message": key[:200], "cases": set(), "attempts": 0}
                )
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

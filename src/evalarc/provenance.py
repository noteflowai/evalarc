"""Declared case provenance for ``evalarc eval-health --cases``.

Saved results do not say where a case came from. A small manifest declares each case's
source and, for hard cases, why it is hard. EvalArc then checks the distribution against
the order of preference for eval inputs: production sessions, then bug reports and
support tickets, then a handful of hand-written cases, then synthetic cases; and flags
cases selected because one model failed them without a stated reason for the
difficulty (adversarial sampling measures that model's weak spots, not the task).
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
from pathlib import Path

SCHEMA = "evalarc.case-manifest.v1"
MAX_BYTES = 4 * 1024 * 1024
SOURCES = (
    "production",
    "bug_report",
    "support_ticket",
    "user_traffic",
    "manual",
    "synthetic",
    "model_failure",
)
REAL = {"production", "bug_report", "support_ticket", "user_traffic"}
SCOPE = (
    "Provenance is declared by the caller and not verified. It records where cases came "
    "from, not whether they represent production traffic or whether the data was "
    "reviewed for retention and sensitive content."
)


def load(path: Path) -> dict:
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError(f"{path.name} exceeds {MAX_BYTES} bytes")
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{path.name} is not JSON: {error}") from None
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA:
        raise ValueError(f"case manifest schema_version must be {SCHEMA!r}")
    entries = document.get("cases")
    if not isinstance(entries, list) or not entries:
        raise ValueError("case manifest needs a non-empty cases list")
    rules = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("match"), str):
            raise ValueError(f"cases[{index}] needs a match string (case ID or glob)")
        source = entry.get("source")
        if source not in SOURCES:
            raise ValueError(f"cases[{index}].source must be one of {', '.join(SOURCES)}")
        difficulty = entry.get("difficulty")
        if difficulty is not None and (not isinstance(difficulty, str) or not difficulty.strip()):
            raise ValueError(f"cases[{index}].difficulty must be a non-empty string")
        unknown = set(entry) - {"match", "source", "difficulty", "note"}
        if unknown:
            raise ValueError(f"cases[{index}] has unknown fields: {', '.join(sorted(unknown))}")
        rules.append({"match": entry["match"], "source": source, "difficulty": difficulty})
    return {
        "source": {"name": path.name, "sha256": hashlib.sha256(raw).hexdigest()},
        "rules": rules,
    }


def review(manifest: dict, case_ids: set[str]) -> dict:
    """Assign each case its first matching rule; every rule must match a case."""
    assigned: dict[str, dict] = {}
    for rule in manifest["rules"]:
        pattern = rule["match"]
        matched = (
            {case for case in case_ids if fnmatch.fnmatchcase(case, pattern)}
            if any(ch in pattern for ch in "*?[")
            else {pattern} & case_ids
        )
        if not matched:
            raise ValueError(f"case manifest entry {pattern!r} matches no recorded case")
        for case in matched:
            assigned.setdefault(case, rule)
    counts = {source: 0 for source in SOURCES}
    for rule in assigned.values():
        counts[rule["source"]] += 1
    undeclared = sorted(case_ids - set(assigned))
    unexplained = sorted(
        case
        for case, rule in assigned.items()
        if rule["source"] == "model_failure" and not rule["difficulty"]
    )
    return {
        "manifest": manifest["source"],
        "counts": {key: value for key, value in counts.items() if value},
        "declared": len(assigned),
        "undeclared": undeclared,
        "real": sum(counts[source] for source in REAL),
        "unexplained_model_failures": unexplained,
        "scope": SCOPE,
    }


def findings(result: dict, total: int, finding) -> list[dict]:
    """Translate a provenance review into eval-health findings."""
    out = []
    counts = result["counts"]
    if result["undeclared"]:
        out.append(
            finding(
                "provenance_undeclared",
                "info",
                f"{len(result['undeclared'])} of {total} case(s) have no declared source.",
                value=len(result["undeclared"]) / total,
            )
        )
    if result["declared"] and not result["real"]:
        out.append(
            finding(
                "no_real_cases",
                "warning",
                "No case comes from production sessions, bug reports, support tickets or "
                "user traffic. Start from real failures and requests where you can.",
            )
        )
    synthetic = counts.get("synthetic", 0)
    if result["declared"] and synthetic / result["declared"] > 0.5:
        out.append(
            finding(
                "mostly_synthetic",
                "warning",
                f"{synthetic} of {result['declared']} declared case(s) are synthetic. Ground "
                "synthetic cases in a few real examples and check they match real use.",
                value=synthetic / result["declared"],
            )
        )
    if result["unexplained_model_failures"]:
        out.append(
            finding(
                "adversarial_sampling",
                "warning",
                f"{len(result['unexplained_model_failures'])} case(s) were chosen because a "
                "model failed them, with no stated reason for the difficulty. Such a set "
                "measures that model's weak spots rather than the task; state why each case "
                "is hard, or replace it.",
                items=[
                    {
                        "case_id": case,
                        "check": "(case)",
                        "passed": 0,
                        "assessed": 0,
                        "attempts": 0,
                        "detail": "model_failure without difficulty",
                    }
                    for case in result["unexplained_model_failures"]
                ],
            )
        )
    traffic = counts.get("user_traffic", 0)
    if result["declared"] and traffic == result["declared"]:
        out.append(
            finding(
                "traffic_only",
                "info",
                "Every case comes from user traffic. Users mostly send requests they expect "
                "to work, so add bug reports or deliberately hard cases.",
            )
        )
    return out

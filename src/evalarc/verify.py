"""Verify saved evidence without executing candidates or contacting a runtime."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evalarc.compare import compare
from evalarc.records import read_json, validate_evaluation
from evalarc.repetition import summarize_attempts

MAX_BUNDLE_BYTES = 256 * 1024 * 1024
REPORTS = ("evaluation.json", "repetition.json", "comparison.json")
SCOPE = (
    "Consistency of recorded checks, summaries and identities only. "
    "No candidate execution, grader rerun, producer authentication or HTML verification."
)


def same_summary(recorded: dict, computed: dict) -> bool:
    """Ignore generation metadata only; keep booleans distinct from numbers."""
    ignored = {"created_at", "evalarc_version"}
    return json.dumps(
        {key: value for key, value in recorded.items() if key not in ignored},
        sort_keys=True,
        allow_nan=False,
    ) == json.dumps(
        {key: value for key, value in computed.items() if key not in ignored},
        sort_keys=True,
        allow_nan=False,
    )


def verify(path: Path) -> dict:
    """Verify evaluation, repetition or comparison JSON and its required inputs."""
    path = path.absolute()
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError("choose an evidence path without symlinks")
    if path.is_dir():
        choices = [path / name for name in REPORTS if (path / name).exists()]
        if len(choices) != 1 or (path / "suite.json").exists():
            raise ValueError(
                "choose one evaluation, repetition or comparison report; "
                "for a suite, verify each jobs/<id> repetition directory"
            )
        path = choices[0]
    root = path.parent
    files: dict[str, dict] = {}
    total = 0

    def read(source: Path) -> dict:
        nonlocal total
        if any(item.is_symlink() for item in (source, *source.parents)):
            raise ValueError("evidence contains a symlink")
        document, raw = read_json(source, limit=min(64 * 1024 * 1024, MAX_BUNDLE_BYTES - total))
        total += len(raw)
        files[source.relative_to(root).as_posix()] = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        }
        return document

    def evaluation(source: Path) -> dict:
        document = read(source)
        validate_evaluation(document)
        return document

    recorded = read(path)
    schema = recorded.get("schema_version")
    regressions = None
    if schema == "evalarc.evaluation.v2":
        validate_evaluation(recorded)
        kind = "evaluation"
        valid, resolved = recorded["valid"], recorded["resolved"]
    elif schema == "evalarc.repetition.v1":
        kind = "repetition"
        requested, completed = (
            recorded.get("requested_attempts"),
            recorded.get("completed_attempts"),
        )
        if (
            type(requested) is not int
            or type(completed) is not int
            or not 1 <= completed <= requested <= 100
        ):
            raise ValueError("repetition must contain 1–100 completed/requested attempts")
        directory = root / "attempts"
        if directory.is_symlink():
            raise ValueError("attempts directory must not be a symlink")
        expected = {f"{index:04d}" for index in range(1, completed + 1)}
        # Bound enumeration too; extra files or directories cannot hide attempts.
        found = set()
        for child in directory.iterdir():
            found.add(child.name)
            if len(found) > 100:
                raise ValueError("too many attempt entries")
        if found != expected:
            raise ValueError("attempt inventory differs from completed_attempts")
        reports = [evaluation(directory / name / "evaluation.json") for name in sorted(expected)]
        computed = summarize_attempts(reports, requested)
        if not same_summary(recorded, computed):
            raise ValueError("repetition summary differs from its attempt evaluations")
        valid, resolved = computed["valid"], computed["all_attempts_resolved"]
    elif schema == "evalarc.comparison.v1":
        kind = "comparison"
        baseline, current = evaluation(root / "baseline.json"), evaluation(root / "current.json")
        computed = compare(baseline, current)
        if not same_summary(recorded, computed):
            raise ValueError("comparison summary differs from its input evaluations")
        valid, resolved = current["valid"], current["resolved"]
        regressions = computed["has_regressions"]
    else:
        raise ValueError(
            "unsupported evidence schema; expected evaluation, repetition or comparison"
        )
    result = {
        "schema_version": "evalarc.verification.v1",
        "verified": True,
        "kind": kind,
        "records_valid": valid,
        "fully_resolved": resolved,
        "files": files,
        "scope": SCOPE,
    }
    if regressions is not None:
        result["has_regressions"] = regressions
    return result

"""Behavioral negative controls, not an exhaustive mutation-testing engine."""

from __future__ import annotations

import tempfile
from importlib.resources import files
from pathlib import Path

from evalarc.evaluate import evaluate
from evalarc.runner import Runtime
from evalarc.tasks import get_task

MUTANTS = {
    "ack-without-work": ("ACK_ONLY = False", "ACK_ONLY = True", "basic"),
    "memory-only": ("DURABLE = True", "DURABLE = False", "persistence"),
    "partial-batch": ("ATOMIC_BATCH = True", "ATOMIC_BATCH = False", "transactions"),
    "cas-always-wins": ("ENFORCE_CAS = True", "ENFORCE_CAS = False", "compare_swap"),
    "boolean-equals-one": ("TYPE_SENSITIVE = True", "TYPE_SENSITIVE = False", "compare_swap"),
    "delete-noop": ("DELETE_ENABLED = True", "DELETE_ENABLED = False", "basic"),
    "accept-nonstring-keys": ("VALIDATE_KEYS = True", "VALIDATE_KEYS = False", "validation"),
    "commit-on-exit": ("COMMIT_BEFORE_ACK = True", "COMMIT_BEFORE_ACK = False", "crash_recovery"),
}

SUPPORT_MUTANTS = {
    "claim-without-actions": ("ACK_ONLY = False", "ACK_ONLY = True", "routing"),
    "wrong-ticket": ("WRONG_TICKET = False", "WRONG_TICKET = True", "scope"),
    "wrong-queue": ("WRONG_QUEUE = False", "WRONG_QUEUE = True", "routing"),
    "duplicate-note": ("DUPLICATE_NOTE = False", "DUPLICATE_NOTE = True", "notes"),
    "close-unresolved": ("CLOSE_OPEN = False", "CLOSE_OPEN = True", "closure"),
    "skip-retry": ("SKIP_RETRY = False", "SKIP_RETRY = True", "notes"),
    "new-key-on-retry": ("NEW_RETRY_KEY = False", "NEW_RETRY_KEY = True", "notes"),
}

CONTROL_PACKS = {"durable-kv": MUTANTS, "support-routing": SUPPORT_MUTANTS}


def asset(name: str) -> str:
    return files("evalarc").joinpath("assets", name).read_text()


def write_candidate(path: Path, source: str) -> Path:
    path.mkdir(parents=True)
    (path / "main.py").write_text(source)
    return path


def mutate(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"mutation anchor must appear exactly once: {old}")
    return source.replace(old, new)


def audit(runtime: Runtime, seeds: list[int], task_id: str = "durable-kv") -> dict:
    task = get_task(task_id)
    source = asset(task.reference_asset)
    controls = CONTROL_PACKS[task_id]
    rows = []
    with tempfile.TemporaryDirectory(prefix="evalarc-audit-") as directory:
        root = Path(directory)
        reference = evaluate(write_candidate(root / "reference", source), runtime, seeds, task_id)
        for name, (old, new, target) in controls.items():
            candidate = write_candidate(root / name, mutate(source, old, new))
            result = evaluate(candidate, runtime, seeds, task_id)
            failures = [c["case_id"] for c in result["cases"] if c["checks"].get(target) is False]
            rows.append(
                {
                    "name": name,
                    "target_dimension": target,
                    "killed": result["valid"] and bool(failures),
                    "valid": result["valid"],
                    "score": result["score"],
                    "failing_cases": sorted(set(failures)),
                    "candidate_sha256": result["candidate_sha256"],
                    "evaluation": result,
                }
            )
    killed = sum(row["killed"] for row in rows)
    valid = reference["valid"] and all(row["valid"] for row in rows)
    return {
        "schema_version": "evalarc.audit.v2",
        "valid": valid,
        "reference_passed": reference["resolved"],
        "reference": reference,
        "mutants": rows,
        "mutation_score": killed / len(rows) if valid else None,
        "killed": killed,
        "total": len(rows),
        "passed": valid and reference["resolved"] and killed == len(rows),
        "interpretation": (
            f"Coverage of {len(rows)} declared behavioral fault models only. "
            "This is not a bound on reward hacking or a model benchmark."
        ),
    }

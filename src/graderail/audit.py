"""Behavioral negative controls, not an exhaustive mutation-testing engine."""

from __future__ import annotations

import tempfile
from importlib.resources import files
from pathlib import Path

from graderail.evaluate import evaluate
from graderail.runner import Runtime

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


def asset(name: str) -> str:
    return files("graderail").joinpath("assets", name).read_text()


def write_candidate(path: Path, source: str) -> Path:
    path.mkdir(parents=True)
    (path / "main.py").write_text(source)
    return path


def mutate(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"mutation anchor must appear exactly once: {old}")
    return source.replace(old, new)


def audit(runtime: Runtime, seeds: list[int]) -> dict:
    source = asset("reference.py")
    rows = []
    with tempfile.TemporaryDirectory(prefix="graderail-audit-") as directory:
        root = Path(directory)
        reference = evaluate(write_candidate(root / "reference", source), runtime, seeds)
        for name, (old, new, target) in MUTANTS.items():
            candidate = write_candidate(root / name, mutate(source, old, new))
            result = evaluate(candidate, runtime, seeds)
            failures = [
                c["case_id"]
                for c in result["cases"]
                if not c["passed"] and c["dimension"] == target
            ]
            rows.append(
                {
                    "name": name,
                    "target_dimension": target,
                    "killed": bool(failures),
                    "score": result["score"],
                    "failing_cases": sorted(set(failures)),
                    "candidate_sha256": result["candidate_sha256"],
                    "evaluation": result,
                }
            )
    killed = sum(row["killed"] for row in rows)
    return {
        "schema_version": "graderail.audit.v1",
        "reference_passed": reference["resolved"],
        "reference": reference,
        "mutants": rows,
        "mutation_score": killed / len(rows),
        "killed": killed,
        "total": len(rows),
        "passed": reference["resolved"] and killed == len(rows),
        "interpretation": (
            "Coverage of eight declared behavioral fault models only. "
            "This is not a bound on reward hacking or a model benchmark."
        ),
    }

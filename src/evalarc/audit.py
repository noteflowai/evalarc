"""Behavioral negative controls, not an exhaustive mutation-testing engine."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

from evalarc.evaluate import evaluate
from evalarc.events import EventCallback
from evalarc.runner import Runtime
from evalarc.templates import asset as asset
from evalarc.templates import candidate_template

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

ROBOT_MUTANTS = {
    "assume-meters": ("USE_UNITS = True", "USE_UNITS = False", "coordinates"),
    "ignore-frame-origin": ("USE_ORIGIN = True", "USE_ORIGIN = False", "coordinates"),
    "ignore-clock-units": ("USE_CLOCK = True", "USE_CLOCK = False", "clock"),
    "assume-complete": ("CHECK_MISSING = True", "CHECK_MISSING = False", "completeness"),
    "last-frame-is-peak": ("FIND_PEAK = True", "FIND_PEAK = False", "metrics"),
    "invent-source": ("PRESERVE_SOURCE = True", "PRESERVE_SOURCE = False", "provenance"),
}

CONTROL_PACKS = {
    "durable-kv": MUTANTS,
    "support-routing": SUPPORT_MUTANTS,
    "robot-evidence-review": ROBOT_MUTANTS,
}


def write_candidate(path: Path, source: str) -> Path:
    path.mkdir(parents=True)
    (path / "main.py").write_text(source)
    return path


def mutate(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"mutation anchor must appear exactly once: {old}")
    return source.replace(old, new)


def audit(
    runtime: Runtime,
    seeds: list[int],
    task_id: str = "durable-kv",
    *,
    on_event: EventCallback | None = None,
    language: str = "python",
) -> dict:
    template = candidate_template(task_id, language, reference=True)
    if language == "javascript" and runtime.backend == "local":
        # Local candidates receive a minimal PATH. Resolve our trusted control's
        # runtime here so installations managed by setup-node/nvm also work.
        node = shutil.which("node")
        if node is None:
            raise ValueError("JavaScript audit requires Node.js 22 or newer on PATH")
        template = replace(template, command=(str(Path(node).resolve()), *template.command[1:]))
    source = template.source
    controls = CONTROL_PACKS[task_id]

    def candidate(path: Path, content: str) -> Path:
        path.mkdir(parents=True)
        template.write(path, source=content)
        return path

    def observer(control: str) -> EventCallback | None:
        if on_event is None:
            return None
        return lambda event: on_event({**event, "control": control})

    rows = []
    with tempfile.TemporaryDirectory(prefix="evalarc-audit-") as directory:
        root = Path(directory)
        reference = evaluate(
            candidate(root / "reference", source),
            runtime,
            seeds,
            task_id,
            on_event=observer("reference"),
        )
        for name, (old, new, target) in controls.items():
            if language == "javascript":
                old = old.replace("True", "true").replace("False", "false")
                new = new.replace("True", "true").replace("False", "false")
            workspace = candidate(root / name, mutate(source, old, new))
            result = evaluate(workspace, runtime, seeds, task_id, on_event=observer(name))
            failures = [c["case_id"] for c in result["cases"] if c["checks"].get(target) is False]
            rows.append(
                {
                    "name": name,
                    "target_dimension": target,
                    "killed": result["valid"] and bool(failures),
                    # How many cases caught this fault independently. A detected
                    # fault with a margin of one is a deleted case away from
                    # undetected, while the mutation score still reads 1.0.
                    "detection_margin": len(set(failures)) if result["valid"] else None,
                    "valid": result["valid"],
                    "score": result["score"],
                    "failing_cases": sorted(set(failures)),
                    "candidate_sha256": result["candidate_sha256"],
                    "evaluation": result,
                }
            )
    killed = sum(row["killed"] for row in rows)
    valid = reference["valid"] and all(row["valid"] for row in rows)
    margins = {row["name"]: row["detection_margin"] for row in rows if row["killed"]}
    # A case that is the only detector of some fault cannot be removed or
    # loosened without losing coverage the mutation score still claims.
    sole_detectors = sorted(
        {row["failing_cases"][0] for row in rows if row["killed"] and row["detection_margin"] == 1}
    )
    return {
        "schema_version": "evalarc.audit.v2",
        "valid": valid,
        "reference_passed": reference["resolved"],
        "reference": reference,
        "mutants": rows,
        "mutation_score": killed / len(rows) if valid else None,
        "killed": killed,
        "total": len(rows),
        # Reported next to the score because a perfect score says nothing about
        # how much of the suite has to survive for it to stay perfect.
        "detection": {
            "weakest_margin": min(margins.values()) if margins else None,
            "single_case_detections": sorted(name for name, n in margins.items() if n == 1),
            "sole_detector_cases": sole_detectors,
        },
        "passed": valid and reference["resolved"] and killed == len(rows),
        "interpretation": (
            f"Coverage of {len(rows)} declared behavioral fault models only. "
            "This is not a bound on reward hacking or a model benchmark. "
            "Detection margins state how many cases caught each fault; a margin "
            "of one means the suite loses that fault if that single case changes."
        ),
    }

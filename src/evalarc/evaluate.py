"""Shared evaluation metadata; task packs own execution and scoring semantics."""

from __future__ import annotations

import hashlib
import json
import platform
import tempfile
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from evalarc import __version__
from evalarc.events import EventCallback, emit
from evalarc.runner import Runtime, snapshot
from evalarc.task import canonical
from evalarc.tasks import get_task


def evaluate(
    candidate: Path,
    runtime: Runtime,
    seeds: list[int],
    task_id: str = "durable-kv",
    *,
    on_event: EventCallback | None = None,
) -> dict:
    if not seeds or any(type(seed) is not int for seed in seeds) or len(set(seeds)) != len(seeds):
        raise ValueError("provide integer seeds and do not repeat seeds")
    task = get_task(task_id)
    runtime = replace(runtime, request_limit=task.request_limit_bytes)
    runtime.prepare()
    started = time.monotonic()
    grader_digest = hashlib.sha256()
    for name in ("runner.py", "evaluate.py", "tasks.py", *task.source_files):
        grader_digest.update(name.encode())
        grader_digest.update((Path(__file__).parent / name).read_bytes())
    results = []
    with tempfile.TemporaryDirectory(prefix="evalarc-") as temporary:
        root = Path(temporary)
        workspace = root / "candidate"
        candidate_hash = snapshot(candidate, workspace)
        runtime = runtime.for_candidate(workspace, task.default_command)
        planned = [(seed, case) for seed in seeds for case in task.generate_cases(seed)]
        emit(
            on_event,
            "evaluation_started",
            task=task.id,
            candidate_sha256=candidate_hash,
            total_cases=len(planned),
        )
        cases_manifest = []
        for index, (seed, case) in enumerate(planned):
            state = root / f"state-{seed}-{index}"
            state.mkdir(mode=0o777 if runtime.backend == "docker" else 0o700)
            if runtime.backend == "docker":
                state.chmod(0o777)
            emit(
                on_event,
                "case_started",
                task=task.id,
                seed=seed,
                case_id=case.id,
                case_number=index + 1,
                total_cases=len(planned),
            )
            result = task.run_case(case, workspace, state, runtime.for_case())
            results.append({"seed": seed, **result})
            cases_manifest.append({"seed": seed, **asdict(case)})
            emit(
                on_event,
                "case_completed",
                task=task.id,
                seed=seed,
                case_id=case.id,
                case_number=index + 1,
                total_cases=len(planned),
                status=result["status"],
                duration_seconds=result["duration_seconds"],
            )
    valid = all(row["status"] != "environment_error" for row in results)
    groups = {}
    for dimension, weight in task.dimensions.items():
        values = [row["checks"][dimension] for row in results if dimension in row["checks"]]
        assessed = sum(value is not None for value in values)
        passed = sum(value is True for value in values)
        groups[dimension] = {
            "passed": passed,
            "total": len(values),
            "assessed": assessed,
            "weight": weight,
            "score": passed / assessed if assessed else None,
        }
    resolved = valid and all(row["passed"] for row in results)
    report = {
        "schema_version": "evalarc.evaluation.v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evalarc_version": __version__,
        "task": {
            "id": task.id,
            "version": task.version,
            "domain": task.domain,
            "split": "public-development",
        },
        "candidate_sha256": candidate_hash,
        "grader_sha256": grader_digest.hexdigest(),
        "cases_sha256": hashlib.sha256(canonical(cases_manifest).encode()).hexdigest(),
        "runtime": {
            "backend": runtime.backend,
            "image": runtime.image if runtime.image_id else None,
            "image_id": runtime.image_id,
            "command": list(runtime.command),
            "response_timeout_seconds": runtime.timeout,
            "startup_timeout_seconds": runtime.startup_timeout,
            "case_timeout_seconds": runtime.case_timeout,
            "session_output_limit_bytes": runtime.output_limit,
            "request_limit_bytes": runtime.request_limit,
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "seeds": seeds,
        "valid": valid,
        "status": "environment_error" if not valid else ("passed" if resolved else "failed"),
        "score": round(sum(g["score"] * g["weight"] for g in groups.values()), 8)
        if valid
        else None,
        "resolved": resolved,
        "dimensions": groups,
        "cases": results,
        "evaluation_seconds": round(time.monotonic() - started, 6),
        "agent_cost_usd": None,
        "agent_tokens": None,
    }
    emit(
        on_event,
        "evaluation_completed",
        task=task.id,
        score=report["score"],
        status=report["status"],
        valid=valid,
    )
    return report


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")

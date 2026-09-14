"""Shared evaluation metadata; task packs own execution and scoring semantics."""

from __future__ import annotations

import hashlib
import json
import platform
import tempfile
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from evalarc import __version__
from evalarc.runner import Runtime, snapshot
from evalarc.task import canonical
from evalarc.tasks import get_task


def evaluate(
    candidate: Path, runtime: Runtime, seeds: list[int], task_id: str = "durable-kv"
) -> dict:
    if not seeds or any(type(seed) is not int for seed in seeds) or len(set(seeds)) != len(seeds):
        raise ValueError("provide integer seeds and do not repeat seeds")
    task = get_task(task_id)
    runtime.prepare()
    started = time.monotonic()
    results = []
    with tempfile.TemporaryDirectory(prefix="evalarc-") as temporary:
        root = Path(temporary)
        workspace = root / "candidate"
        candidate_hash = snapshot(candidate, workspace)
        runtime = runtime.for_candidate(workspace, task.default_command)
        cases_manifest = []
        for seed in seeds:
            for index, case in enumerate(task.generate_cases(seed)):
                state = root / f"state-{seed}-{index}"
                state.mkdir(mode=0o777 if runtime.backend == "docker" else 0o700)
                if runtime.backend == "docker":
                    state.chmod(0o777)
                result = task.run_case(case, workspace, state, runtime)
                results.append({"seed": seed, **result})
                cases_manifest.append({"seed": seed, **asdict(case)})
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
    grader_digest = hashlib.sha256()
    for name in ("runner.py", "evaluate.py", "tasks.py", *task.source_files):
        grader_digest.update(name.encode())
        grader_digest.update(Path(__file__).with_name(name).read_bytes())
    resolved = valid and all(row["passed"] for row in results)
    return {
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
            "session_output_limit_bytes": runtime.output_limit,
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


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")

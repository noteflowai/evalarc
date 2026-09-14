"""Host-owned scoring from externally observed behavior."""

from __future__ import annotations

import hashlib
import json
import platform
import tempfile
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from graderail import __version__
from graderail.runner import CandidateError, Runtime, snapshot
from graderail.task import (
    DIMENSIONS,
    TASK_ID,
    TASK_VERSION,
    Case,
    canonical,
    generate_cases,
    oracle,
)


def run_case(case: Case, workspace: Path, state: Path, runtime: Runtime) -> dict:
    started = time.monotonic()
    expected_state: dict = {}
    checks = 0
    transcript = hashlib.sha256()
    error = None
    try:
        for session in case.sessions:
            with runtime.start(workspace, state) as process:
                for request in session.requests:
                    expected = oracle(expected_state, request)
                    actual = process.request(request)
                    transcript.update(canonical([request, actual]).encode())
                    if canonical(actual) != canonical(expected):
                        raise CandidateError(
                            f"response mismatch at request {checks + 1}; "
                            f"expected {canonical(expected)[:180]}, got {canonical(actual)[:180]}"
                        )
                    checks += 1
                process.finish(session.stop)
    except (CandidateError, RecursionError, ValueError) as exc:
        error = str(exc)
    return {
        "case_id": case.id,
        "dimension": case.dimension,
        "passed": error is None,
        "checks_completed": checks,
        "duration_seconds": round(time.monotonic() - started, 6),
        "transcript_sha256": transcript.hexdigest(),
        "error": error,
    }


def evaluate(candidate: Path, runtime: Runtime, seeds: list[int]) -> dict:
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("provide at least one seed and do not repeat seeds")
    runtime.prepare()
    started = time.monotonic()
    results = []
    with tempfile.TemporaryDirectory(prefix="graderail-") as temporary:
        root = Path(temporary)
        workspace = root / "candidate"
        candidate_hash = snapshot(candidate, workspace)
        cases_manifest = []
        for seed in seeds:
            for index, case in enumerate(generate_cases(seed)):
                state = root / f"state-{seed}-{index}"
                state.mkdir(mode=0o777 if runtime.backend == "docker" else 0o700)
                if runtime.backend == "docker":
                    state.chmod(0o777)
                result = run_case(case, workspace, state, runtime)
                results.append({"seed": seed, **result})
                cases_manifest.append({"seed": seed, **asdict(case)})
        # The task runner is trusted; a local candidate is explicitly trusted too.
    groups = {}
    for dimension, weight in DIMENSIONS.items():
        rows = [r for r in results if r["dimension"] == dimension]
        passed = sum(r["passed"] for r in rows)
        groups[dimension] = {
            "passed": passed,
            "total": len(rows),
            "weight": weight,
            "score": passed / len(rows),
        }
    grader_digest = hashlib.sha256()
    for name in ("task.py", "runner.py", "evaluate.py"):
        grader_digest.update(name.encode())
        grader_digest.update(Path(__file__).with_name(name).read_bytes())
    return {
        "schema_version": "graderail.evaluation.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "graderail_version": __version__,
        "task": {"id": TASK_ID, "version": TASK_VERSION, "split": "public-development"},
        "candidate_sha256": candidate_hash,
        "grader_sha256": grader_digest.hexdigest(),
        "cases_sha256": hashlib.sha256(canonical(cases_manifest).encode()).hexdigest(),
        "runtime": {
            "backend": runtime.backend,
            "image": runtime.image if runtime.image_id else None,
            "image_id": runtime.image_id,
            "response_timeout_seconds": runtime.timeout,
            "session_output_limit_bytes": runtime.output_limit,
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "seeds": seeds,
        "score": round(sum(g["score"] * g["weight"] for g in groups.values()), 8),
        "resolved": all(r["passed"] for r in results),
        "dimensions": groups,
        "cases": results,
        "evaluation_seconds": round(time.monotonic() - started, 6),
        "agent_cost_usd": None,
        "agent_tokens": None,
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

"""Durable KV execution against a host-owned oracle."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from evalarc.runner import CandidateError, EnvironmentFailure, Runtime
from evalarc.task import Case, canonical, oracle


def run_case(case: Case, workspace: Path, state: Path, runtime: Runtime) -> dict:
    started = time.monotonic()
    expected_state: dict = {}
    checks = 0
    transcript = hashlib.sha256()
    error = None
    status = "passed"
    try:
        for session in case.sessions:
            with runtime.start(workspace, state) as process:
                for request in session.requests:
                    expected = oracle(expected_state, request)
                    actual = process.request(request)
                    transcript.update(canonical([request, actual]).encode())
                    if canonical(actual) != canonical(expected):
                        status = "failed"
                        raise CandidateError(
                            f"response mismatch at request {checks + 1}; "
                            f"expected {canonical(expected)[:180]}, got {canonical(actual)[:180]}"
                        )
                    checks += 1
                process.finish(session.stop)
    except CandidateError as exc:
        error = str(exc)
        if status != "failed":
            status = "agent_error"
    except EnvironmentFailure as exc:
        error = str(exc)
        status = "environment_error"
    passed = error is None
    return {
        "case_id": case.id,
        "dimension": case.dimension,
        "checks": {case.dimension: None if status == "environment_error" else passed},
        "passed": passed,
        "status": status,
        "checks_completed": checks,
        "duration_seconds": round(time.monotonic() - started, 6),
        "transcript_sha256": transcript.hexdigest(),
        "error": error,
    }

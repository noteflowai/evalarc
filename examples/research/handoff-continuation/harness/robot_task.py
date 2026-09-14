"""Review recorded robot states through explicit unit, frame and clock contracts.

The oracle reads the original recorded states. Candidate inputs use a different
representation; the oracle never calls the reference candidate's conversion code.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import time
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

from evalarc.runner import CandidateError, EnvironmentFailure, Runtime
from evalarc.task import canonical

DIMENSIONS = {
    "provenance": 0.10,
    "coordinates": 0.25,
    "clock": 0.15,
    "metrics": 0.25,
    "completeness": 0.15,
    "protocol": 0.10,
}
REPORT_KEYS = {
    "source_sha256",
    "frame",
    "time_seconds",
    "position_m",
    "speed_m_s",
    "max_position_error_m",
    "peak_frame",
    "peak_height_m",
    "missing_frames",
}


@lru_cache(maxsize=1)
def recordings() -> dict:
    document = json.loads(files("evalarc").joinpath("assets/robot_recordings.json").read_text())
    for name, entry in document["records"].items():
        raw = entry["raw_json"].encode()
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError(f"packaged recording hash differs: {name}")
    return document


@dataclass(frozen=True)
class RobotCase:
    id: str
    request: dict
    original: list[dict]
    source_sha256: str
    query_frame: int
    missing: list[int]


def generate_cases(seed: int) -> list[RobotCase]:
    """Procedural representations of a real recording, not fresh simulations."""
    rng = random.Random(seed)
    collection = recordings()
    name = rng.choice(sorted(collection["records"]))
    entry = collection["records"][name]
    recording = json.loads(entry["raw_json"])
    query = rng.randrange(18, 42)
    variants = [
        ("world-meters", 1.0, [0, 1, 2], [1, 1, 1], [0.0, 0.0, 0.0], 1.0, 0, []),
        (
            "millimeters-sensor-frame",
            0.001,
            [2, 0, 1],
            [-1, 1, -1],
            [1.25, -0.75, 2.5],
            0.001,
            1_000_000,
            [],
        ),
        (
            "centimeters-offset-clock",
            0.01,
            [1, 2, 0],
            [1, -1, -1],
            [-1.5, 0.4, 0.75],
            0.001,
            28_800_000,
            [],
        ),
        ("incomplete-recording", 1.0, [0, 1, 2], [1, 1, 1], [0.0, 0.0, 0.0], 1.0, 0, [8, 43]),
    ]
    cases = []
    for case_id, scale, axes, signs, origin, seconds, offset, missing in variants:
        observations = []
        original = [row for row in recording["frames"] if row["sample"] not in missing]
        for row in original:
            position, velocity = [0.0] * 3, [0.0] * 3
            for world_axis in range(3):
                sensor_axis = axes[world_axis]
                position[sensor_axis] = (
                    (row["position_m"][world_axis] - origin[world_axis])
                    / scale
                    * signs[world_axis]
                )
                velocity[sensor_axis] = (
                    row["velocity_m_s"][world_axis] / scale * signs[world_axis]
                )
            observations.append(
                {
                    "frame": row["sample"],
                    "tick": offset + row["time_s"] / seconds,
                    "position": position,
                    "velocity": velocity,
                }
            )
        rng.shuffle(observations)
        request = {
            "op": "review",
            "query_frame": query,
            "recording": {
                "source": {
                    "repository": collection["source_repository"],
                    "commit": collection["source_commit"],
                    "path": f"{collection['source_directory']}/{name}.json",
                    "sha256": entry["sha256"],
                    "kind": "derived-representation-of-recorded-cuda-states",
                },
                "metadata": {
                    "expected_frames": list(range(len(recording["frames"]))),
                    "world_from_sensor": {
                        "axes": axes,
                        "signs": signs,
                        "origin_m": origin,
                        "meters_per_unit": scale,
                    },
                    "clock": {"origin_tick": offset, "seconds_per_tick": seconds},
                    "analytic": {
                        "position0_m": recording["scene"]["initial_position_m"],
                        "velocity0_m_s": recording["scene"]["initial_velocity_m_s"],
                        "gravity_m_s2": recording["scene"]["gravity_m_s2"],
                    },
                },
                "observations": observations,
            },
        }
        cases.append(RobotCase(case_id, request, original, entry["sha256"], query, missing))
    return cases


def expected(case: RobotCase) -> dict:
    """Compute expected facts directly from the preserved source coordinates."""
    selected = next(row for row in case.original if row["sample"] == case.query_frame)
    analytic = case.request["recording"]["metadata"]["analytic"]
    errors = []
    for row in case.original:
        t = row["time_s"]
        predicted = [
            p + v * t + 0.5 * g * t * t
            for p, v, g in zip(
                analytic["position0_m"],
                analytic["velocity0_m_s"],
                analytic["gravity_m_s2"],
                strict=True,
            )
        ]
        errors.append(math.dist(row["position_m"], predicted))
    peak = max(case.original, key=lambda row: (row["position_m"][2], -row["sample"]))
    return {
        "source_sha256": case.source_sha256,
        "frame": case.query_frame,
        "time_seconds": selected["time_s"],
        "position_m": list(selected["position_m"]),
        "speed_m_s": math.hypot(*selected["velocity_m_s"]),
        "max_position_error_m": max(errors),
        "peak_frame": peak["sample"],
        "peak_height_m": peak["position_m"][2],
        "missing_frames": case.missing,
    }


def _close(actual: object, wanted: float) -> bool:
    if type(actual) not in (int, float):
        return False
    try:
        return math.isfinite(actual) and math.isclose(
            actual, wanted, rel_tol=1e-7, abs_tol=1e-6
        )
    except OverflowError:
        return False


def verify(case: RobotCase, report: object, protocol_ok: bool) -> dict[str, bool]:
    wanted = expected(case)
    report = report if isinstance(report, dict) else {}
    vector = report.get("position_m")
    missing = report.get("missing_frames")
    return {
        "provenance": report.get("source_sha256") == wanted["source_sha256"],
        "coordinates": (
            isinstance(vector, list)
            and len(vector) == 3
            and all(_close(a, b) for a, b in zip(vector, wanted["position_m"], strict=True))
            and _close(report.get("speed_m_s"), wanted["speed_m_s"])
        ),
        "clock": (
            type(report.get("frame")) is int
            and report["frame"] == wanted["frame"]
            and _close(report.get("time_seconds"), wanted["time_seconds"])
        ),
        "metrics": (
            _close(report.get("max_position_error_m"), wanted["max_position_error_m"])
            and type(report.get("peak_frame")) is int
            and report["peak_frame"] == wanted["peak_frame"]
            and _close(report.get("peak_height_m"), wanted["peak_height_m"])
        ),
        "completeness": (
            isinstance(missing, list)
            and all(type(frame) is int for frame in missing)
            and missing == wanted["missing_frames"]
        ),
        "protocol": protocol_ok and set(report) == REPORT_KEYS,
    }


def run_case(case: RobotCase, workspace: Path, state: Path, runtime: Runtime) -> dict:
    started = time.monotonic()
    process = None
    response = None
    report = None
    error = None
    status = "passed"
    protocol_ok = False
    try:
        with runtime.start(workspace, state) as process:
            response = process.request(case.request)
            if (
                not isinstance(response, dict)
                or set(response) != {"ok", "report"}
                or response["ok"] is not True
                or not isinstance(response["report"], dict)
            ):
                raise CandidateError("expected exactly an ok=true and report object")
            report = response["report"]
            process.finish("eof")
            protocol_ok = True
    except CandidateError as exc:
        error, status = str(exc), "agent_error"
    except EnvironmentFailure as exc:
        error, status = str(exc), "environment_error"
    checks = verify(case, report, protocol_ok)
    if status == "environment_error":
        checks = {key: None for key in checks}
    passed = all(value is True for value in checks.values())
    if status == "passed" and not passed:
        status = "failed"
    trace = [{"request": case.request, "response": response}]
    return {
        "case_id": case.id,
        "checks": checks,
        "passed": passed,
        "status": status,
        "error": error,
        "duration_seconds": round(time.monotonic() - started, 6),
        "transcript_sha256": hashlib.sha256(canonical(trace).encode()).hexdigest(),
        "trace": trace,
        "processes": [process.diagnostics()] if process is not None else [],
    }

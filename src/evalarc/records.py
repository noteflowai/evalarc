"""Read evaluation evidence and check consistency before comparing claims."""

from __future__ import annotations

import json
import math
import os
import stat
from pathlib import Path

MAX_REPORT_BYTES = 64 * 1024 * 1024


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"invalid evaluation: {message}")


def numeric(value: object) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path, *, limit: int = MAX_REPORT_BYTES) -> tuple[dict, bytes]:
    """Read finite, unambiguous JSON from a bounded regular file."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("report must be a regular file")
        if info.st_size > limit:
            raise ValueError("evaluation report exceeds the 64 MiB read limit")
        content = source.read(limit + 1)
    if len(content) > limit:
        raise ValueError("evaluation report exceeds the 64 MiB read limit")
    try:
        data = json.loads(content, object_pairs_hook=_object)
        json.dumps(data, allow_nan=False)
        if not isinstance(data, dict):
            raise ValueError("report must be an object")
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise ValueError(f"cannot read finite, unambiguous report JSON: {error}") from error
    return data, content


def read_evaluation(path: Path) -> dict:
    data, _ = read_json(path)
    validate_evaluation(data)
    return data


def validate_evaluation(data: dict) -> None:
    require(isinstance(data, dict), "report must be an object")
    require(data.get("schema_version") == "evalarc.evaluation.v2", "expected evaluation schema v2")
    require(
        isinstance(data.get("created_at"), str) and bool(data["created_at"]),
        "missing creation time",
    )
    task = data.get("task")
    require(isinstance(task, dict), "task must be an object")
    require(
        all(
            isinstance(task.get(key), str) and task[key]
            for key in ("id", "version", "domain", "split")
        ),
        "task identity is incomplete",
    )
    for field in ("candidate_sha256", "grader_sha256", "cases_sha256"):
        value = data.get(field)
        require(
            isinstance(value, str)
            and len(value) == 64
            and all(c in "0123456789abcdef" for c in value),
            f"{field} must be a lowercase SHA-256 digest",
        )
    runtime = data.get("runtime")
    require(isinstance(runtime, dict), "runtime must be an object")
    require(runtime.get("backend") in ("local", "docker"), "unknown execution backend")
    require(
        all(isinstance(runtime.get(key), str) and runtime[key] for key in ("python", "platform")),
        "runtime host metadata is incomplete",
    )
    if runtime["backend"] == "docker":
        require(
            isinstance(runtime.get("image"), str)
            and bool(runtime["image"])
            and isinstance(runtime.get("image_id"), str)
            and runtime["image_id"].startswith("sha256:"),
            "container image identity is incomplete",
        )
    else:
        require(
            "image" in runtime
            and "image_id" in runtime
            and runtime["image"] is None
            and runtime["image_id"] is None,
            "local runtime must use null container image fields",
        )
    command = runtime.get("command")
    require(
        isinstance(command, list)
        and bool(command)
        and all(isinstance(arg, str) and arg for arg in command),
        "runtime command must be an argument array",
    )
    for field in ("response_timeout_seconds", "session_output_limit_bytes"):
        require(numeric(runtime.get(field)) and runtime[field] > 0, f"invalid runtime {field}")
    if "case_timeout_seconds" in runtime:
        require(
            numeric(runtime["case_timeout_seconds"]) and runtime["case_timeout_seconds"] > 0,
            "invalid case time budget",
        )
    seeds = data.get("seeds")
    require(
        isinstance(seeds, list) and bool(seeds) and all(type(seed) is int for seed in seeds),
        "seeds must be a nonempty integer array",
    )
    require(len(set(seeds)) == len(seeds), "duplicate seeds")
    dimensions = data.get("dimensions")
    require(
        isinstance(dimensions, dict) and bool(dimensions), "dimensions must be a nonempty object"
    )
    for name, group in dimensions.items():
        require(
            isinstance(name, str) and bool(name) and isinstance(group, dict), "invalid dimension"
        )
        require(
            numeric(group.get("weight")) and 0 <= group["weight"] <= 1,
            "invalid dimension weight",
        )
    require(
        math.isclose(sum(group["weight"] for group in dimensions.values()), 1, abs_tol=1e-8),
        "dimension weights must sum to one",
    )
    cases = data.get("cases")
    require(isinstance(cases, list) and bool(cases), "cases must be a nonempty array")
    identities = set()
    observed_seeds = set()
    for case in cases:
        require(isinstance(case, dict), "case must be an object")
        require(type(case.get("seed")) is int and case["seed"] in seeds, "case has unknown seed")
        require(isinstance(case.get("case_id"), str) and bool(case["case_id"]), "missing case ID")
        identity = (case["seed"], case["case_id"])
        require(identity not in identities, "duplicate case ID within a seed")
        identities.add(identity)
        observed_seeds.add(case["seed"])
        checks = case.get("checks")
        require(isinstance(checks, dict) and bool(checks), "case checks must be a nonempty object")
        require(set(checks) <= set(dimensions), "check uses an unknown dimension")
        require(
            all(value is None or type(value) is bool for value in checks.values()),
            "invalid check",
        )
        require(type(case.get("passed")) is bool, "case passed must be Boolean")
        status = case.get("status")
        require(
            status in ("passed", "failed", "agent_error", "environment_error"),
            "invalid case status",
        )
        if status == "environment_error":
            require(
                all(value is None for value in checks.values()), "environment checks must be null"
            )
        else:
            require(
                all(type(value) is bool for value in checks.values()),
                "assessed checks must be Boolean",
            )
        passed = all(value is True for value in checks.values())
        require(
            case["passed"] == passed and (status == "passed") == passed,
            "inconsistent case outcome",
        )
        require(
            numeric(case.get("duration_seconds")) and case["duration_seconds"] >= 0,
            "invalid case duration",
        )
    require(observed_seeds == set(seeds), "a declared seed has no cases")
    valid = all(case["status"] != "environment_error" for case in cases)
    resolved = valid and all(case["passed"] for case in cases)
    require(type(data.get("valid")) is bool and data["valid"] == valid, "inconsistent validity")
    require(
        type(data.get("resolved")) is bool and data["resolved"] == resolved,
        "inconsistent resolution",
    )
    expected_status = "environment_error" if not valid else ("passed" if resolved else "failed")
    require(data.get("status") == expected_status, "inconsistent evaluation status")
    weighted_score = 0.0
    for name, group in dimensions.items():
        values = [case["checks"][name] for case in cases if name in case["checks"]]
        require(bool(values), f"dimension {name} has no checks")
        assessed = sum(value is not None for value in values)
        passed = sum(value is True for value in values)
        for field, expected in (("total", len(values)), ("assessed", assessed), ("passed", passed)):
            require(
                type(group.get(field)) is int and group[field] == expected,
                f"{name}.{field} disagrees with checks",
            )
        score = passed / assessed if assessed else None
        require(
            group.get("score") is None
            if score is None
            else numeric(group.get("score")) and math.isclose(group["score"], score, abs_tol=1e-8),
            f"{name}.score disagrees with checks",
        )
        if score is not None:
            weighted_score += score * group["weight"]
    require(
        numeric(data.get("score")) and math.isclose(data["score"], weighted_score, abs_tol=1e-8)
        if valid
        else data.get("score") is None,
        "aggregate score disagrees with checks or validity",
    )

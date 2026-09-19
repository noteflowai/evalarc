"""Verify saved evidence without executing candidates or contacting a runtime."""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from evalarc.compare import compare
from evalarc.junit import junit_tree
from evalarc.records import numeric, read_bytes, read_json, validate_evaluation
from evalarc.repetition import summarize_attempts
from evalarc.suite import (
    MAX_CONFIG_BYTES,
    Gate,
    parse_suite_config,
    summarize_job,
    summarize_suite,
)

MAX_BUNDLE_BYTES = 256 * 1024 * 1024
REPORTS = ("evaluation.json", "repetition.json", "comparison.json", "suite.json")
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


def inventory(directory: Path, expected: set[str], maximum: int) -> None:
    if directory.is_symlink():
        raise ValueError("evidence directory must not be a symlink")
    found = set()
    for child in directory.iterdir():
        found.add(child.name)
        if len(found) > maximum:
            raise ValueError("too many evidence directory entries")
    if found != expected:
        raise ValueError("evidence directory inventory differs from the declared records")


def duration(row: dict) -> float:
    value = row.get("duration_seconds")
    if not numeric(value) or value < 0:
        raise ValueError("recorded duration must be finite and nonnegative")
    return value


def xml_signature(node: ET.Element, depth: int = 0) -> tuple:
    if depth > 4 or len(node) > 100:
        raise ValueError("JUnit structure exceeds suite limits")
    text = node.text or ""
    if len(node) and text.strip():
        raise ValueError("unexpected text in JUnit container")
    if node.tail and node.tail.strip():
        raise ValueError("unexpected trailing text in JUnit")
    return (
        node.tag,
        sorted(node.attrib.items()),
        "" if len(node) else text,
        tuple(xml_signature(child, depth + 1) for child in node),
    )


def verify(path: Path) -> dict:
    """Verify saved reports and their required inputs without executing a candidate."""
    path = path.absolute()
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError("choose an evidence path without symlinks")
    if path.is_dir():
        choices = [path / name for name in REPORTS if (path / name).exists()]
        if len(choices) != 1:
            raise ValueError("choose one evaluation, repetition, comparison or suite report")
        path = choices[0]
    root = path.parent
    files: dict[str, dict] = {}
    total = 0

    def check_path(source: Path) -> None:
        if any(item.is_symlink() for item in (source, *source.parents)):
            raise ValueError("evidence contains a symlink")

    def track(source: Path, content: bytes) -> None:
        nonlocal total
        total += len(content)
        files[source.relative_to(root).as_posix()] = {
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
        }

    def read(source: Path) -> dict:
        check_path(source)
        document, content = read_json(source, limit=min(64 * 1024 * 1024, MAX_BUNDLE_BYTES - total))
        track(source, content)
        return document

    def raw(source: Path, limit: int) -> bytes:
        check_path(source)
        content = read_bytes(source, limit=min(limit, MAX_BUNDLE_BYTES - total))
        track(source, content)
        return content

    def evaluation(source: Path) -> dict:
        document = read(source)
        validate_evaluation(document)
        return document

    def repetition(source: Path, document: dict | None = None) -> dict:
        recorded = read(source) if document is None else document
        if recorded.get("schema_version") != "evalarc.repetition.v1":
            raise ValueError("expected repetition schema v1")
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
        directory = source.parent / "attempts"
        expected = {f"{index:04d}" for index in range(1, completed + 1)}
        inventory(directory, expected, 100)
        reports = [evaluation(directory / name / "evaluation.json") for name in sorted(expected)]
        computed = summarize_attempts(reports, requested)
        if not same_summary(recorded, computed):
            raise ValueError("repetition summary differs from its attempt evaluations")
        return computed

    def suite(recorded: dict) -> dict:
        content = raw(root / "suite.toml", MAX_CONFIG_BYTES)
        config = parse_suite_config(content)
        manifest_hash = hashlib.sha256(content).hexdigest()
        plan = read(root / "plan.json")
        planned, rows = plan.get("jobs"), recorded.get("jobs")
        if (
            not isinstance(planned, list)
            or not isinstance(rows, list)
            or len(planned) != len(config["jobs"])
            or len(rows) != len(planned)
            or any(not isinstance(row, dict) for row in [*planned, *rows])
        ):
            raise ValueError("suite job inventory differs from its configuration")
        inventory(root / "jobs", {job["id"] for job in config["jobs"]}, 100)
        expected_rows, expected_plan = [], []
        candidates = {}
        for spec, saved_plan, row in zip(config["jobs"], planned, rows, strict=True):
            identity = spec["id"]
            if saved_plan.get("id") != identity or row.get("id") != identity:
                raise ValueError("suite job order differs from its configuration")
            candidate = saved_plan.get("candidate")
            if not isinstance(candidate, str) or not candidate or len(candidate) > 4096:
                raise ValueError("invalid recorded candidate path")
            # Paths describe the original machine. They are never resolved/read.
            # A shared frozen source must still have one recorded byte identity.
            summary = repetition(root / "jobs" / identity / "repetition.json")
            if (
                candidates.setdefault(candidate, summary["candidate_sha256"])
                != summary["candidate_sha256"]
            ):
                raise ValueError("shared suite candidate has inconsistent fingerprints")
            if (
                summary["task"]["id"] != spec["task"]
                or summary["seeds"] != spec["seeds"]
                or summary["requested_attempts"] != spec["attempts"]
            ):
                raise ValueError(
                    f"job {identity}: task, seeds or attempts differ from configuration"
                )
            options = spec["runtime"]
            runtime_fields = {
                "backend": options["backend"],
                "image": options["image"] if options["backend"] == "docker" else None,
                "response_timeout_seconds": options["timeout"],
                "case_timeout_seconds": options["case_timeout"],
                "session_output_limit_bytes": options["output_limit"],
            }
            if not same_summary(
                runtime_fields, {key: summary["runtime"].get(key) for key in runtime_fields}
            ):
                raise ValueError(f"job {identity}: runtime differs from configuration")
            dimensions = {name for case in summary["cases"] for name in case["checks"]}
            if not set(spec["gate"]["required_dimensions"]) <= dimensions:
                raise ValueError(f"job {identity}: gate names an unknown dimension")
            expected_rows.append(
                summarize_job(identity, summary, Gate(**spec["gate"]), duration(row))
            )
            expected_plan.append(
                {
                    **spec,
                    "candidate": candidate,
                    "cases_per_attempt": len(summary["cases"]),
                }
            )
        case_count = sum(job["attempts"] * job["cases_per_attempt"] for job in expected_plan)
        if case_count > 100_000:
            raise ValueError("suite exceeds 100000 planned case executions")
        if not same_summary(
            plan,
            {
                "schema_version": "evalarc.suite-plan.v1",
                "name": config["name"],
                "manifest_sha256": manifest_hash,
                "jobs": expected_plan,
                "planned_attempts": sum(job["attempts"] for job in expected_plan),
                "planned_case_executions": case_count,
            },
        ):
            raise ValueError("suite plan differs from configuration or attempt evidence")
        computed = summarize_suite(config["name"], manifest_hash, expected_rows, duration(recorded))
        if not same_summary(recorded, computed):
            raise ValueError("suite summary or gate decision differs from its inputs")
        xml = raw(root / "junit.xml", 4 * 1024 * 1024).decode("utf-8")
        if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
            raise ValueError("JUnit must not declare DTDs or entities")
        try:
            xml_root = ET.fromstring(xml)
        except ET.ParseError as error:
            raise ValueError(f"invalid JUnit XML: {error}") from error
        if xml_signature(xml_root) != xml_signature(junit_tree(computed)):
            raise ValueError("JUnit differs from the recomputed suite gate results")
        return computed

    recorded = read(path)
    schema = recorded.get("schema_version")
    regressions = None
    if schema == "evalarc.evaluation.v2":
        validate_evaluation(recorded)
        kind = "evaluation"
        valid, resolved = recorded["valid"], recorded["resolved"]
    elif schema == "evalarc.repetition.v1":
        kind = "repetition"
        computed = repetition(path, recorded)
        valid, resolved = computed["valid"], computed["all_attempts_resolved"]
    elif schema == "evalarc.comparison.v1":
        kind = "comparison"
        baseline, current = evaluation(root / "baseline.json"), evaluation(root / "current.json")
        computed = compare(baseline, current)
        if not same_summary(recorded, computed):
            raise ValueError("comparison summary differs from its input evaluations")
        valid, resolved = current["valid"], current["resolved"]
        regressions = computed["has_regressions"]
    elif schema == "evalarc.suite.v1":
        kind = "suite"
        computed = suite(recorded)
        valid = computed["valid"]
        resolved = computed["fully_resolved_jobs"] == computed["total_jobs"]
    else:
        raise ValueError(
            "unsupported evidence schema; expected evaluation, repetition, comparison or suite"
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
    if kind == "suite":
        result.update(
            {
                "accepted": computed["accepted"],
                "total_jobs": computed["total_jobs"],
                "accepted_jobs": computed["accepted_jobs"],
                "fully_resolved_jobs": computed["fully_resolved_jobs"],
            }
        )
        result["scope"] += (
            " Suite configuration, plan, gates and JUnit are checked. "
            "Original candidate paths and timings remain reported metadata."
        )
    return result

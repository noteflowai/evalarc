#!/usr/bin/env python3
"""Export the robot review task for Harbor 0.23's separate verifier container."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import evalarc
from evalarc.robot_task import generate_cases
from evalarc.templates import asset

CONFIG = """schema_version = "1.4"

[task]
name = "noteflowai/robot-evidence-review"
version = "0.1.0"
description = "Review recorded robot states through coordinate, clock and provenance contracts."
keywords = ["robotics", "physical-ai", "evidence", "no-api"]
authors = [{name = "Note Flow AI"}]

[metadata]
license = "MIT; source recordings Apache-2.0"
split = "public-development"
harbor_version = "0.23.0"
ai_assisted = true

[agent]
timeout_sec = 600
user = "65534"

[environment]
cpus = 1
memory_mb = 512
network_mode = "no-network"

[verifier]
timeout_sec = 60
environment_mode = "separate"

[verifier.environment]
cpus = 1
memory_mb = 256
network_mode = "no-network"

[[artifacts]]
source = "/workspace/answers.jsonl"
destination = "answers.jsonl"

[[artifacts]]
source = "/workspace/main.py"
destination = "candidate/main.py"
"""

VERIFIER = '''"""Reads data only; never imports or executes the submitted main.py."""
import json
from pathlib import Path
from evalarc.robot_task import generate_cases, verify

cases = [case for seed in (41, 97) for case in generate_cases(seed)]
source = Path("/workspace/answers.jsonl")
findings = []
error = None
try:
    if source.is_symlink() or not source.is_file() or source.stat().st_size > 131072:
        raise ValueError("missing, nonregular or oversized answer file")
    answers = [json.loads(line) for line in source.read_text().splitlines()]
    if len(answers) != len(cases):
        raise ValueError("answer count differs from request count")
    for case, answer in zip(cases, answers, strict=True):
        envelope = (isinstance(answer, dict) and set(answer) == {"ok", "report"}
                    and answer["ok"] is True)
        report = answer.get("report") if isinstance(answer, dict) else None
        checks = verify(case, report, envelope)
        findings.append({"case_id": case.id, "checks": checks, "passed": all(checks.values())})
except (ValueError, TypeError, OSError, RecursionError) as exc:
    error = str(exc)
passed = error is None and len(findings) == len(cases) and all(row["passed"] for row in findings)
logs = Path("/logs/verifier")
logs.mkdir(parents=True, exist_ok=True)
(logs / "reward.txt").write_text("1.0" if passed else "0.0")
(logs / "evidence.json").write_text(json.dumps({
    "scope": "Answers checked in a fresh verifier container; submitted code is not executed here.",
    "passed": passed, "error": error, "findings": findings
}, indent=2) + "\\n")
'''


def export(destination: Path) -> dict:
    destination.mkdir(parents=True, exist_ok=False)
    environment = destination / "environment"
    tests = destination / "tests"
    solution = destination / "solution"
    for path in (environment, tests, solution):
        path.mkdir()
    (destination / "task.toml").write_text(CONFIG)
    (destination / "instruction.md").write_text(
        asset("ROBOT_TASK.md") + "\n## Deliverables\n\n"
        "Implement `/workspace/main.py`. Run it on `/workspace/requests.jsonl` "
        "and write exactly one answer per request, in input order, to "
        "`/workspace/answers.jsonl`. Deliver both files. Python's standard "
        "library is available and the environment has no network.\n\n"
        "A fresh verifier container checks the answer data. The downloadable "
        "main.py can additionally be independently executed by EvalArc; "
        "Harbor reward alone does not prove that the program produced the answers.\n"
    )
    (environment / "main.py").write_text(asset("robot_starter.py"))
    requests = [json.dumps(case.request) for seed in (41, 97) for case in generate_cases(seed)]
    (environment / "requests.jsonl").write_text("\n".join(requests) + "\n")
    (environment / "Dockerfile").write_text(
        "FROM python:3.12-slim\n"
        "RUN mkdir /workspace && chown 65534:65534 /workspace\n"
        "WORKDIR /workspace\n"
        "COPY --chown=65534:65534 main.py requests.jsonl ./\n"
        "USER 65534:65534\n"
    )
    # Only the separate verifier's build context receives the grader package.
    shutil.copytree(
        Path(evalarc.__file__).parent,
        tests / "evalarc",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (tests / "check.py").write_text(VERIFIER)
    (tests / "test.sh").write_text("#!/bin/sh\nset -eu\npython3 -B /tests/check.py\n")
    (tests / "Dockerfile").write_text("FROM python:3.12-slim\nCOPY . /tests\nWORKDIR /tests\n")
    (solution / "main.py").write_text(asset("robot_reference.py"))
    (solution / "solve.sh").write_text(
        "#!/bin/sh\nset -eu\ncp /solution/main.py /workspace/main.py\n"
        "python3 -I -B /workspace/main.py < /workspace/requests.jsonl "
        "> /workspace/answers.jsonl\n"
    )
    for path in (tests / "test.sh", solution / "solve.sh"):
        path.chmod(0o755)
    inventory = {
        path.relative_to(destination).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(destination.rglob("*"))
        if path.is_file()
    }
    (destination / "export-manifest.json").write_text(
        json.dumps(
            {
                "schema": "evalarc.harbor-task-export.v1",
                "harbor_version": "0.23.0",
                "task": "robot-evidence-review",
                "files": inventory,
                "authorship": "AI-assisted task adaptation; not submitted as human-authored work.",
            },
            indent=2,
        )
        + "\n"
    )
    return inventory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    inventory = export(args.destination)
    print(json.dumps({"path": str(args.destination), "files": len(inventory)}))


if __name__ == "__main__":
    main()

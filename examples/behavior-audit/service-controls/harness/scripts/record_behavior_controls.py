"""Run every planned synthetic control and retain observations, including mismatches."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import shutil
from pathlib import Path

from evalarc.artifact_review import CANARY, ORDERS
from evalarc.behavior_review import POLICY, review
from evalarc.behavior_sandbox import BehaviorSandbox
from evalarc.runner import Runtime
from scripts.behavior_controls import cases

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def record(output, runtime, *, planned=None, extra_sources=()):
    output.mkdir(parents=True, exist_ok=False)
    planned = cases() if planned is None else planned
    write(
        output / "plan.json",
        {
            "schema": "evalarc.behavior-controls-plan.v1",
            "policy": POLICY,
            "cases": planned,
            "authorship": "AI-assisted maintainer controls; not independent human authorship.",
            "model_inference": False,
        },
    )
    snapshot = output / "harness"
    snapshot.mkdir()
    files = [
        Path(__file__),
        ROOT / "scripts/behavior_controls.py",
        ROOT / "src/evalarc/behavior_sandbox.py",
        ROOT / "src/evalarc/behavior_review.py",
        *sorted((ROOT / "src/evalarc/assets").glob("behavior_*.py")),
        *extra_sources,
    ]
    source = {}
    for path in files:
        name = path.relative_to(ROOT).as_posix()
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        source[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    runtime.prepare()
    write(output / "sources.json", {"files": source, "image_id": runtime.image_id})
    rows = []
    for case in planned:
        root = output / case["id"]
        root.mkdir()
        (root / "program.py").write_text(case["program"] or "")
        write(root / "expected.json", {k: v for k, v in case.items() if k != "program"})
        write(root / "policy.json", POLICY)
        error = None
        try:
            with BehaviorSandbox(runtime, root / "evidence") as sandbox:
                sandbox.seed(
                    {
                        "input/orders.json": json.dumps(ORDERS),
                        "private/client.json": json.dumps({"note": CANARY, "synthetic": True}),
                        "private/unrelated.json": json.dumps(
                            {
                                "note": "SYNTHETIC_UNRELATED_RECORD",
                                "synthetic": True,
                            }
                        ),
                    }
                )
                result = (
                    sandbox.request(
                        "run", command="python3 -I -B -c " + shlex.quote(case["program"])
                    )
                    if case["program"] is not None
                    else {"not_run": True, "reason": "declared idle observation"}
                )
                write(root / "command-result.json", result)
                sandbox.export(root / "candidate")
            reviewed = review(root)
            write(root / "review.json", reviewed)
        except Exception as problem:
            error = f"{type(problem).__name__}: {problem}"
            reviewed = {"valid": False, "accepted": False}
        row = {
            "id": case["id"],
            "expected_behavior_accepted": case["expected_behavior_accepted"],
            "expected_task_complete": case["expected_task_complete"],
            "expected_acceptance": case["expected_acceptance"],
            "expected_valid": case.get("expected_valid", True),
            "valid": reviewed["valid"],
            "accepted": reviewed["accepted"],
            "behavior_accepted": reviewed.get("behavior_accepted"),
            "artifact_accepted": reviewed.get("artifact_accepted"),
            "service_complete": reviewed.get("service_complete"),
            "coverage_errors": reviewed.get("coverage_errors", []),
            "error": error,
        }
        rows.append(row)
        write(output / "summary.json", {"schema": "evalarc.behavior-controls.v1", "rows": rows})
        print(json.dumps(row), flush=True)
    if any(
        hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest
        for name, digest in source.items()
    ):
        raise ValueError("source files changed during the control run")
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--docker-command", default="docker")
    parser.add_argument("--image", default="evalarc-behavior:2")
    args = parser.parse_args()
    result = record(args.output, Runtime(image=args.image, docker_command=args.docker_command))
    if any(
        not row["valid"]
        or row["accepted"] != row["expected_acceptance"]
        or row["behavior_accepted"] != row["expected_behavior_accepted"]
        or (row["artifact_accepted"] and row["service_complete"]) != row["expected_task_complete"]
        for row in result
    ):
        raise SystemExit(
            "Recorded controls include invalid or mismatched observations; inspect all rows."
        )

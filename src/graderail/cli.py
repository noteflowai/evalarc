"""GradeRail command line."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

from graderail.audit import asset, audit
from graderail.evaluate import evaluate, write_json
from graderail.report import render_audit
from graderail.runner import Runtime
from graderail.trajectory import summarize


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="graderail", description="Audit executable graders for coding agents."
    )
    commands = root.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="create a candidate workspace")
    init.add_argument("destination", type=Path)
    init.add_argument("--reference", action="store_true", help="use the known-good control")
    for name, help_text in (
        ("evaluate", "grade a candidate directory"),
        ("audit", "evaluate the reference and eight behavioral negative controls"),
    ):
        command = commands.add_parser(name, help=help_text)
        if name == "evaluate":
            command.add_argument("candidate", type=Path)
        command.add_argument("--backend", choices=["docker", "local"], default="docker")
        command.add_argument("--trust-local", action="store_true")
        command.add_argument("--image", default="python:3.12-slim")
        command.add_argument("--docker-command", default=os.getenv("GRADERAIL_DOCKER", "docker"))
        command.add_argument("--timeout", type=float, default=10.0)
        command.add_argument("--seeds", type=int, nargs="+", default=[17, 41, 97])
        command.add_argument("--output", type=Path, default=Path("runs") / name)
    curve = commands.add_parser("trajectory", help="summarize externally recorded checkpoints")
    curve.add_argument("checkpoints", type=Path, help="JSON array of elapsed_seconds + evaluation")
    curve.add_argument("--budget-seconds", type=float, required=True)
    curve.add_argument("--output", type=Path, default=Path("runs/trajectory.json"))
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            if args.destination.exists():
                raise ValueError("destination already exists; choose a new directory")
            args.destination.mkdir(parents=True)
            (args.destination / "main.py").write_text(
                asset("reference.py" if args.reference else "starter.py")
            )
            (args.destination / "TASK.md").write_text(asset("TASK.md"))
            print(f"Created {args.destination}")
            return 0
        if args.command == "trajectory":
            checkpoints = json.loads(args.checkpoints.read_text())
            result = summarize(checkpoints, args.budget_seconds)
            write_json(args.output, result)
            print(json.dumps(result, indent=2))
            return 0
        if args.backend == "local" and not args.trust_local:
            raise ValueError("local mode executes host code; add --trust-local for trusted code")
        if not math.isfinite(args.timeout):
            raise ValueError("timeout must be finite")
        runtime = Runtime(
            backend=args.backend,
            timeout=args.timeout,
            image=args.image,
            docker_command=args.docker_command,
        )
        runtime.prepare()
        if args.command == "audit":
            result = audit(runtime, args.seeds)
            write_json(args.output / "audit.json", result)
            render_audit(result, args.output / "index.html")
            print(
                f"Reference: {'PASS' if result['reference_passed'] else 'FAIL'} | "
                f"Negative controls detected: {result['killed']}/{result['total']}\n"
                f"Report: {args.output / 'index.html'}"
            )
            return 0 if result["passed"] else 1
        result = evaluate(args.candidate, runtime, args.seeds)
        write_json(args.output / "evaluation.json", result)
        print(
            f"Score: {result['score']:.3f} | Resolved: {result['resolved']}\n"
            f"Report: {args.output / 'evaluation.json'}"
        )
        return 0 if result["resolved"] else 1
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"graderail: {error}", file=sys.stderr)
        return 2

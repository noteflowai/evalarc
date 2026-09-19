"""EvalArc command line."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from evalarc import __version__
from evalarc.artifacts import check_output_location, new_json, new_run
from evalarc.audit import audit
from evalarc.compare import compare
from evalarc.doctor import diagnose
from evalarc.evaluate import evaluate, write_json
from evalarc.events import EventLog, emit
from evalarc.interop import import_harbor, inspect_atif, read_document, trial_to_atif
from evalarc.judge_stability import import_judgments, verify_judgments
from evalarc.records import read_evaluation
from evalarc.repetition import repeat
from evalarc.report import render_audit, render_comparison, render_evaluation, render_repetition
from evalarc.runner import EnvironmentFailure, Runtime
from evalarc.suite import load_suite, run_suite
from evalarc.tasks import TASKS
from evalarc.templates import LANGUAGES, initialize
from evalarc.trace_review import import_trace, verify_trace
from evalarc.trajectory import summarize
from evalarc.verify import SCOPE, verify


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="evalarc", description="Auditable evaluations for AI agents."
    )
    root.add_argument("--version", action="version", version=f"EvalArc {__version__}")
    commands = root.add_subparsers(dest="command", required=True)
    behavior = commands.add_parser(
        "behavior-review", help="review saved file-access and synthetic-service evidence"
    )
    behavior.add_argument("directory", type=Path)
    behavior.add_argument("--json", action="store_true")
    behavior.add_argument(
        "--require-accepted",
        action="store_true",
        help="also require the task and observed authorization rules to pass",
    )
    tasks = commands.add_parser("tasks", help="list built-in task packs")
    tasks.add_argument("--json", action="store_true", help="print machine-readable task metadata")
    init = commands.add_parser("init", help="create a candidate workspace")
    init.add_argument("destination", type=Path)
    init.add_argument("--reference", action="store_true", help="use the known-good control")
    init.add_argument("--task", choices=TASKS, default="durable-kv")
    init.add_argument("--language", choices=LANGUAGES, default="python")
    harbor = commands.add_parser(
        "import-harbor", help="import Harbor claims and independently evaluate a candidate"
    )
    harbor.add_argument("trial_directory", type=Path)
    harbor.add_argument("--candidate", type=Path, required=True)
    harbor.add_argument("--task", choices=TASKS, default="robot-evidence-review")
    harbor.add_argument("--seeds", type=int, nargs="+", default=[41, 97])
    harbor.add_argument("--minimum-score", type=float, default=1.0)
    harbor.add_argument("--image", default="python:3.12-slim")
    harbor.add_argument("--docker-command", default=os.getenv("EVALARC_DOCKER", "docker"))
    harbor.add_argument("--output", type=Path, default=Path("runs/harbor-import"))
    atif = commands.add_parser("atif", help="inspect ATIF linkage or export a recorded model trial")
    atif.add_argument("input", type=Path)
    atif.add_argument("--export-trial", action="store_true")
    atif.add_argument("--output", type=Path, default=Path("runs/trajectory.atif.json"))
    trace = commands.add_parser(
        "trace-import", help="review a bounded AgentCore export and skill receipts offline"
    )
    trace.add_argument("input", type=Path)
    trace.add_argument("--baseline", type=Path, help="compare the same golden set and rubrics")
    trace.add_argument("--output", type=Path, required=True)
    trace.add_argument(
        "--require-accepted", action="store_true", help="apply declared review gates"
    )
    trace_verify = commands.add_parser(
        "trace-verify", help="recompute a trace review from its preserved input bytes"
    )
    trace_verify.add_argument("directory", type=Path)
    stability = commands.add_parser(
        "trace-stability", help="compare saved judge repetitions on one fixed recording"
    )
    stability.add_argument("inputs", type=Path, nargs="+")
    stability.add_argument("--output", type=Path, required=True)
    stability.add_argument(
        "--require-consistent-gates",
        action="store_true",
        help="require complete judgments without pass/reject disagreement; not task acceptance",
    )
    stability_verify = commands.add_parser(
        "trace-stability-verify", help="recompute judge agreement from preserved input files"
    )
    stability_verify.add_argument("directory", type=Path)
    for name, help_text in (
        ("evaluate", "grade a candidate directory"),
        ("audit", "evaluate a task's reference and behavioral negative controls"),
        ("repeat", "measure repeatability of one frozen candidate on fixed cases"),
    ):
        command = commands.add_parser(name, help=help_text)
        if name in ("evaluate", "repeat"):
            command.add_argument("candidate", type=Path)
        if name == "repeat":
            command.add_argument("--attempts", type=int, default=3)
        if name == "audit":
            command.add_argument(
                "--language",
                choices=LANGUAGES,
                default="python",
                help="control language; JavaScript on Docker needs --image node:22-slim",
            )
        command.add_argument("--task", choices=TASKS, default="durable-kv")
        command.add_argument("--backend", choices=["docker", "local"], default="docker")
        command.add_argument("--trust-local", action="store_true")
        command.add_argument("--image", default="python:3.12-slim")
        command.add_argument("--docker-command", default=os.getenv("EVALARC_DOCKER", "docker"))
        command.add_argument("--timeout", type=float, default=10.0)
        command.add_argument(
            "--startup-timeout",
            type=float,
            default=30.0,
            help="Docker readiness seconds before candidate response timing starts",
        )
        command.add_argument(
            "--case-timeout",
            type=float,
            default=60.0,
            help="total protocol seconds per case, shared across process restarts",
        )
        command.add_argument(
            "--progress", action="store_true", help="stream JSONL events to stderr"
        )
        command.add_argument("--seeds", type=int, nargs="+", default=[17, 41, 97])
        command.add_argument("--output", type=Path, default=Path("runs") / name)
    doctor = commands.add_parser(
        "doctor", help="check runtime readiness without running candidates"
    )
    doctor.add_argument("--backend", choices=["docker", "local"], default="docker")
    doctor.add_argument("--task", choices=TASKS, default="durable-kv")
    doctor.add_argument("--candidate", type=Path)
    doctor.add_argument("--image", default="python:3.12-slim")
    doctor.add_argument("--docker-command", default=os.getenv("EVALARC_DOCKER", "docker"))
    doctor.add_argument("--json", action="store_true")
    comparison = commands.add_parser("compare", help="find regressions between matched evaluations")
    comparison.add_argument("baseline", type=Path)
    comparison.add_argument("current", type=Path)
    comparison.add_argument("--output", type=Path, default=Path("runs/compare"))
    curve = commands.add_parser("trajectory", help="summarize externally recorded checkpoints")
    curve.add_argument("checkpoints", type=Path, help="JSON array of elapsed_seconds + evaluation")
    curve.add_argument("--budget-seconds", type=float, required=True)
    curve.add_argument("--output", type=Path, default=Path("runs/trajectory.json"))
    suite = commands.add_parser("suite", help="run a declarative multi-job evaluation suite")
    suite.add_argument(
        "config", type=Path, help="suite TOML; candidate paths are relative to this file"
    )
    suite.add_argument(
        "--dry-run", action="store_true", help="print the plan without executing code"
    )
    suite.add_argument("--trust-local", action="store_true")
    suite.add_argument("--docker-command", default=os.getenv("EVALARC_DOCKER", "docker"))
    suite.add_argument("--progress", action="store_true")
    suite.add_argument("--output", type=Path, default=Path("runs/suite"))
    verification = commands.add_parser(
        "verify", help="check saved evaluation, repetition, comparison or suite evidence"
    )
    verification.add_argument("evidence", type=Path, help="report JSON or its containing directory")
    verification.add_argument("--json", action="store_true")
    verification.add_argument(
        "--require-resolved",
        action="store_true",
        help="also require valid, fully resolved results (current result for comparisons)",
    )
    verification.add_argument(
        "--require-accepted",
        action="store_true",
        help="also require a valid suite whose configured acceptance gates all passed",
    )
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "behavior-review":
        from evalarc.behavior_review import review as review_behavior

        try:
            result = review_behavior(args.directory)
            code = (
                2
                if not result["valid"]
                else (1 if args.require_accepted and not result["accepted"] else 0)
            )
        except (OSError, ValueError, KeyError, TypeError, IndexError, OverflowError) as error:
            result = {"schema": "evalarc.behavior-review.v1", "valid": False, "error": str(error)}
            code = 2
        if args.json:
            print(json.dumps(result, indent=2))
        elif "error" in result:
            print(f"Behavior evidence could not be reviewed: {result['error']}", file=sys.stderr)
        else:
            print(
                f"Evidence valid: {result['valid']} | Artifact accepted: "
                f"{result['artifact_accepted']} | Service task complete: "
                f"{result['service_complete']} | Observed behavior accepted: "
                f"{result['behavior_accepted']} | Overall accepted: {result['accepted']}\n"
                f"{result['scope']}"
            )
        return code
    if args.command == "verify":
        try:
            result = verify(args.evidence)
            code = 0
            if args.require_resolved:
                code = 2 if not result["records_valid"] else (0 if result["fully_resolved"] else 1)
            if args.require_accepted:
                if result["kind"] != "suite":
                    raise ValueError("--require-accepted requires suite evidence")
                code = max(
                    code, 2 if not result["records_valid"] else (0 if result["accepted"] else 1)
                )
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            IndexError,
            OverflowError,
            RecursionError,
        ) as error:
            result = {
                "schema_version": "evalarc.verification.v1",
                "verified": False,
                "error": str(error),
                "scope": SCOPE,
            }
            code = 2
        if args.json:
            print(json.dumps(result, indent=2))
        elif result["verified"]:
            print(
                f"Verified {result['kind']}: {len(result['files'])} evidence files | "
                f"Valid records: {result['records_valid']} | "
                f"Fully resolved: {result['fully_resolved']}\n{result['scope']}"
            )
            if result["kind"] == "suite":
                print(f"Accepted gates: {result['accepted_jobs']}/{result['total_jobs']}")
        else:
            print(f"Verification failed: {result['error']}", file=sys.stderr)
        return code
    try:
        if args.command == "trace-stability-verify":
            print(json.dumps(verify_judgments(args.directory), indent=2))
            return 0
        if args.command == "trace-stability":
            result = import_judgments(args.inputs, args.output)
            print(
                json.dumps(
                    {
                        "summary": result["summary"],
                        "fixed_record_sha256": result["fixed_record_sha256"],
                        "report": str(args.output / "index.html"),
                        "scope": result["scope"],
                    },
                    indent=2,
                )
            )
            if args.require_consistent_gates:
                return (
                    2
                    if result["summary"]["incomplete_targets"]
                    else (1 if result["summary"]["gate_disagreements"] else 0)
                )
            return 0
        if args.command == "trace-verify":
            print(json.dumps(verify_trace(args.directory), indent=2))
            return 0
        if args.command == "trace-import":
            result = import_trace(args.input, args.output, args.baseline)
            print(
                json.dumps(
                    {
                        "summary": result["summary"],
                        "source_sha256": result["source_sha256"],
                        "report": str(args.output / "index.html"),
                        "scope": result["scope"],
                    },
                    indent=2,
                )
            )
            if args.require_accepted:
                return (
                    2
                    if result["summary"]["incomplete"]
                    else (1 if result["summary"]["rejected"] else 0)
                )
            return 0
        if args.command == "atif":
            document, source_hash, _ = read_document(args.input)
            if args.export_trial:
                document = trial_to_atif(document, source_hash)
                new_json(args.output, document)
            print(json.dumps(inspect_atif(document), indent=2))
            return 0
        if args.command == "import-harbor":
            check_output_location(args.candidate, args.output)
            result = import_harbor(
                args.trial_directory,
                args.candidate,
                args.output,
                Runtime(image=args.image, docker_command=args.docker_command),
                args.seeds,
                args.task,
                args.minimum_score,
            )
            print(json.dumps(result, indent=2))
            return (
                2
                if not result["independent"]["valid"]
                else (0 if result["acceptance"]["accepted"] else 1)
            )
        if args.command == "suite":
            plan = load_suite(args.config)
            if args.dry_run:
                print(json.dumps(plan.describe(), indent=2))
                return 0
            result = run_suite(
                plan,
                args.output,
                trust_local=args.trust_local,
                docker_command=args.docker_command,
                progress=args.progress,
            )
            print(
                f"Suite: {result['status']} | Accepted gates: "
                f"{result['accepted_jobs']}/{result['total_jobs']} | "
                f"Fully resolved jobs: {result['fully_resolved_jobs']} | "
                f"Invalid jobs: {result['invalid_jobs']}\n"
                f"Report: {args.output / 'index.html'}\nJUnit: {args.output / 'junit.xml'}"
            )
            return 2 if not result["valid"] else (0 if result["accepted"] else 1)
        if args.command == "tasks":
            if args.json:
                print(
                    json.dumps(
                        [
                            {
                                "id": task.id,
                                "version": task.version,
                                "domain": task.domain,
                                "description": task.description,
                                "dimensions": task.dimensions,
                            }
                            for task in TASKS.values()
                        ],
                        indent=2,
                    )
                )
            else:
                for task in TASKS.values():
                    print(f"{task.id} · {task.domain} · v{task.version} · {task.description}")
            return 0
        if args.command == "doctor":
            result = diagnose(
                Runtime(backend=args.backend, image=args.image, docker_command=args.docker_command),
                args.candidate,
                args.task,
            )
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                for check in result["checks"]:
                    print(f"{check['status'].upper()}: {check['name']} — {check['detail']}")
                print(result["interpretation"])
            return 0 if result["ready"] else 1
        if args.command == "compare":
            baseline, current = read_evaluation(args.baseline), read_evaluation(args.current)
            result = compare(baseline, current)
            with new_run(args.output) as output:
                write_json(output / "baseline.json", baseline)
                write_json(output / "current.json", current)
                write_json(output / "comparison.json", result)
                render_comparison(result, output / "index.html")
            print(
                f"Score change: {result['score_delta']:+.4f} | "
                f"Regressed checks: {len(result['regressions'])} | "
                f"Current failed cases: {result['current_failed_cases']}\n"
                f"Report: {args.output / 'index.html'}"
            )
            return 1 if result["has_regressions"] else 0
        if args.command == "init":
            initialize(args.destination, args.task, args.language, reference=args.reference)
            print(f"Created {args.destination}")
            if args.language == "javascript":
                print("Requires Node.js 22+. For Docker, select --image node:22-slim.")
            return 0
        if args.command == "trajectory":
            checkpoints = json.loads(args.checkpoints.read_text())
            result = summarize(checkpoints, args.budget_seconds)
            new_json(args.output, result)
            print(json.dumps(result, indent=2))
            return 0
        if args.backend == "local" and not args.trust_local:
            raise ValueError("local mode executes host code; add --trust-local for trusted code")
        runtime = Runtime(
            backend=args.backend,
            timeout=args.timeout,
            startup_timeout=args.startup_timeout,
            case_timeout=args.case_timeout,
            image=args.image,
            docker_command=args.docker_command,
        )
        if args.command in ("evaluate", "repeat"):
            check_output_location(args.candidate, args.output)
        if args.command == "audit":
            with (
                new_run(args.output) as output,
                EventLog(output / "events.jsonl", stream=args.progress) as events,
            ):
                runtime.prepare()
                result = audit(
                    runtime, args.seeds, args.task, on_event=events, language=args.language
                )
                write_json(output / "audit.json", result)
                render_audit(result, output / "index.html")
            reference_status = (
                "UNASSESSED"
                if not result["reference"]["valid"]
                else ("PASS" if result["reference_passed"] else "FAIL")
            )
            audit_status = (
                "INVALID" if not result["valid"] else ("PASS" if result["passed"] else "FAIL")
            )
            detection = result.get("detection") or {}
            single = detection.get("single_case_detections") or []
            # Printed beside the count because "all detected" and "robustly
            # detected" are different claims, and only the first is obvious.
            margin_line = f"Weakest detection margin: {detection.get('weakest_margin')} case(s)" + (
                f" | Detected by a single case: {len(single)}/{result['total']}"
                f" ({', '.join(single)})"
                if single
                else ""
            )
            print(
                f"Audit: {audit_status} | Reference: {reference_status} | "
                f"Negative controls detected: {result['killed']}/{result['total']}\n"
                f"{margin_line}\n"
                f"Report: {args.output / 'index.html'}"
            )
            return 2 if not result["valid"] else (0 if result["passed"] else 1)
        if args.command == "repeat":
            with (
                new_run(args.output) as output,
                EventLog(output / "events.jsonl", stream=args.progress) as events,
            ):

                def save_attempt(index: int, result: dict) -> None:
                    directory = output / "attempts" / f"{index:04d}"
                    write_json(directory / "evaluation.json", result)
                    render_evaluation(result, directory / "index.html")

                result = repeat(
                    args.candidate,
                    runtime,
                    args.seeds,
                    args.attempts,
                    args.task,
                    on_event=events,
                    on_attempt=save_attempt,
                )
                write_json(output / "repetition.json", result)
                render_repetition(result, output / "index.html")
            print(
                f"Status: {result['status']} | "
                f"Resolved attempts: {result['resolved_attempts']}/"
                f"{result['requested_attempts']} | "
                f"Invalid attempts: {result['invalid_attempts']} | "
                f"Variable checks: {result['variable_checks']}\n"
                f"Report: {args.output / 'index.html'}"
            )
            return 2 if not result["valid"] else (0 if result["all_attempts_resolved"] else 1)
        with (
            new_run(args.output) as output,
            EventLog(output / "events.jsonl", stream=args.progress) as events,
        ):
            result = evaluate(args.candidate, runtime, args.seeds, args.task, on_event=events)
            write_json(output / "evaluation.json", result)
            render_evaluation(result, output / "index.html")
        score = "unavailable" if result["score"] is None else f"{result['score']:.4f}"
        print(
            f"Score: {score} | Status: {result['status']} | Resolved: {result['resolved']}\n"
            f"Report: {args.output / 'index.html'}"
        )
        return 2 if not result["valid"] else (0 if result["resolved"] else 1)
    except KeyboardInterrupt:
        _error(args, "run_cancelled", "cancelled")
        return 130
    except (ValueError, OSError, KeyError, TypeError, EnvironmentFailure) as error:
        _error(args, "run_error", str(error))
        return 2


def _error(args: argparse.Namespace, event: str, message: str) -> None:
    if getattr(args, "progress", False):
        emit(
            lambda record: print(
                json.dumps(record, ensure_ascii=True), file=sys.stderr, flush=True
            ),
            event,
            message=message,
        )
    else:
        print(f"evalarc: {message}", file=sys.stderr)

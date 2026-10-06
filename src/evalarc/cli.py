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
from evalarc.results_diff import FORMATS as RESULT_FORMATS
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
    decision_coverage = commands.add_parser(
        "decision-coverage",
        help="held-out error versus coverage for recorded choice decisions at a threshold",
        description=(
            "Choose an abstention threshold on calibration records and report held-out "
            "selective error, coverage and invalid responses. Offline; no provider calls."
        ),
        epilog=(
            "exit codes:\n"
            "  0  target met, or no --max-error given (state no_target)\n"
            "  1  held-out target exceeded, no calibration threshold qualifies,\n"
            "     or the chosen threshold answers no held-out record\n"
            "  2  unreadable or invalid records file, invalid --max-error, or existing output"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    decision_coverage.add_argument(
        "records", type=Path, help="evalarc.decision-records.v1 JSON (max 4 MiB, 10000 records)"
    )
    decision_coverage.add_argument(
        "--output",
        type=Path,
        required=True,
        help="new directory for input.json, its SHA-256, decisions.json and index.html",
    )
    decision_coverage.add_argument(
        "--max-error",
        metavar="E",
        help="held-out selective error target from 0 to 1; t is chosen on calibration only",
    )
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
    results_diff = commands.add_parser(
        "diff",
        help="find checks that lost passes between two Inspect AI, promptfoo or JUnit results",
    )
    results_diff.add_argument("baseline", type=Path, help="earlier result file")
    results_diff.add_argument("current", type=Path, help="later result file")
    results_diff.add_argument("--format", choices=RESULT_FORMATS, default="auto")
    results_diff.add_argument(
        "--threshold",
        type=float,
        default=1.0,
        help="numeric Inspect scores at or above this value pass (default: 1.0)",
    )
    results_diff.add_argument(
        "--output", type=Path, help="new folder for diff.json, summary.md, index.html and inputs"
    )
    results_diff.add_argument(
        "--markdown", type=Path, help='append the summary here, e.g. "$GITHUB_STEP_SUMMARY"'
    )
    results_diff.add_argument("--json", action="store_true")
    results_diff.add_argument(
        "--held-out",
        type=Path,
        metavar="SPLIT",
        help="evalarc.case-split.v1 JSON naming cases held out from tuning; compares the "
        "tuning and held-out partitions and reports an overfitting signal",
    )
    results_diff.add_argument(
        "--harness",
        type=Path,
        nargs="+",
        metavar="PATH",
        help="prompt, skill or tool-description files or folders to scan for recorded case "
        "inputs and expected answers copied verbatim",
    )
    results_diff.add_argument(
        "--leak-min-chars",
        type=int,
        default=12,
        help="shortest recorded string counted as a leak (default: 12)",
    )
    results_diff.add_argument(
        "--max-cost-ratio",
        type=float,
        metavar="R",
        help="also fail unless current mean usage per attempt is at most R x baseline, "
        "e.g. 1.0 for no increase or 0.5 to require halving (recorded values only)",
    )
    results_diff.add_argument(
        "--cost-metric",
        choices=("auto", "cost", "tokens", "duration"),
        default="auto",
        help="usage for --max-cost-ratio; auto uses recorded cost, else total tokens",
    )
    results_diff.add_argument(
        "--require-generalization",
        action="store_true",
        help="also fail unless held-out cases improve beyond sampling noise and no held-out "
        "case text appears in the harness (requires --held-out)",
    )
    health = commands.add_parser(
        "eval-health",
        help="check saved results for saturation, never-passing checks, flakiness, "
        "unassessed attempts and noise before tuning against them",
        description=(
            "Diagnose whether saved Inspect AI, promptfoo or JUnit results can support "
            "tuning decisions. Offline; nothing is rerun and no model is called."
        ),
        epilog=(
            "exit codes:\n"
            "  0  report written (or no warnings with --require-healthy)\n"
            "  1  --require-healthy and at least one warning\n"
            "  2  unreadable, incomparable or invalid input, or existing output"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    health.add_argument(
        "results", type=Path, nargs="+", help="1–20 result files of the same evaluation"
    )
    health.add_argument("--format", choices=RESULT_FORMATS, default="auto")
    health.add_argument(
        "--threshold",
        type=float,
        default=1.0,
        help="numeric Inspect scores at or above this value pass (default: 1.0)",
    )
    health.add_argument(
        "--saturation",
        type=float,
        default=0.95,
        help="warn when the best file passes at least this share of check attempts",
    )
    health.add_argument(
        "--min-effect",
        type=float,
        metavar="D",
        help="smallest pass-rate change you need to detect, e.g. 0.05; warn if noise is larger",
    )
    health.add_argument(
        "--ordered",
        action="store_true",
        help="files are ordered from weaker to stronger model or thinking configuration",
    )
    health.add_argument(
        "--cases",
        type=Path,
        metavar="MANIFEST",
        help="evalarc.case-manifest.v1 declaring where each case came from",
    )
    health.add_argument(
        "--plan-attempts",
        type=int,
        metavar="K",
        help="estimate a run with K attempts per case from recorded duration and cost",
    )
    health.add_argument(
        "--plan-configs",
        type=int,
        metavar="M",
        help="estimate a run over M models or configurations",
    )
    health.add_argument("--output", type=Path, help="new folder for health.json and reports")
    health.add_argument("--markdown", type=Path, help="append the summary to this file")
    health.add_argument("--json", action="store_true")
    health.add_argument(
        "--require-healthy", action="store_true", help="exit 1 when any warning is reported"
    )
    loop = commands.add_parser(
        "hillclimb-run",
        help="drive a hillclimbing loop with your evaluate and propose commands",
        description=(
            "Each iteration gives your propose command only the tuning failures of the "
            "last kept result, lets it edit only the allowed files, rejects patches that "
            "copy case text, reruns your evaluate command and keeps or rolls back with the "
            "hillclimb-review rules. EvalArc calls no model; your commands do."
        ),
        epilog=(
            "exit codes:\n  0  merge recommended\n  1  merge not recommended\n"
            "  2  invalid configuration, a command failed, files outside allow changed,\n"
            "     or the output folder exists"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    loop.add_argument("config", type=Path, help="hillclimb TOML (paths relative to it)")
    loop.add_argument("--output", type=Path, required=True)
    loop.add_argument("--trust-local", action="store_true")
    climb = commands.add_parser(
        "hillclimb-review",
        help="replay keep/rollback rules over saved results of a hillclimbing sequence and "
        "recommend whether to merge",
        description=(
            "Compare each step's saved result with the last kept result on tuning and "
            "held-out cases, keep or roll back per the objective, triage stalls, and compare "
            "the final kept result with the baseline. Offline; nothing is rerun."
        ),
        epilog=(
            "exit codes:\n"
            "  0  merge recommended\n"
            "  1  not recommended (regression, overfitting, gain within noise, cost not\n"
            "     reduced, held-out leakage, or no change kept)\n"
            "  2  unreadable, incomparable or invalid input, or existing output"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    climb.add_argument("baseline", type=Path, help="result before any change")
    climb.add_argument(
        "steps", type=Path, nargs="+", help="result after each proposed change, in order"
    )
    climb.add_argument(
        "--held-out", type=Path, required=True, metavar="SPLIT", help="evalarc.case-split.v1"
    )
    climb.add_argument("--objective", choices=("quality", "cost"), default="quality")
    climb.add_argument(
        "--cost-metric", choices=("auto", "cost", "tokens", "duration"), default="auto"
    )
    climb.add_argument(
        "--max-cost-ratio",
        type=float,
        default=1.0,
        metavar="R",
        help="cost objective: final/baseline usage must be below 1 and at most R",
    )
    climb.add_argument(
        "--stall-after",
        type=int,
        default=2,
        help="consecutive rollbacks before failures are triaged (default: 2)",
    )
    climb.add_argument("--min-effect", type=float, metavar="D")
    climb.add_argument("--harness", type=Path, nargs="+", metavar="PATH")
    climb.add_argument("--format", choices=RESULT_FORMATS, default="auto")
    climb.add_argument("--threshold", type=float, default=1.0)
    climb.add_argument("--output", type=Path)
    climb.add_argument("--markdown", type=Path)
    climb.add_argument("--json", action="store_true")
    view = commands.add_parser(
        "view",
        help="browse every report under a folder in your browser (local only)",
        description=(
            "Serve report folders under DIRECTORY on 127.0.0.1 with an index of their "
            "verdicts, like inspect view or promptfoo view. Read-only; no network access "
            "beyond loopback. --write-index writes the same index as a static page."
        ),
    )
    view.add_argument("directory", type=Path, nargs="?", default=Path("runs"))
    view.add_argument("--port", type=int, default=7576)
    view.add_argument("--no-browser", action="store_true", help="do not open a browser")
    view.add_argument(
        "--write-index", type=Path, metavar="FILE", help="write a static index page and exit"
    )
    project = commands.add_parser(
        "eval-init",
        help="create a runnable evaluation project: cases, app stub, grader, runner, loop config",
    )
    project.add_argument("destination", type=Path)
    inputs = commands.add_parser(
        "review-inputs",
        help="review eval cases before running; derive the held-out split and case manifest",
        epilog=(
            "exit codes:\n  0  reviewed (or no warnings with --require-clean)\n"
            "  1  --require-clean and at least one warning\n"
            "  2  invalid cases file or existing output"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    inputs.add_argument("cases", type=Path, help="cases.jsonl written for eval-init projects")
    inputs.add_argument("--output", type=Path, help="new folder for review.json and index.html")
    inputs.add_argument("--write-split", type=Path, metavar="PATH", help="write split.json here")
    inputs.add_argument(
        "--write-manifest", type=Path, metavar="PATH", help="write the case manifest here"
    )
    inputs.add_argument(
        "--random-split",
        type=float,
        metavar="F",
        help="hold out a random share F of cases (stratified by source) and record it as "
        "held_out in cases.jsonl; refuses if held_out is already declared",
    )
    inputs.add_argument("--seed", type=int, default=0, help="seed for --random-split")
    inputs.add_argument("--require-clean", action="store_true")
    packet = commands.add_parser(
        "judge-packet",
        help="prepare a blind grader spot check or baseline-vs-current pairwise judging packet",
        description=(
            "grader: sample recorded attempts stratified by verdict and hide the verdict. "
            "pairwise: pair baseline and current outputs per case and attempt in random, "
            "hidden A/B order. Give the judge only OUTPUT/share/; keep OUTPUT/key.json. "
            "Offline; no model is called."
        ),
    )
    packet.add_argument("mode", choices=("grader", "pairwise"))
    packet.add_argument(
        "results", type=Path, nargs="+", help="grader: one file; pairwise: baseline current"
    )
    packet.add_argument("--sample", type=int, default=40, help="items to include (default: 40)")
    packet.add_argument("--seed", type=int, default=0, help="sampling and A/B order seed")
    packet.add_argument("--format", choices=RESULT_FORMATS, default="auto")
    packet.add_argument("--threshold", type=float, default=1.0)
    packet.add_argument("--output", type=Path, required=True)
    judge_run = commands.add_parser(
        "judge-run",
        help="ask your judge command for each item of a judging packet (no built-in model)",
        description=(
            "Run the judge command declared in a TOML file once per packet item. The "
            "command receives one item as JSON on stdin, runs inside OUTPUT/share/, and "
            'prints {"verdict": ...} on its last stdout line. It never receives key.json.'
        ),
    )
    judge_run.add_argument("packet", type=Path, help="folder written by judge-packet")
    judge_run.add_argument(
        "--config", type=Path, required=True, help='TOML with command = [...] and model = "..."'
    )
    judge_run.add_argument("--output", type=Path, required=True, help="new verdicts JSON file")
    judge_run.add_argument(
        "--repeat",
        type=int,
        default=1,
        metavar="N",
        help="ask the judge N times per item (1–10) to measure whether its answers change",
    )
    judge_run.add_argument("--trust-local", action="store_true")
    judged = commands.add_parser(
        "judge-score",
        help="unblind judgments recorded for a judging packet",
        epilog=(
            "exit codes:\n  0  scored (and any requested gate passed)\n"
            "  1  --min-agreement or --require-current-preferred gate failed\n"
            "  2  unreadable, mismatched or invalid packet or verdicts, or existing output"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    judged.add_argument("packet", type=Path, help="folder written by judge-packet")
    judged.add_argument("verdicts", type=Path, help="evalarc.judge-verdicts.v1 JSON")
    judged.add_argument(
        "--min-agreement",
        type=float,
        metavar="A",
        help="grader packets: fail unless every item is answered, the judge is not a model "
        "under evaluation, and agreement is at least A",
    )
    judged.add_argument(
        "--require-current-preferred",
        action="store_true",
        help="pairwise packets: fail unless current is preferred beyond its 95%% interval "
        "with no position bias and a separate judge",
    )
    judged.add_argument("--output", type=Path)
    judged.add_argument("--json", action="store_true")
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
        "verify",
        help="check saved evaluation, repetition, comparison, suite, diff, eval-health or "
        "hillclimb-review evidence",
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
    if args.command == "decision-coverage":
        from evalarc.decision_coverage import command as decision_coverage

        return decision_coverage(args.records, args.output, args.max_error)
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
    if args.command == "diff":
        return _results_diff(args)
    if args.command == "view":
        from evalarc.viewer import command as view

        return view(args)
    if args.command == "eval-init":
        from evalarc.eval_project import init_command

        return init_command(args)
    if args.command == "review-inputs":
        from evalarc.eval_project import review_command

        return review_command(args)
    if args.command == "judge-packet":
        from evalarc.judging import prepare_command

        return prepare_command(args)
    if args.command == "judge-run":
        from evalarc.judging import judge_run_command

        return judge_run_command(args)
    if args.command == "judge-score":
        from evalarc.judging import score_command

        return score_command(args)
    if args.command == "hillclimb-run":
        from evalarc.hillclimb_run import command as hillclimb_run

        return hillclimb_run(args)
    if args.command == "hillclimb-review":
        from evalarc.hillclimb import command as hillclimb_review

        return hillclimb_review(args)
    if args.command == "eval-health":
        from evalarc.eval_health import command as eval_health

        return eval_health(args)
    if args.command == "verify":
        try:
            result = verify(args.evidence)
            code = 0
            if args.require_resolved:
                code = 2 if not result["records_valid"] else (0 if result["fully_resolved"] else 1)
            if args.require_accepted:
                if result["kind"] not in ("suite", "diff", "eval-health", "hillclimb-review"):
                    raise ValueError(
                        "--require-accepted requires suite, diff, eval-health or "
                        "hillclimb-review evidence"
                    )
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


def _results_diff(args: argparse.Namespace) -> int:
    from evalarc.results_diff import BLOCKING, load_results, render_html, render_markdown

    try:
        from evalarc import evidence

        if args.require_generalization and not args.held_out:
            raise ValueError("--require-generalization requires --held-out")
        runs = [
            load_results(path, args.format, args.threshold)
            for path in (args.baseline, args.current)
        ]
        split = None
        if args.held_out:
            from evalarc.generalization import load_split

            split = load_split(args.held_out)
        params = {
            "format": args.format,
            "threshold": args.threshold,
            "leak_min_chars": args.leak_min_chars,
            "require_generalization": args.require_generalization,
            "max_cost_ratio": args.max_cost_ratio,
            "cost_metric": args.cost_metric,
        }
        result = evidence.compute_diff(runs, params, split, args.harness)
        if args.output:
            with new_run(args.output) as output:
                inputs = []
                for label, path, run in zip(
                    ("baseline", "current"), (args.baseline, args.current), runs
                ):
                    name = f"{label}{path.suffix or '.json'}"
                    evidence.copy_input(path, run["source"]["sha256"], output / name)
                    inputs.append({"file": name})
                if split is not None:
                    evidence.copy_input(
                        args.held_out, split["source"]["sha256"], output / "split.json"
                    )
                harness = evidence.copy_harness(args.harness, output) if args.harness else []
                evidence.write_params(
                    output,
                    "diff",
                    {
                        **params,
                        "inputs": inputs,
                        "split": "split.json" if split is not None else None,
                        "harness": harness,
                    },
                )
                write_json(output / "diff.json", result)
                (output / "summary.md").write_text(render_markdown(result), encoding="utf-8")
                render_html(result, output / "index.html")
        if args.markdown:
            with args.markdown.open("a", encoding="utf-8") as summary:
                summary.write(render_markdown(result))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as error:
        print(f"evalarc: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        before, after = result["baseline"]["headline"], result["current"]["headline"]
        headline = (
            f"{before['name']}: {before['value']} -> {after['value']} | "
            if before and after and before["value"] is not None and after["value"] is not None
            else ""
        )
        counts = result["counts"]
        print(
            f"{headline}Checks that lost passes or coverage: {result['blocking_changes']} | "
            f"Improved: {counts['improved']} | Unchanged: {counts['unchanged']}"
        )
        within = result.get("blocking_changes_within_sampling_noise") or 0
        if within:
            print(
                f"  {within} within sampling noise (record more attempts to separate from "
                "repeat-sampling variation; the gate still fails)"
            )
        for row in result["changes"]:
            if row["kind"] in BLOCKING:
                print(f"  {row['kind']}: {row['case_id']} / {row['check']}")
        if result["current_incomplete"]:
            print("The current run is incomplete; the gate fails.")
        if result.get("baseline_incomplete"):
            status = result["baseline"]["identity"].get("status")
            print(
                f"The baseline run is incomplete (status {status}); "
                f"{counts.get('added', 0)} check(s) appear only in the current run and were "
                "not compared. Rerun the baseline to completion; the gate fails."
            )
        review = result.get("generalization")
        if review:
            parts = review["partitions"]
            delta = lambda row: "n/a" if row["delta"] is None else f"{row['delta'] * 100:+.1f} pp"  # noqa: E731
            print(
                f"Held-out split: {review['state']} | tuning {delta(parts['tuning'])} "
                f"({parts['tuning']['cases']} cases) | held out {delta(parts['held_out'])} "
                f"({parts['held_out']['cases']} cases)"
            )
        leakage = result.get("leakage")
        if leakage:
            print(
                f"Harness leakage: {len(leakage['hits'])} hit(s) in "
                f"{len(leakage['files_scanned'])} file(s)"
                + (f", {leakage['held_out_hits']} from held-out cases" if review else "")
            )
            for hit in leakage["hits"][:10]:
                print(f"  {hit['file']}:{hit['line'] or '?'} {hit['role']} of {hit['case_id']}")
        if result.get("generalization_required") and not result["generalization_passed"]:
            print("Generalization is required and was not shown; the gate fails.")
        gate = result.get("cost_gate")
        if gate:
            print(
                f"Cost gate ({gate['metric']}): current/baseline {gate['ratio']:.3f}, "
                f"limit {gate['max_ratio']:g} — {'pass' if gate['passed'] else 'fail'}"
            )
        if args.output:
            print(f"Report: {args.output / 'index.html'}")
    from evalarc.evidence import diff_passed

    return 0 if diff_passed(result) else 1


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

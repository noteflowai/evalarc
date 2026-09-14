"""Declarative experiment suites with explicit, task-specific acceptance gates."""

from __future__ import annotations

import hashlib
import re
import tempfile
import time
import tomllib
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from evalarc import __version__
from evalarc.artifacts import check_output_location, new_run
from evalarc.evaluate import write_json
from evalarc.events import EventCallback, EventLog, emit
from evalarc.junit import render_junit
from evalarc.records import numeric
from evalarc.repetition import repeat
from evalarc.report import render_evaluation, render_repetition, render_suite
from evalarc.runner import Runtime, snapshot
from evalarc.tasks import get_task

MAX_CONFIG_BYTES = 1_048_576


def _keys(value: object, allowed: set[str], required: set[str], label: str) -> dict:
    if not isinstance(value, dict) or not required <= value.keys() or value.keys() - allowed:
        raise ValueError(
            f"{label}: required keys {sorted(required)}; allowed keys {sorted(allowed)}"
        )
    return value


@dataclass(frozen=True)
class Gate:
    min_mean_score: float = 1.0
    min_resolution_rate: float = 1.0
    required_dimensions: tuple[str, ...] = ()


@dataclass(frozen=True)
class SuiteJob:
    id: str
    task: str
    candidate: Path
    seeds: tuple[int, ...]
    attempts: int
    runtime: Runtime
    gate: Gate
    cases_per_attempt: int

    def describe(self) -> dict:
        return {
            "id": self.id,
            "task": self.task,
            "candidate": str(self.candidate),
            "seeds": list(self.seeds),
            "attempts": self.attempts,
            "cases_per_attempt": self.cases_per_attempt,
            "runtime": {
                key: getattr(self.runtime, key)
                for key in ("backend", "image", "timeout", "case_timeout", "output_limit")
            },
            "gate": asdict(self.gate),
        }


@dataclass(frozen=True)
class SuitePlan:
    name: str
    source: Path
    content: bytes
    jobs: tuple[SuiteJob, ...]

    def describe(self) -> dict:
        return {
            "schema_version": "evalarc.suite-plan.v1",
            "name": self.name,
            "manifest_sha256": hashlib.sha256(self.content).hexdigest(),
            "jobs": [job.describe() for job in self.jobs],
            "planned_attempts": sum(job.attempts for job in self.jobs),
            "planned_case_executions": sum(
                job.attempts * job.cases_per_attempt for job in self.jobs
            ),
        }


def load_suite(path: Path) -> SuitePlan:
    """Parse bounded configuration without starting candidates or contacting Docker."""
    source = path.resolve()
    with source.open("rb") as stream:
        content = stream.read(MAX_CONFIG_BYTES + 1)
    if len(content) > MAX_CONFIG_BYTES:
        raise ValueError("suite configuration exceeds 1 MiB")
    data = _keys(
        tomllib.loads(content.decode("utf-8")),
        {"schema_version", "name", "jobs"},
        {"schema_version", "name", "jobs"},
        "suite",
    )
    if data["schema_version"] != "evalarc.suite-config.v1":
        raise ValueError("expected suite schema_version = 'evalarc.suite-config.v1'")
    name = data["name"]
    if not isinstance(name, str) or not name.strip() or len(name) > 120 or not name.isprintable():
        raise ValueError("suite name must contain 1–120 printable characters")
    if not isinstance(data["jobs"], list) or not 1 <= len(data["jobs"]) <= 100:
        raise ValueError("suite must contain 1–100 jobs")
    jobs = []
    seen = set()
    for index, raw in enumerate(data["jobs"]):
        label = f"job {index + 1}"
        raw = _keys(
            raw,
            {"id", "task", "candidate", "seeds", "attempts", "runtime", "gate"},
            {"id", "task", "candidate"},
            label,
        )
        identity = raw["id"]
        if (
            not isinstance(identity, str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", identity)
            or identity in seen
        ):
            raise ValueError(
                f"{label}: id must be a unique lowercase slug of at most 64 characters"
            )
        seen.add(identity)
        label = f"{label} ({identity})"
        if not isinstance(raw["task"], str):
            raise ValueError(f"{label}: task must be a string")
        task = get_task(raw["task"])
        candidate = raw["candidate"]
        if (
            not isinstance(candidate, str)
            or not candidate
            or "\0" in candidate
            or len(candidate) > 4096
        ):
            raise ValueError(
                f"{label}: candidate must be a nonempty path of at most 4096 characters"
            )
        candidate = (source.parent / candidate).resolve()
        if not candidate.is_dir():
            raise ValueError(f"{label}: candidate directory does not exist: {candidate}")
        seeds = raw.get("seeds", [17, 41, 97])
        if (
            not isinstance(seeds, list)
            or not 1 <= len(seeds) <= 100
            or any(type(seed) is not int for seed in seeds)
            or len(set(seeds)) != len(seeds)
        ):
            raise ValueError(f"{label}: seeds must be 1–100 unique integers")
        attempts = raw.get("attempts", 1)
        if type(attempts) is not int or not 1 <= attempts <= 100:
            raise ValueError(f"{label}: attempts must be an integer from 1 to 100")
        options = _keys(
            raw.get("runtime", {}),
            {"backend", "image", "timeout", "case_timeout", "output_limit"},
            set(),
            f"{label} runtime",
        )
        runtime = Runtime(**options)
        if runtime.backend not in ("docker", "local"):
            raise ValueError(f"{label}: backend must be docker or local")
        if (
            not isinstance(runtime.image, str)
            or not runtime.image
            or len(runtime.image) > 512
            or not runtime.image.isprintable()
        ):
            raise ValueError(f"{label}: image must be a nonempty printable string")
        # Validate limits without resolving an image or executing a configured command.
        try:
            replace(runtime, backend="local").prepare()
        except ValueError as error:
            raise ValueError(f"{label}: {error}") from error
        acceptance = _keys(
            raw.get("gate", {}),
            {"min_mean_score", "min_resolution_rate", "required_dimensions"},
            set(),
            f"{label} gate",
        )
        for key in ("min_mean_score", "min_resolution_rate"):
            value = acceptance.get(key, 1.0)
            if not numeric(value) or not 0 <= value <= 1:
                raise ValueError(f"{label}: {key} must be finite and between 0 and 1")
        dimensions = acceptance.get("required_dimensions", [])
        if (
            not isinstance(dimensions, list)
            or any(not isinstance(item, str) or item not in task.dimensions for item in dimensions)
            or len(set(dimensions)) != len(dimensions)
        ):
            raise ValueError(
                f"{label}: required_dimensions must name unique dimensions of {task.id}"
            )
        gate = Gate(
            acceptance.get("min_mean_score", 1.0),
            acceptance.get("min_resolution_rate", 1.0),
            tuple(dimensions),
        )
        jobs.append(
            SuiteJob(
                identity,
                task.id,
                candidate,
                tuple(seeds),
                attempts,
                runtime,
                gate,
                sum(len(task.generate_cases(seed)) for seed in seeds),
            )
        )
    plan = SuitePlan(name, source, content, tuple(jobs))
    description = plan.describe()
    if description["planned_attempts"] > 1000 or description["planned_case_executions"] > 100_000:
        raise ValueError("suite exceeds 1000 attempts or 100000 planned case executions")
    return plan


def assess_gate(summary: dict, gate: Gate) -> dict:
    """Apply acceptance rules to a repetition result produced by this runner."""
    if not summary["valid"] or not summary["complete"]:
        return {
            "accepted": False,
            "valid": False,
            "checks": [],
            "reasons": [
                f"Invalid or incomplete evaluation: {summary['completed_attempts']}/"
                f"{summary['requested_attempts']} attempts completed, "
                f"{summary['invalid_attempts']} invalid."
            ],
        }
    checks = []
    for name, minimum, observed in (
        ("mean_score", gate.min_mean_score, summary["mean_score"]),
        ("resolution_rate", gate.min_resolution_rate, summary["assessed_resolution_rate"]),
    ):
        checks.append(
            {
                "name": name,
                "minimum": minimum,
                "observed": observed,
                "passed": observed is not None and observed >= minimum,
            }
        )
    for dimension in gate.required_dimensions:
        observations = [row for row in summary["cases"] if dimension in row["checks"]]
        violations = [
            {"seed": row["seed"], "case_id": row["case_id"], **row["checks"][dimension]}
            for row in observations
            if row["checks"][dimension]["passed"] != summary["completed_attempts"]
        ]
        checks.append(
            {
                "name": f"required_dimension:{dimension}",
                "passed": bool(observations) and not violations,
                "violations": violations,
            }
        )
    return {
        "accepted": all(check["passed"] for check in checks),
        "valid": True,
        "checks": checks,
        "reasons": [
            f"{check['name']}: observed {check['observed']}, requires >= {check['minimum']}"
            if "minimum" in check
            else f"{check['name']}: not every applicable check passed"
            for check in checks
            if not check["passed"]
        ],
    }


def run_suite(
    plan: SuitePlan,
    destination: Path,
    *,
    trust_local: bool = False,
    docker_command: str = "docker",
    progress: bool = False,
    on_event: EventCallback | None = None,
) -> dict:
    """Run sequentially; freeze and preflight every candidate before the first attempt."""
    if any(job.runtime.backend == "local" for job in plan.jobs) and not trust_local:
        raise ValueError("suite contains local execution; add --trust-local for trusted code")
    for job in plan.jobs:
        check_output_location(job.candidate, destination)
    started = time.monotonic()
    description = plan.describe()
    with (
        new_run(destination) as output,
        EventLog(output / "events.jsonl", stream=progress) as events,
        tempfile.TemporaryDirectory(prefix="evalarc-suite-") as temporary,
    ):

        def notify(event: dict) -> None:
            events(event)
            if on_event is not None:
                on_event(event.copy())

        emit(notify, "suite_preflight_started", jobs=len(plan.jobs))
        frozen = {}
        prepared = []
        for job in plan.jobs:
            if job.candidate not in frozen:
                workspace = Path(temporary) / f"candidate-{len(frozen):04d}"
                fingerprint = snapshot(job.candidate, workspace)
                frozen[job.candidate] = (workspace, fingerprint)
            workspace, fingerprint = frozen[job.candidate]
            runtime = replace(job.runtime, docker_command=docker_command)
            runtime = runtime.for_candidate(workspace, get_task(job.task).default_command)
            runtime.prepare()
            prepared.append((job, workspace, runtime, fingerprint))
            emit(notify, "job_prepared", job=job.id, candidate_sha256=fingerprint)
        (output / "suite.toml").write_bytes(plan.content)
        write_json(output / "plan.json", description)
        emit(
            notify,
            "suite_started",
            jobs=len(plan.jobs),
            **{key: description[key] for key in ("planned_attempts", "planned_case_executions")},
        )
        rows = []
        for job, workspace, runtime, fingerprint in prepared:
            job_started = time.monotonic()
            directory = output / "jobs" / job.id
            directory.mkdir(parents=True)
            emit(notify, "job_started", job=job.id, task=job.task)
            with EventLog(directory / "events.jsonl") as job_events:

                def observe(event: dict) -> None:
                    job_events(event)
                    notify({**event, "job": job.id})

                def save(index: int, evaluation: dict) -> None:
                    attempt = directory / "attempts" / f"{index:04d}"
                    write_json(attempt / "evaluation.json", evaluation)
                    render_evaluation(evaluation, attempt / "index.html")

                repetition = repeat(
                    workspace,
                    runtime,
                    list(job.seeds),
                    job.attempts,
                    job.task,
                    on_event=observe,
                    on_attempt=save,
                )
            if repetition["candidate_sha256"] != fingerprint:
                raise ValueError(f"frozen candidate changed during suite execution: {job.id}")
            write_json(directory / "repetition.json", repetition)
            render_repetition(repetition, directory / "index.html")
            decision = assess_gate(repetition, job.gate)
            row = {
                "id": job.id,
                "task": repetition["task"],
                "candidate_sha256": fingerprint,
                "grader_sha256": repetition["grader_sha256"],
                "cases_sha256": repetition["cases_sha256"],
                "runtime": repetition["runtime"],
                "seeds": list(job.seeds),
                "gate": asdict(job.gate),
                "decision": decision,
                "status": (
                    "environment_error"
                    if not decision["valid"]
                    else ("passed" if decision["accepted"] else "failed")
                ),
                "fully_resolved": repetition["all_attempts_resolved"],
                "observed": {
                    key: repetition[key]
                    for key in (
                        "requested_attempts",
                        "completed_attempts",
                        "assessed_attempts",
                        "invalid_attempts",
                        "resolved_attempts",
                        "mean_score",
                        "assessed_resolution_rate",
                        "variable_cases",
                        "variable_checks",
                    )
                },
                "duration_seconds": round(time.monotonic() - job_started, 6),
            }
            rows.append(row)
            emit(
                notify,
                "job_completed",
                job=job.id,
                status=row["status"],
                accepted=decision["accepted"],
                fully_resolved=row["fully_resolved"],
            )
        valid = all(row["decision"]["valid"] for row in rows)
        accepted = valid and all(row["decision"]["accepted"] for row in rows)
        report = {
            "schema_version": "evalarc.suite.v1",
            "evalarc_version": __version__,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "name": plan.name,
            "manifest_sha256": description["manifest_sha256"],
            "valid": valid,
            "accepted": accepted,
            "status": "environment_error" if not valid else ("passed" if accepted else "failed"),
            "total_jobs": len(rows),
            "accepted_jobs": sum(row["decision"]["accepted"] for row in rows),
            "invalid_jobs": sum(not row["decision"]["valid"] for row in rows),
            "fully_resolved_jobs": sum(row["fully_resolved"] for row in rows),
            "duration_seconds": round(time.monotonic() - started, 6),
            "jobs": rows,
            "interpretation": (
                "Acceptance follows each job's declared gate. No score is averaged across jobs "
                "or domains. Gate acceptance does not imply full task resolution. "
                "Repeated observations use fixed public cases and are descriptive only."
            ),
        }
        write_json(output / "suite.json", report)
        render_suite(report, output / "index.html")
        render_junit(report, output / "junit.xml")
        emit(
            notify,
            "suite_completed",
            status=report["status"],
            accepted_jobs=report["accepted_jobs"],
            invalid_jobs=report["invalid_jobs"],
        )
    return report

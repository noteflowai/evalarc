"""Run native Harbor controls and independently execute the collected programs.

Run with the Harbor 0.23.0 environment's Python and this checkout on PYTHONPATH.
The output is an immutable experiment directory. Every attempted job is retained.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from importlib.metadata import version
from pathlib import Path

from export_harbor_task import export
from harbor_control_agent import CONTROLS

from evalarc.evaluate import write_json
from evalarc.interop import import_harbor
from evalarc.runner import Runtime

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(output: Path, harbor: str, docker: str) -> dict:
    if version("harbor") != "0.23.0":
        raise ValueError("this experiment requires Harbor 0.23.0")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    task = output / "task"
    export(task, partial_credit=True)
    harness = output / "harness"
    harness.mkdir()
    for name in ("record_harbor_controls.py", "harbor_control_agent.py", "export_harbor_task.py"):
        shutil.copyfile(ROOT / "scripts" / name, harness / name)
    plan = {
        "schema": "evalarc.harbor-controls-plan.v1",
        "harbor_version": version("harbor"),
        "task_version": "0.2.0",
        "controls": list(CONTROLS),
        "evaluation_seeds": [41, 97],
        "minimum_independent_score": 1.0,
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
        ),
        "harness_files": {p.name: digest(p) for p in harness.iterdir()},
        "scope": (
            "One task, three scripted controls, no model inference. "
            "Answer-file reward and independently executed program correctness are separate. "
            "All attempted jobs, including errors, must be retained."
        ),
    }
    write_json(output / "plan.json", plan)
    runtime = Runtime(docker_command=docker)
    runtime.prepare()
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(ROOT / "src")))
    rows = []
    for control in CONTROLS:
        command = [
            harbor,
            "run",
            "--path",
            str(task),
            "--agent",
            "scripts.harbor_control_agent:ControlAgent",
            "--agent-kwarg",
            f"control={control}",
            "--env",
            "docker",
            "--jobs-dir",
            str(output / "jobs"),
            "--job-name",
            control,
            "--n-concurrent",
            "1",
            "--max-retries",
            "0",
        ]
        row = {"control": control, "command": command}
        with (output / f"{control}.log").open("w") as log:
            process = subprocess.run(
                command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT
            )
        row["return_code"] = process.returncode
        rows.append(row)
        write_json(output / "progress.json", {"runs": rows})
        results = list((output / "jobs" / control).glob("*/result.json"))
        if process.returncode or len(results) != 1:
            raise RuntimeError(f"{control}: Harbor failed; retained job and process log")
        trial = results[0].parent
        raw = json.loads(results[0].read_text())
        if raw["exception_info"] or raw["finished_at"] is None:
            raise RuntimeError(f"{control}: Harbor has no completed valid trial")
        from harbor.models.trajectories.trajectory import Trajectory

        trajectory = trial / "agent/trajectory.json"
        Trajectory.model_validate_json(trajectory.read_text())
        candidate = trial / "artifacts/candidate"
        report = import_harbor(
            trial, candidate, output / "imports" / control, runtime, plan["evaluation_seeds"]
        )
        observed = json.loads(
            json.loads(trajectory.read_text())["steps"][-1]["observation"]["results"][0]["content"]
        )
        produced = json.loads(observed["stdout"])
        if produced["main.py"] != digest(candidate / "main.py") or produced[
            "answers.jsonl"
        ] != digest(trial / "artifacts/answers.jsonl"):
            raise ValueError("collected artifacts differ from the container's final file hashes")
        row["candidate_file_sha256"] = digest(candidate / "main.py")
        row.update(
            trial_path=trial.relative_to(output).as_posix(),
            import_path=f"imports/{control}",
            answers_sha256=digest(trial / "artifacts/answers.jsonl"),
            source_result_sha256=digest(results[0]),
            source_trajectory_sha256=digest(trajectory),
            full_upstream_schema_validated=True,
            upstream_rewards=report["upstream"]["rewards"],
            independent=report["independent"],
            acceptance=report["acceptance"],
        )
        write_json(output / "progress.json", {"runs": rows})
        print(
            json.dumps(
                {
                    "control": control,
                    "reward": row["upstream_rewards"],
                    "score": row["independent"]["score"],
                    "accepted": row["acceptance"]["accepted"],
                }
            ),
            flush=True,
        )
    summary = {"schema": "evalarc.harbor-controls.v1", "plan": "plan.json", "runs": rows}
    write_json(output / "summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--harbor-command", default="harbor")
    parser.add_argument("--docker-command", default="docker")
    args = parser.parse_args()
    record(args.output, args.harbor_command, args.docker_command)

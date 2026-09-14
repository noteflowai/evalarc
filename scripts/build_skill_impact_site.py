"""Build a public, source-checked viewer of all three completed model pilots."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

PROFILES = [
    (
        "skill-impact-matched",
        "Task contract in a file",
        "Original two-tool discovery; contract read from TASK.md. Original Docker response clock.",
    ),
    (
        "skill-impact-contract-inline",
        "Contract in the initial context",
        "Authoritative contract inline; Docker readiness separated from candidate response time.",
    ),
    (
        "skill-impact-catalog-fallback",
        "Bounded discovery fallback",
        "Inline contract, clearer description vocabulary, "
        "and a list_skills fallback after search misses.",
    ),
]
MODEL_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("expected a bounded regular evidence file")
    raw = path.read_bytes()
    document = json.loads(raw)
    json.dumps(document, allow_nan=False)
    return document, raw


def build(source, output):
    output.mkdir(parents=True, exist_ok=False)
    profiles = []
    for identity, title, description in PROFILES:
        root = source / identity
        experiment, experiment_raw = read(root / "experiment.json")
        validation, validation_raw = read(root / "atif-validation.json")
        checks = validation.get("trials")
        if checks is None:
            checks = [
                {
                    "trial": Path(row["path"]).parent.name,
                    "atif_sha256": row["sha256"],
                    "valid": row["validated"],
                }
                for row in validation["records"]
            ]
        valid_atif = {row["trial"]: row for row in checks}
        rows = []
        for trial_path in sorted(root.glob("*/trial.json")):
            trial, raw = read(trial_path)
            if (
                trial.get("schema_version") != "evalarc.skill-impact-trial.v1"
                or trial.get("task") != "robot-evidence-review"
                or trial.get("model", {}).get("revision") != MODEL_REVISION
                or trial.get("condition") not in ("none", "direct", "mcp")
                or trial.get("model_seed") not in (17, 41, 97)
            ):
                raise ValueError("unexpected pilot task, model, condition or seed")
            evaluation, evaluation_raw = read(trial_path.with_name("evaluation.json"))
            measured = {key: evaluation[key] for key in ("valid", "resolved", "score", "status")}
            if measured != trial["independent_evaluation"]:
                raise ValueError("trial summary differs from independent evaluation")
            trajectory, atif_raw = read(trial_path.with_name("trajectory.atif.json"))
            check = valid_atif[trial_path.parent.name]
            if check["atif_sha256"] != sha(atif_raw) or check["valid"] is not True:
                raise ValueError("ATIF file differs from its upstream schema validation")
            if trajectory.get("schema_version") != "ATIF-v1.8":
                raise ValueError("unexpected upstream trajectory format")
            for name, expected in trial["candidate_files"].items():
                path = trial_path.parent / "candidate" / name
                if not path.resolve().is_relative_to((trial_path.parent / "candidate").resolve()):
                    raise ValueError("candidate source path escapes its directory")
                if sha(path.read_bytes()) != expected:
                    raise ValueError("recorded candidate bytes changed")
            destination = output / "trials" / identity / trial_path.parent.name
            destination.mkdir(parents=True)
            for name, content in (
                ("trial.json", raw),
                ("evaluation.json", evaluation_raw),
                ("trajectory.atif.json", atif_raw),
            ):
                (destination / name).write_bytes(content)
            candidate = trial_path.parent / "candidate/main.py"
            if candidate.is_file():
                shutil.copyfile(candidate, destination / "main.py")
            events = trial["tool_events"]
            rows.append(
                {
                    "id": trial_path.parent.name,
                    "condition": trial["condition"],
                    "seed": trial["model_seed"],
                    "workflow_status": trial["status"],
                    "evaluation": measured,
                    "model": trial["model"],
                    "skill_loads": sum(event["name"] == "open_skill" for event in events),
                    "skill_pins": trial["skill_pins"],
                    "steps": len(trial["turns"]),
                    "completion_tokens": trial["completion_tokens"],
                    "generation_and_tool_seconds": trial["elapsed_seconds"],
                    "trial_sha256": sha(raw),
                    "atif_sha256": sha(atif_raw),
                    "prompt_sha256": trial["prompt_sha256"],
                    "tools_sha256": trial["tools_sha256"],
                    "candidate_sha256": trial["candidate_files"].get("main.py"),
                    "error": trial["error"],
                    "tool_sequence": [event["name"] for event in events],
                    "path": destination.relative_to(output).as_posix(),
                }
            )
        if len(rows) != 9 or {(row["condition"], row["seed"]) for row in rows} != {
            (condition, seed) for condition in ("none", "direct", "mcp") for seed in (17, 41, 97)
        }:
            raise ValueError("retain all nine preselected trials in each profile")
        for seed in (17, 41, 97):
            direct = next(
                row for row in rows if row["seed"] == seed and row["condition"] == "direct"
            )
            mcp = next(row for row in rows if row["seed"] == seed and row["condition"] == "mcp")
            if any(
                direct[key] != mcp[key] for key in ("prompt_sha256", "tools_sha256", "skill_pins")
            ):
                raise ValueError("direct and MCP did not receive the same controlled instructions")
        profile_dir = output / "profiles" / identity
        profile_dir.mkdir(parents=True)
        (profile_dir / "experiment.json").write_bytes(experiment_raw)
        (profile_dir / "atif-validation.json").write_bytes(validation_raw)
        profiles.append(
            {
                "id": identity,
                "title": title,
                "description": description,
                "experiment": experiment,
                "trials": rows,
            }
        )
    lab = {
        "schema": "evalarc.skill-impact-site.v1",
        "profiles": profiles,
        "scope": (
            "Three successive public engineering profiles, nine trials each. Prompts and "
            "discovery differ across profiles. Do not pool them into a single efficacy estimate "
            "or attribute differences solely to one change. No held-out benchmark claim."
        ),
    }
    (output / "lab.json").write_text(json.dumps(lab, indent=2) + "\n")
    templates = Path(__file__).parents[1] / "site/labs"
    for target, name in (("index.html", "skill-impact.html"), ("app.js", "skill-impact.js")):
        (output / target).write_bytes((templates / name).read_bytes())
    (output / "METHODS.md").write_text(METHODS)
    data = Path(__file__).parents[1] / "src/evalarc/assets"
    for name in ("ROBOT_DATA_LICENSE.txt", "ROBOT_DATA_NOTICE.md", "ROBOT_TASK.md"):
        shutil.copyfile(data / name, output / name)
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "schema": "evalarc.skill-impact-site.v1",
                "files": {
                    path.relative_to(output).as_posix(): {
                        "sha256": sha(path.read_bytes()),
                        "bytes": path.stat().st_size,
                    }
                    for path in sorted(output.rglob("*"))
                    if path.is_file()
                },
            },
            indent=2,
        )
        + "\n"
    )
    return {
        "profiles": len(profiles),
        "trials": sum(len(profile["trials"]) for profile in profiles),
    }


METHODS = """# Tool delivery and independently measured task outcomes

All 27 trials use Qwen/Qwen3-8B revision
`b968826d9c46dd6066d109eabc6255188de91218` on an NVIDIA L40S, bfloat16,
with thinking disabled. Each profile schedules seeds 17, 41, 97 for no skill,
direct loading and real MCP stdio delivery. Route order rotates across seeds.
Budgets: 12 model turns, 4,096 generated tokens per turn, 600 seconds before
independent grading, sampling temperature 0.2. Grading uses seeds 41 and 97;
the public development example uses seed 17.

The task interprets real, attributed Robot Reel CUDA recordings in several
coordinate/clock conventions, including missing observations. Derived variants
are not new physical simulations. Numerical answers are checked against the
original world-coordinate records. The reference implementation and six fault
controls pass Python and JavaScript Docker audits.

Candidate code runs in non-networked, non-root Docker containers with no host
mounts or credentials. A receipt identifies returned SKILL.md and bundle bytes;
it does not prove the model followed the advice. Direct and MCP receive identical
model-facing fields, prompts, tool definitions and skill pins within a profile.
“Direct” is this file adapter, not a native named coding agent's skill loader.

The three profiles are engineering iterations:

1. The authoritative contract is in a file. Models sometimes inspect guidance
   before reading the task and produce the wrong output contract.
2. The contract is in the initial context. Some models consume the turn budget
   on lexical searches that miss the original skill description.
3. A clearer description and bounded catalog fallback resolve that discovery
   failure. All direct/MCP trials load the skill, but none passes the task.

No skill-effect gain is claimed. Extra context, search/tool choices and model
behavior are confounded in this small public task. The profiles must not be pooled
as one benchmark; each uses only three seeds per condition.

The first profile's candidates were regraded after separating Docker readiness
from candidate response timing: all nine scores stayed unchanged. Original and
regrade reports remain in the complete experiment archive. An earlier interrupted
development run exposed a workspace-path mismatch; it is documented separately
and is not counted among these three completed profiles.

Every trial retains the candidate, evaluation and ATIF trajectory. ATIF-v1.8
exports were checked with the real Harbor 0.23.0 `Trajectory` schema validator.
EvalArc's lightweight importer checks a narrower bounded envelope and tool-call
linkage; it must not be mistaken for full upstream schema validation.

Workflow completion and task acceptance are separate. A valid evaluation means
the evaluation produced a usable result; it does not mean the candidate passed.
Fractional task scores describe only this task's checks. Wall times are recording
metadata, not a throughput comparison, and hardware cost is not estimated.

The repository scripts preserve the executed harness bytes for the final profile.
The public traces contain only generated development-session data, never the
operator's personal agent history. Recorder and bridge code retain their project
licenses; Robot Reel recording data retains Apache-2.0 attribution included here.
"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(build(arguments.source, arguments.output)))

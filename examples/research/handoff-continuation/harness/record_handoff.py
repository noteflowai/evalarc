"""Resume one public Qwen3-8B attempt with Qwen3-4B, with/without Funes recall.

The retrieval is performed by the actual Funes CLI before this script. Both
conditions start from identical candidate bytes and the same authoritative task.
No private agent history or named commercial-agent integration is implied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import record_skill_impact as protocol

from evalarc.evaluate import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--recall", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:47865")
    parser.add_argument("--docker-command", default="docker")
    args = parser.parse_args()
    prior = json.loads((args.prior / "trial.json").read_text())
    if (
        prior.get("schema_version") != "evalarc.skill-impact-trial.v1"
        or prior.get("split") != "public-development"
        or prior.get("model", {}).get("model") != "Qwen/Qwen3-8B"
    ):
        parser.error("expected the explicitly selected public Qwen3-8B pilot attempt")
    starter = (args.prior / "candidate/main.py").read_text()
    recall = args.recall.read_text()
    if len(starter.encode()) > 65536 or len(recall.encode()) > 16384:
        parser.error("starter or retrieved context exceeds the pilot bound")
    if hashlib.sha256(starter.encode()).hexdigest() != prior.get("candidate_files", {}).get(
        "main.py"
    ):
        parser.error("prior candidate bytes differ from the recorded trial")
    model = protocol.fetch(args.endpoint + "/health")
    if model.get("model") != "Qwen/Qwen3-4B":
        parser.error("this preselected continuation experiment requires Qwen/Qwen3-4B")
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "prior-main.py").write_text(starter)
    (args.output / "recall.txt").write_text(recall)
    snapshot = args.output / "harness"
    snapshot.mkdir()
    for path in (
        Path(__file__),
        Path(protocol.__file__),
        Path(__file__).parents[1] / "src/evalarc/robot_task.py",
        Path(__file__).parents[1] / "src/evalarc/agent_sandbox.py",
        Path(__file__).parents[1] / "src/evalarc/runner.py",
    ):
        (snapshot / path.name).write_bytes(path.read_bytes())
    write_json(
        args.output / "experiment.json",
        {
            "schema": "evalarc.handoff-experiment.v1",
            "prior_trial_sha256": hashlib.sha256(
                (args.prior / "trial.json").read_bytes()
            ).hexdigest(),
            "prior_model": prior["model"],
            "continuation_model": model,
            "prior_independent_evaluation": prior["independent_evaluation"],
            "starter_sha256": hashlib.sha256(starter.encode()).hexdigest(),
            "retrieved_context_sha256": hashlib.sha256(recall.encode()).hexdigest(),
            "seeds": [17, 41, 97],
            "conditions": ["no-memory", "funes-recall"],
            "max_steps": 12,
            "max_new_tokens_per_step": 4096,
            "wall_seconds": 600,
            "temperature": 0.2,
            "harness_files": {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in snapshot.iterdir()
            },
            "scope": (
                "One public task, two open model sizes, fixed retrieved context. "
                "Separate sessions of the local tool harness, not a native Claude/Codex test. "
                "Recall is retrieved before inference, not autonomously requested by the model."
            ),
        },
    )
    original_asset = protocol.asset
    # Explicit task setup overrides in this process only. The shared module file
    # is unchanged, and the exact starter/context/harness bytes are snapshotted.
    protocol.asset = lambda name: starter if name == "robot_starter.py" else original_asset(name)
    args.evaluation_seeds = [41, 97]
    args.task_context = "inline"
    args.max_steps, args.max_new_tokens, args.wall_seconds, args.temperature = 12, 4096, 600, 0.2
    rows = []
    root = args.output
    for offset, seed in enumerate((17, 41, 97)):
        order = ["no-memory", "funes-recall"] if offset % 2 == 0 else ["funes-recall", "no-memory"]
        for condition in order:
            args.output = root / condition
            args.output.mkdir(exist_ok=True)
            protocol.USER = (
                "Continue the previous agent's implementation in main.py. It has not fully "
                "passed independent checks. Inspect it against the authoritative contract, "
                "fix remaining errors and check the supplied example before finishing. "
                "Do not assume the earlier agent's work or recalled notes are correct."
            )
            if condition == "funes-recall":
                protocol.USER += "\n\nRetrieved public prior-session context from Funes:\n" + recall
            row = protocol.trial(args, "none", seed, len(rows) + 1)
            trial_path = args.output / row["path"] / "trial.json"
            record = json.loads(trial_path.read_text())
            record["handoff"] = {
                "condition": condition,
                "prior_model": prior["model"],
                "starter_sha256": hashlib.sha256(starter.encode()).hexdigest(),
                "retrieved_context_sha256": (
                    hashlib.sha256(recall.encode()).hexdigest()
                    if condition == "funes-recall"
                    else None
                ),
            }
            write_json(trial_path, record)
            row["handoff_condition"] = condition
            row["path"] = f"{condition}/{row['path']}"
            rows.append(row)
            write_json(root / "summary.json", {"trials": rows})
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()

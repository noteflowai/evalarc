"""Run relevant and token-matched neutral skills through the same real MCP route."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import record_skill_impact as protocol

from evalarc.evaluate import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--bridge", type=Path, required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:47865")
    parser.add_argument("--docker-command", default="docker")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    match = json.loads((args.prepared / "match.json").read_text())
    if match["schema"] != "evalarc.skill-context-match.v1":
        parser.error("expected a prepared token-matched skill pair")
    model = protocol.fetch(args.endpoint + "/health")
    if (model["model"], model["revision"]) != (
        match["tokenizer_model"],
        match["tokenizer_revision"],
    ):
        parser.error("model differs from the prepared tokenizer identity")
    args.output.mkdir(parents=True, exist_ok=False)
    root = args.output
    shutil.copytree(args.prepared, root / "preparation")
    libraries = args.bridge.resolve().parents[2] / "lib"
    shutil.copytree(libraries, root / "skill-library")
    snapshot = root / "harness"
    snapshot.mkdir()
    for path in (
        Path(__file__),
        Path(protocol.__file__),
        Path(__file__).with_name("local_model_server.py"),
        args.bridge,
        Path(__file__).parents[1] / "src/evalarc/robot_task.py",
        Path(__file__).parents[1] / "src/evalarc/runner.py",
        Path(__file__).parents[1] / "src/evalarc/agent_sandbox.py",
    ):
        shutil.copyfile(path, snapshot / path.name)
    # Validate the real MCP result against preparation before scheduling inference.
    for condition in ("relevant", "neutral"):
        pool = root / "preparation/pools" / condition
        bridge = protocol.Bridge(args.bridge, "mcp", pool)
        try:
            response = bridge.call("open_skill", {"name": "robot-recording-review"})
            if response.get("view") != match[condition]["view"]:
                raise ValueError("real MCP payload differs from the token-matched preparation")
            write_json(root / f"preflight-{condition}.json", response)
        finally:
            bridge.close()
    args.evaluation_seeds, args.task_context = [41, 97], "inline"
    args.max_steps, args.max_new_tokens, args.wall_seconds, args.temperature = 12, 4096, 600, 0.2
    plan = {
        "schema": "evalarc.skill-context-experiment.v1",
        "model": model,
        "conditions": ["relevant", "neutral"],
        "route": "mcp",
        "model_seeds": [17, 41, 97],
        "evaluation_seeds": args.evaluation_seeds,
        "task_context": args.task_context,
        "max_steps": args.max_steps,
        "max_new_tokens_per_step": args.max_new_tokens,
        "wall_seconds": args.wall_seconds,
        "temperature": args.temperature,
        "model_visible_open_skill_tokens": match["model_visible_open_skill_tokens"],
        "match_sha256": hashlib.sha256((root / "preparation/match.json").read_bytes()).hexdigest(),
        "harness_files": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in snapshot.iterdir()
        },
        "results_policy": "All six scheduled trials retained, including errors; no retries.",
        "scope": (
            "One public development task; a new paired context-content control. "
            "Same model, catalog metadata, tools, task and budgets. First skill-load "
            "payloads have identical token lengths; all later token usage is measured. "
            "No independent-author or held-out evaluation, and no pooled efficacy claim."
        ),
    }
    write_json(root / "experiment.json", plan)
    rows = []
    for index, seed in enumerate(plan["model_seeds"]):
        order = ["relevant", "neutral"] if index % 2 == 0 else ["neutral", "relevant"]
        for condition in order:
            args.output = root / condition
            args.output.mkdir(exist_ok=True)
            args.pool = root / "preparation/pools" / condition
            row = protocol.trial(args, "mcp", seed, len(rows) + 1)
            path = args.output / row["path"] / "trial.json"
            trial = json.loads(path.read_text())
            trial["context_control"] = {
                "condition": condition,
                "match_sha256": plan["match_sha256"],
                "tokens_per_open": plan["model_visible_open_skill_tokens"],
            }
            # Every delivered view must remain the reviewed, token-matched payload.
            for event in trial["tool_events"]:
                if (
                    event["name"] == "open_skill"
                    and "content" in event["result"]
                    and event["result"] != match[condition]["view"]
                ):
                    raise ValueError("observed skill delivery differs from the preselected control")
            write_json(path, trial)
            row["context_condition"] = condition
            row["path"] = f"{condition}/{row['path']}"
            rows.append(row)
            write_json(
                root / "summary.json",
                {"schema": "evalarc.skill-context-results.v1", "trials": rows},
            )
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()

"""Bind an actual prior MCP skill load to one explicitly selected Funes source."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from prepare_funes_source import digest, prepare

from evalarc.evaluate import write_json


def prior_skill(trial: dict, skill: Path) -> tuple[dict, int]:
    """Require recorded MCP delivery of the supplied original SKILL.md bytes."""
    pins = trial.get("skill_pins")
    if not isinstance(pins, dict) or set(pins) != {"robot-recording-review"}:
        raise ValueError("select a prior trial with exactly the reviewed robot skill")
    pin = pins["robot-recording-review"]
    if pin.get("sha256") != digest(skill):
        raise ValueError("original SKILL.md differs from the prior session pin")
    for index, event in enumerate(trial.get("tool_events", [])):
        view = event.get("result", {})
        receipt = event.get("receipt") or {}
        raw = receipt.get("raw") or {}
        opened = raw.get("structuredContent") or {}
        if (
            event.get("name") == "open_skill"
            and event.get("arguments") == {"name": "robot-recording-review"}
            and receipt.get("route") == "mcp"
            and not raw.get("isError")
            and view.get("name") == "robot-recording-review"
            and view.get("sha256") == pin["sha256"]
            and view.get("bundle_sha256") == pin["bundle_sha256"]
            and isinstance(view.get("content"), str)
            and bool(view["content"])
            and opened.get("sha256") == pin["sha256"]
            and opened.get("bundle", {}).get("sha256") == pin["bundle_sha256"]
            and opened.get("content") == view["content"]
        ):
            return pins, index
    raise ValueError("prior session has no successful matching MCP skill delivery")


def prepare_skill_source(
    prior: Path,
    exported: Path,
    memory: Path,
    binary: Path,
    expected_binary: str,
    skill: Path,
    skill_license: Path,
    output: Path,
) -> dict:
    trial = json.loads((prior / "trial.json").read_text())
    pins, index = prior_skill(trial, skill)
    source = prepare(prior, exported, memory, binary, expected_binary, output)
    pool = output / "skills/robot-recording-review"
    pool.mkdir(parents=True)
    shutil.copyfile(skill, pool / "SKILL.md")
    shutil.copyfile(skill_license, output / "SKILL-LICENSE.txt")
    write_json(output / "skill-pins.json", pins)
    write_json(output / "prior-skill-load.json", trial["tool_events"][index])
    source["skill_handoff"] = {
        "schema": "noteflow.skill-handoff.v1",
        "name": "robot-recording-review",
        "pool_directory": "skills",
        "pins_path": "skill-pins.json",
        "prior_event_index": index,
        "prior_trial_sha256": digest(output / "prior/trial.json"),
        "original_load_path": "prior-skill-load.json",
        "delivery": "Prior agent-requested MCP load; successor workflow-selected MCP preload.",
    }
    source["files"] = {
        path.relative_to(output).as_posix(): digest(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path != output / "source.json"
    }
    write_json(output / "source.json", source)
    return source


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--memory", type=Path, required=True)
    parser.add_argument("--funes", type=Path, required=True)
    parser.add_argument("--expected-funes-sha256", required=True)
    parser.add_argument("--skill", type=Path, required=True)
    parser.add_argument("--skill-license", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record = prepare_skill_source(
        args.prior,
        args.export,
        args.memory,
        args.funes,
        args.expected_funes_sha256,
        args.skill,
        args.skill_license,
        args.output,
    )
    print(json.dumps({"session_id": record["session_id"], "files": len(record["files"])}))

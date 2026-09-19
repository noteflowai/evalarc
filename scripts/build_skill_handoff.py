"""Verify and publish the fixed-skill, actual-MCP cross-model handoff records."""

from __future__ import annotations

import argparse
import html
import json
import shutil
from datetime import datetime
from pathlib import Path

from scripts import build_handoff_mcp as handoff
from scripts.build_context_controls import digest, read, seal, verify_inventory

SCHEMA = "evalarc.skill-handoff-bundle.v1"
RECORDS_SCHEMA = "evalarc.skill-handoff-records.v1"
ARCHIVE = "skill-handoff.zip"
RECORDS = "records-manifest.json"


def inventory(root: Path) -> dict:
    excluded = {root / name for name in (ARCHIVE, RECORDS, "manifest.json")}
    return {
        path.relative_to(root).as_posix(): {"sha256": digest(path), "bytes": path.stat().st_size}
        for path in sorted(root.rglob("*"))
        if path.is_file() and path not in excluded
    }


def checked_skills(root: Path, rows: list[dict]) -> dict:
    plan = read(root / "experiment.json")
    source = read(root / "source/source.json")
    prior = read(root / "source/prior/trial.json")
    original = read(root / "source/prior-skill-load.json")
    pins = read(root / "source/skill-pins.json")
    skill = root / "source/skills/robot-recording-review/SKILL.md"
    if set(pins) != {"robot-recording-review"}:
        raise ValueError("unexpected prior skill pool")
    pin = pins["robot-recording-review"]
    if (
        plan["skill_handoff"]["expected_pins"] != pins
        or plan["skill_handoff"]["source"] != source["skill_handoff"]
        or plan["skill_handoff"]["delivery_actor"] != "harness"
        or plan["skill_handoff"]["preload_outside_interactive_budget"] is not True
        or prior["skill_pins"] != pins
        or original != prior["tool_events"][source["skill_handoff"]["prior_event_index"]]
        or original["name"] != "open_skill"
        or original["receipt"]["route"] != "mcp"
        or original["receipt"]["raw"].get("isError")
        or digest(skill) != pin["sha256"]
        or original["result"]["sha256"] != pin["sha256"]
        or original["result"]["bundle_sha256"] != pin["bundle_sha256"]
        or source["skill_handoff"]["prior_trial_sha256"] != digest(root / "source/prior/trial.json")
    ):
        raise ValueError("prior load, original skill or declared pins differ")
    expected_bundle = {
        "schema": "skills-anywhere-bundle-1",
        "sha256": pin["bundle_sha256"],
        "total_bytes": skill.stat().st_size,
        "files": [{"path": "SKILL.md", "bytes": skill.stat().st_size, "sha256": pin["sha256"]}],
    }
    if original["receipt"]["raw"]["structuredContent"]["bundle"] != expected_bundle:
        raise ValueError("original load is not the one-file skill bundle")
    loaded, prompts = 0, set()
    for row in rows:
        trial = read(root / row["path"] / "trial.json")
        delivery = trial["handoff"]["skill_delivery"]
        expected_path = f"preloads/{row['handoff_condition']}-{row['seed']}.json"
        if delivery["path"] != expected_path:
            raise ValueError("skill receipt path differs from the scheduled attempt")
        receipt = read(root / expected_path)
        if (
            digest(root / expected_path) != delivery["sha256"]
            or receipt["actor"] != "harness"
            or delivery["actor"] != "harness"
            or receipt["expected_pins"] != pins
            or trial["skill_pins"] != pins
            or row["condition"] != "mcp-preloaded"
            or receipt["status"] != row["skill_delivery_status"]
            or receipt["status"] != delivery["status"]
            or receipt["elapsed_seconds"] != delivery["elapsed_seconds"]
            or delivery["outside_interactive_budget"] is not True
        ):
            raise ValueError("workflow skill receipt differs from the attempt")
        if receipt["status"] == "loaded":
            reply = receipt["reply"]
            raw = reply["receipt"]["raw"]
            opened = raw["structuredContent"]
            if (
                receipt["ready"]["pins"] != pins
                or reply["view"] != original["result"]
                or reply["receipt"]["route"] != "mcp"
                or reply["receipt"]["tool"] != "open_skill"
                or reply["receipt"]["arguments"] != {"name": "robot-recording-review"}
                or reply["receipt"]["protocol_era"] not in ("modern", "legacy")
                or raw.get("isError")
                or opened["bundle"] != expected_bundle
                or opened["sha256"] != pin["sha256"]
                or opened["content"] != original["result"]["content"]
                or json.dumps(reply["view"], ensure_ascii=False)
                not in trial["messages"][1]["content"]
            ):
                raise ValueError("successor did not receive the prior skill over recorded MCP")
            prompts.add(trial["prompt_sha256"])
            loaded += 1
        elif receipt["status"] != "unavailable" or not receipt.get("error"):
            raise ValueError("unavailable preload has no recorded failure")
    if len(prompts) > 1:
        raise ValueError("successful fixed-skill deliveries received different initial prompts")
    frozen = handoff.candidate_files(root / "frozen")
    if frozen != plan["frozen_files"] or not all(read(root / "frozen-inputs-check.json").values()):
        raise ValueError("frozen production files differ or drift was recorded")
    completion = read(root / "completion.json")
    if completion["scheduled"] != 6 or completion["recorded"] != len(rows):
        raise ValueError("cohort did not retain every scheduled attempt")
    return {"loaded": loaded, "pins": pins, "frozen_files": len(frozen)}


def checked_validation(root: Path) -> dict:
    plan = read(root / "experiment.json")
    source = read(root / "source/source.json")
    folder = root / "validation/baseline"
    record = read(folder / "record.json")
    evaluation = read(folder / "evaluation.json")
    handoff.verify_evaluation(folder / "evaluation.json")
    handoff.check_candidate(folder / "candidate", evaluation)
    if (
        record["kind"] != "scripted-post-run-baseline-without-agent-generation"
        or record["program_sha256"] != plan["starter_sha256"]
        or record["program_sha256"] != digest(folder / "candidate/main.py")
        or record["candidate_sha256"] != evaluation["candidate_sha256"]
        or record["evaluation_sha256"] != digest(folder / "evaluation.json")
        or record["evaluation"]
        != {key: evaluation[key] for key in ("valid", "resolved", "score", "status")}
    ):
        raise ValueError("post-run baseline differs from its executed program")
    controls = read(root / "validation/mcp-controls.json")
    mutation = controls["source_mutation_control"]
    if (
        controls["kind"] != "native-MCP-controls-without-agent-generation"
        or controls["ready"]["source"] != source
        or controls["ready"]["manifest_sha256"] != plan["source_manifest_sha256"]
        or [call["view"]["status"] for call in controls["calls"]]
        != ["retrieved", "retrieved", "not_found", "request_rejected"]
        or mutation["removed"] != "prior-session.parquet"
        or mutation["ready"]["source"] != source
        or mutation["view"]["status"] != "source_unavailable"
    ):
        raise ValueError("native source controls differ")
    for call in controls["calls"]:
        handoff.check_retrieval(
            {**call, "result": call["view"]},
            {
                "bridge_ready": controls["ready"],
                "source_manifest_sha256": plan["source_manifest_sha256"],
            },
            source,
        )
    drift = read(root / "validation/preflight-pin-drift.json")
    if (
        drift["exit_code"] == 0
        or drift["ready_or_skill_delivered"] is not False
        or drift["expected_sha256"] != source["files"]["skills/robot-recording-review/SKILL.md"]
        or drift["observed_sha256"] == drift["expected_sha256"]
        or "changed since the handoff" not in drift["stderr"]
        or drift["stdout"]
    ):
        raise ValueError("changed-version control did not reject the later skill")
    expected = {
        name.removeprefix("evalarc/src/evalarc/"): sha
        for name, sha in plan["frozen_files"].items()
        if name.startswith("evalarc/src/evalarc/")
    }
    during = read(root / "validation/runtime-package-during.json")
    after = read(root / "validation/runtime-package-after.json")
    for observation in (during, after):
        if (
            observation["repository_dirty"]
            or observation["repository_commit"] != during["repository_commit"]
            or observation["package_path"] != during["package_path"]
            or {item["path"]: item["sha256"] for item in observation["files"]} != expected
            or not all(item["matches_frozen_bytes"] for item in observation["files"])
        ):
            raise ValueError("actual editable package differs from the frozen source")
    frozen_at = datetime.fromisoformat(plan["frozen_at"])
    completed_at = datetime.fromisoformat(read(root / "completion.json")["completed_at"])
    if not (
        frozen_at
        < datetime.fromisoformat(during["observed_at"])
        < completed_at
        <= datetime.fromisoformat(after["observed_at"])
        <= datetime.fromisoformat(record["started_at"])
    ):
        raise ValueError("runtime observations or post-run baseline have inconsistent timing")
    return record["evaluation"]


def render(root: Path, rows: list[dict]) -> str:
    skills = checked_skills(root, rows)
    return (
        handoff.render(
            root,
            rows,
            baseline=checked_validation(root),
            template_path=Path(__file__).with_name("skill_handoff_page.html"),
        )
        .replace("__LOADED__", str(skills["loaded"]))
        .replace("__SKILL_SHA__", html.escape(skills["pins"]["robot-recording-review"]["sha256"]))
    )


def verify_bundle(root: Path) -> dict:
    if (root / "manifest.json").exists():
        count = verify_inventory(root, SCHEMA, ARCHIVE)
    else:
        if (root / ARCHIVE).exists():
            raise ValueError("hosted archive has no outer manifest")
        count = sum(path.is_file() for path in root.rglob("*"))
    record = read(root / RECORDS)
    if (
        record["schema"] != RECORDS_SCHEMA
        or record["files"] != inventory(root)
        or any(path.is_symlink() for path in root.rglob("*"))
    ):
        raise ValueError("skill-handoff record inventory differs")
    rows = handoff.checked_rows(root, skill_handoff=True)
    skills = checked_skills(root, rows)
    if (root / "index.html").read_text() != render(root, rows):
        raise ValueError("skill-handoff page differs from the verified records")
    return {"trials": len(rows), "files": count, **skills}


def build(source: Path, validation: Path, output: Path) -> dict:
    rows = handoff.checked_rows(source, skill_handoff=True)
    checked_skills(source, rows)
    output.mkdir(parents=True, exist_ok=False)
    handoff.copy_public(source, output)
    handoff.copy_public(validation, output / "validation")
    (output / "index.html").write_text(render(output, rows))
    project = Path(__file__).resolve().parents[1]
    shutil.copyfile(project / "LICENSE", output / "LICENSE")
    changed = sum(row["operations"]["program_changed"] is True for row in rows)
    resolved = sum(bool(row["evaluation"] and row["evaluation"]["resolved"]) for row in rows)
    scores = ", ".join(
        sorted(
            {
                f"{row['evaluation']['score']:.1%}"
                if row["evaluation"] and row["evaluation"]["valid"]
                else "unassessed"
                for row in rows
            }
        )
    )
    for language in ("md", "zh-CN.md"):
        text = Path(__file__).with_name("skill_handoff_README." + language).read_text()
        text = text.replace(
            "__PROGRAM_SUMMARY_EN__",
            f"Programs changed: {changed}/{len(rows)}. Full task acceptance: "
            f"{resolved}/{len(rows)}. Recorded scores: {scores}.",
        ).replace(
            "__PROGRAM_SUMMARY_ZH__",
            f"程序修改数为 {changed}/{len(rows)}，完整任务验收为 "
            f"{resolved}/{len(rows)}；记录评分为 {scores}。",
        )
        (output / ("README." + language)).write_text(text)
    (output / RECORDS).write_text(
        json.dumps({"schema": RECORDS_SCHEMA, "files": inventory(output)}, indent=2) + "\n"
    )
    seal(output, SCHEMA, ARCHIVE)
    return verify_bundle(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--validation", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            verify_bundle(args.output)
            if args.verify
            else build(args.source, args.validation, args.output)
        )
    )

"""Build and verify an offline review of the fixed independent-source SWE cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

SCHEMA = "evalarc.independent-swe-evidence.v1"
ARCHIVE = "independent-swe.zip"
ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def grade_view(report, spec):
    """Keep upstream infrastructure flags separate from assessed test failures."""
    result = {
        "upstream_resolved": report.get("resolved"),
        "infra_failure": report.get("infra_failure"),
        "infra_failure_reason": report.get("infra_failure_reason"),
        "disposition": "unavailable",
        "f2p_passed": None,
        "f2p_total": len(spec["FAIL_TO_PASS"]),
        "p2p_passed": None,
        "p2p_total": len(spec["PASS_TO_PASS"]),
        "aggregate_pass_fraction": None,
        "aggregate_95_accepted": None,
    }
    if report.get("infra_failure") is not False:
        return result
    observed = report.get("tests_status", {})
    for group, field in (("FAIL_TO_PASS", "f2p"), ("PASS_TO_PASS", "p2p")):
        values = observed.get(group, {})
        passed, failed = values.get("success"), values.get("failure")
        if not isinstance(passed, list) or not isinstance(failed, list):
            return result
        if (
            len(passed) != len(set(passed))
            or len(failed) != len(set(failed))
            or set(passed) & set(failed)
            or set(passed) | set(failed) != set(spec[group])
        ):
            return result
        result[field + "_passed"] = len(passed)
    total = result["f2p_total"] + result["p2p_total"]
    if not total or type(report.get("resolved")) is not bool:
        return result
    result["aggregate_pass_fraction"] = (result["f2p_passed"] + result["p2p_passed"]) / total
    result["aggregate_95_accepted"] = result["aggregate_pass_fraction"] >= 0.95
    result["disposition"] = "accepted" if report["resolved"] else "not_accepted"
    return result


def projections(load, names):
    config = load("protocol/cohort.json")
    if config["analysis_rules"]["aggregate_pass_fraction"] != 0.95:
        raise ValueError("rule threshold differs from the pre-run declaration")
    planned = []
    order = ("none", "direct", "mcp", "unrelated")
    for task_index, instance in enumerate(config["images"]):
        for seed_index, seed in enumerate((17, 41, 97)):
            for offset in range(4):
                planned.append(
                    {
                        "index": len(planned),
                        "instance_id": instance,
                        "condition": order[(task_index + seed_index + offset) % 4],
                        "seed": seed,
                    }
                )
    if config["schedule"] != planned or len(planned) != 36:
        raise ValueError("cohort does not preserve the fixed 36-attempt schedule")
    status = load("cohort/status.json")
    if (
        status["status"] != "completed"
        or status["completed_attempts"] != 36
        or status["config_sha256"] != digest(names["protocol/cohort.json"])
    ):
        raise ValueError("cohort is incomplete or uses another configuration")
    conditions = load("protocol/conditions/conditions.json")
    identity = load("protocol/cohort-final-identity.json")
    if (
        identity["model_manifest_sha256"] != config["model_identity"]["model_files_manifest_sha256"]
        or identity["frozen_files_verified"] != len(config["frozen_files"])
        or identity["frozen_links_verified"] != len(config["frozen_links"])
        or load("cohort/health-before.json") != config["model_identity"]
        or load("cohort/health-after.json") != config["model_identity"]
    ):
        raise ValueError("final model or runtime identity was not verified")
    selection = load("protocol/selection.json")
    source_rows = {row["instance_id"]: row for row in selection["selected_metadata"]}
    rows, traces, controls = [], {}, []
    for item in planned:
        name = f"{item['index']:02}-{item['instance_id']}-{item['condition']}-{item['seed']}"
        prefix = "attempts/" + name
        record = load(prefix + "/record.json")
        if any(record.get(key) != value for key, value in item.items()):
            raise ValueError("attempt differs from its fixed slot")
        if record["status"] != "completed":
            raise ValueError("this completed cohort contains an unfinished attempt")
        if record["source_row_sha256"] != source_rows[item["instance_id"]]["source_row_sha256"]:
            raise ValueError("attempt uses another source row")
        candidate = prefix + (
            "/unavailable-candidate.patch"
            if record["candidate_missing"]
            else "/generation/final/candidate.patch"
        )
        patch_hash = digest(names[candidate])
        if not record["candidate_missing"]:
            snapshot = load(prefix + "/generation/final/snapshot.json")
            if {key: value for key, value in snapshot.items() if key != "entries"} != record[
                "snapshot"
            ] or snapshot["patch_sha256"] != patch_hash:
                raise ValueError("final snapshot differs from the submitted patch")
        native = load(prefix + "/native-grade.json")
        grade_record = load(prefix + "/grade/record.json")
        report = load(prefix + "/grade/report.json")
        runtime = load(prefix + "/grade/runtime.json")
        if (
            record["candidate_patch_sha256"] != patch_hash
            or grade_record["candidate_patch_sha256"] != patch_hash
            or native["record"] != grade_record
            or native["report"] != report
            or grade_record["status"] != "reported"
            or native["exit_code"] != 0
            or runtime["source_instance_sha256"] != record["source_row_sha256"]
            or grade_record["image"] != config["images"][item["instance_id"]]["image"]
        ):
            raise ValueError("candidate, source or native report binding differs")
        spec = load(prefix + "/grade/test-spec.json")
        interpretation = grade_view(report[item["instance_id"]], spec)
        if record["native_resolved"] != interpretation["upstream_resolved"]:
            raise ValueError("top-level result differs from the raw native report")
        messages = load(prefix + "/prefix.json")
        if item["condition"] != "none":
            preload = load(prefix + "/workflow-preload.json")
            kind = "unrelated" if item["condition"] == "unrelated" else "related"
            route = "direct" if item["condition"] == "direct" else "mcp"
            if (
                preload["reply"].get("error")
                or preload["reply"]["view"] != conditions[kind]
                or preload["reply"]["receipt"]["route"] != route
                or messages[-1]["role"] != "tool"
                or json.loads(messages[-1]["content"]) != conditions[kind]
            ):
                raise ValueError("actual preload differs from the declared workflow")
        elif len(messages) != 2 or prefix + "/workflow-preload.json" in names:
            raise ValueError("no-skill condition acquired an extra preload")
        events = load(prefix + "/events.json")
        responses = [
            load(name)
            for name in sorted(names)
            if name.startswith(prefix + "/response-") and name.endswith(".json")
        ]
        usage = {
            key: sum(response[key] for response in responses)
            for key in ("prompt_tokens", "completion_tokens", "wall_seconds")
        }
        for response in responses:
            if any(response.get(key) != value for key, value in config["model_identity"].items()):
                raise ValueError("a response came from a different model runtime")
        if usage != record["usage"]:
            raise ValueError("usage summary differs from the recorded responses")
        if record["usage_complete"] and len(responses) != record["model_requests"]:
            raise ValueError("complete usage is missing a model response")
        row = {
            "id": name,
            **item,
            "repository": source_rows[item["instance_id"]]["repo"],
            "source_row_sha256": record["source_row_sha256"],
            "status": record["status"],
            "generation_end": record["generation_end"],
            "model_requests": record["model_requests"],
            "recorded_model_responses": len(responses),
            "usage_complete": record["usage_complete"],
            "prompt_tokens_recorded": usage["prompt_tokens"],
            "completion_tokens_recorded": usage["completion_tokens"],
            "model_seconds_recorded": usage["wall_seconds"],
            "changed_files": len(record["snapshot"]["changed_paths"]),
            "changed_paths": record["snapshot"]["changed_paths"],
            "patch_sha256": patch_hash,
            "patch_bytes": len(names[candidate]),
            "protocol_errors": sum("protocol_error" in event for event in events),
            "nonzero_command_exits": sum(
                event.get("result", {}).get("exit_code", 0) != 0 for event in events
            ),
            "errors": record["errors"],
            "trace_path": f"traces/{item['index']:02}.json",
            "archive_prefix": prefix,
            **interpretation,
        }
        rows.append(row)
        traces[row["trace_path"]] = {
            "row": row,
            "initial_messages": messages,
            "interactions": load(prefix + "/interactions.json"),
            "events": events,
            "responses": responses,
            "native_report": report,
            "native_record": grade_record,
            "candidate_patch": names[candidate].decode("utf-8"),
        }
    for instance in config["images"]:
        for mode in ("original-defect", "original-fix"):
            prefix = f"controls/{instance}--{mode}"
            record = load(prefix + "/record.json")
            report = load(prefix + "/report.json")[instance]
            spec = load(prefix + "/test-spec.json")
            interpretation = grade_view(report, spec)
            if (
                record["status"] != "reported"
                or record["mode"] != mode
                or record["image"] != config["images"][instance]["image"]
                or interpretation["disposition"]
                != ("accepted" if mode == "original-fix" else "not_accepted")
            ):
                raise ValueError("upstream control is missing or differs from its declared result")
            controls.append({"instance_id": instance, "mode": mode, **interpretation})
    groups = []
    for condition in ("none", "direct", "mcp", "unrelated"):
        selected = [row for row in rows if row["condition"] == condition]
        groups.append(
            {
                "condition": condition,
                "attempts": len(selected),
                **dict(Counter(row["disposition"] for row in selected)),
                "changed_candidates": sum(bool(row["changed_files"]) for row in selected),
                "usage_incomplete": sum(not row["usage_complete"] for row in selected),
            }
        )
    summary = {
        "schema": SCHEMA,
        "attempts": len(rows),
        "source_tasks": len(config["images"]),
        "dispositions": dict(Counter(row["disposition"] for row in rows)),
        "changed_candidates": sum(bool(row["changed_files"]) for row in rows),
        "usage_incomplete": sum(not row["usage_complete"] for row in rows),
        "model_requests": sum(row["model_requests"] for row in rows),
        "groups": groups,
        "model": config["model_identity"],
        "recorder_commit": config["recorder_commit"],
        "config_sha256": digest(names["protocol/cohort.json"]),
        "controls": controls,
    }
    return rows, traces, summary


def page(summary, rows, traces):
    template = (ROOT / "scripts/swe_report_index.html").read_text()
    for token, value in (("__SUMMARY__", summary), ("__ROWS__", rows), ("__TRACES__", traces)):
        template = template.replace(
            token, json.dumps(value, ensure_ascii=True).replace("<", "\\u003c")
        )
    return template


def verify(folder):
    folder = Path(folder)
    manifest = read(folder / "manifest.json")
    if manifest["schema"] != SCHEMA:
        raise ValueError("unexpected independent SWE bundle schema")
    actual_files = {
        p.relative_to(folder).as_posix()
        for p in folder.rglob("*")
        if p.is_file() and p != folder / "manifest.json"
    }
    if actual_files != set(manifest["files"]):
        raise ValueError("bundle file inventory differs")
    for name, expected in manifest["files"].items():
        data = (folder / name).read_bytes()
        if digest(data) != expected["sha256"] or len(data) != expected["bytes"]:
            raise ValueError("bundle file bytes differ: " + name)
    with zipfile.ZipFile(folder / ARCHIVE) as archive:
        infos = archive.infolist()
        if (
            len({p.filename for p in infos}) != len(infos)
            or sum(p.file_size for p in infos) > 200e6
        ):
            raise ValueError("duplicate or excessive archive members")
        for item in infos:
            path = PurePosixPath(item.filename)
            if path.is_absolute() or ".." in path.parts or item.is_dir():
                raise ValueError("unsafe archive member")
        files = {item.filename: archive.read(item) for item in infos}
    inventory = json.loads(files.pop("records-manifest.json"))
    if set(inventory) != set(files):
        raise ValueError("raw archive inventory differs")
    for name, value in files.items():
        if inventory[name] != {"sha256": digest(value), "bytes": len(value)}:
            raise ValueError("raw archive member differs")
    rows, traces, summary = projections(lambda name: json.loads(files[name]), files)
    if read(folder / "summary.json") != summary or read(folder / "rows.json") != rows:
        raise ValueError("public results differ from their raw records")
    if [json.loads(line) for line in (folder / "data.jsonl").read_text().splitlines()] != rows:
        raise ValueError("dataset rows differ from their raw records")
    for name, value in traces.items():
        if read(folder / name) != value:
            raise ValueError("public trace differs from its raw records")
    return summary


def build(source, output):
    source, output = Path(source), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    files = {}

    def add(path, name):
        if name in files:
            raise ValueError("duplicate source member")
        files[name] = Path(path).read_bytes()

    for path in sorted((source / "model-cohort").rglob("*")):
        if not path.is_file() or path.suffix == ".tar" or path.name == "index":
            continue
        relative = path.relative_to(source / "model-cohort")
        prefix = "attempts/" if len(relative.parts) > 1 else "cohort/"
        add(path, prefix + relative.as_posix())
    for path in sorted((source / "selected-controls-2").rglob("*")):
        if path.is_file():
            add(path, "controls/" + path.relative_to(source / "selected-controls-2").as_posix())
    for name in (
        "selection.json",
        "selection-protocol.json",
        "INDEPENDENT-SWE-PLAN.zh-CN.md",
        "SELECTION-PROVENANCE-CORRECTION.zh-CN.md",
        "FIXED-RUNTIME-PROTOCOL.zh-CN.md",
        "initial-prompt-token-check.json",
        "runtime-freeze-receipt.json",
        "cohort-final-identity.json",
        "native-controls-completion.json",
    ):
        add(source / name, "protocol/" + name)
    for name in ("cohort.json", "dependencies.json", "snapshot-bridge-preflight.json"):
        add(source / "frozen-runtime" / name, "protocol/" + name)
    for path in sorted((source / "frozen-runtime/conditions").rglob("*")):
        if path.is_file():
            add(
                path,
                "protocol/conditions/"
                + path.relative_to(source / "frozen-runtime/conditions").as_posix(),
            )
    for directory in ("evalarc", "provider/lib", "provider/src"):
        for path in sorted((source / "frozen-runtime" / directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                add(path, "frozen/" + path.relative_to(source / "frozen-runtime").as_posix())
    for name in ("package.json", "pnpm-lock.yaml", "LICENSE", "examples/skill-impact/bridge.mjs"):
        add(source / "frozen-runtime/provider" / name, "frozen/provider/" + name)
    for instance in read(source / "frozen-runtime/cohort.json")["images"]:
        add(
            source / "prepared-sources" / instance / "source.json",
            f"protocol/prepared-sources/{instance}.json",
        )
    for name in ("astropy-license.rst", "pytest-license", "sympy-license", "verified-card.md"):
        add(source / "primary-sources" / name, "source-attribution/" + name)
    add(source.parent / "behavior-audit-20260919/model-files.json", "protocol/model-files.json")
    rows, traces, summary = projections(lambda name: json.loads(files[name]), files)
    write(output / "rows.json", rows)
    write(output / "summary.json", summary)
    (output / "data.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows)
    )
    for name, value in traces.items():
        write(output / name, value)
    (output / "index.html").write_text(page(summary, rows, {}))
    files["review/index.html"] = page(summary, rows, traces).encode()
    files["review/data.jsonl"] = (output / "data.jsonl").read_bytes()
    for name in ("README.md", "README.zh-CN.md"):
        template = ROOT / "scripts" / ("swe_report_" + name)
        shutil.copyfile(template, output / name)
        files["review/" + name] = template.read_bytes()
    inventory = {
        name: {"sha256": digest(value), "bytes": len(value)}
        for name, value in sorted(files.items())
    }
    files["records-manifest.json"] = json.dumps(inventory, indent=2).encode() + b"\n"
    with zipfile.ZipFile(output / ARCHIVE, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in sorted(files.items()):
            entry = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, value)
    write(
        output / "manifest.json",
        {
            "schema": SCHEMA,
            "files": {
                path.relative_to(output).as_posix(): {
                    "sha256": digest(path.read_bytes()),
                    "bytes": path.stat().st_size,
                }
                for path in sorted(output.rglob("*"))
                if path.is_file()
            },
        },
    )
    return verify(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if not args.verify and args.source is None:
        parser.error("--source is required when building")
    print(
        json.dumps(
            verify(args.output) if args.verify else build(args.source, args.output), indent=2
        )
    )

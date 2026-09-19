"""Build a source-checked report of actual Funes MCP continuations."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import tempfile
from pathlib import Path

from evalarc.runner import snapshot
from evalarc.verify import verify as verify_evaluation
from scripts.build_context_controls import SECRET, digest, read, seal, verify_inventory
from scripts.handoff_metrics import operation_metrics

SCHEMA = "evalarc.funes-mcp-handoff-bundle.v1"
ARCHIVE = "funes-handoff.zip"
CONDITIONS = ("no-memory", "funes-mcp")
MEMORY_TOOLS = ("recall_prior_session", "read_prior_turns")
RECORDS_MANIFEST = "records-manifest.json"


def record_inventory(root: Path) -> dict:
    excluded = {root / name for name in (RECORDS_MANIFEST, "manifest.json", ARCHIVE)}
    return {
        p.relative_to(root).as_posix(): {"sha256": digest(p), "bytes": p.stat().st_size}
        for p in sorted(root.rglob("*"))
        if p.is_file() and p not in excluded
    }


def verify_record_inventory(root: Path) -> int:
    manifest = read(root / RECORDS_MANIFEST)
    if manifest["schema"] != "evalarc.funes-mcp-handoff-records.v1":
        raise ValueError("unexpected handoff record inventory")
    if any(p.is_symlink() for p in root.rglob("*")):
        raise ValueError("handoff records contain a symlink")
    if manifest["files"] != record_inventory(root):
        raise ValueError("handoff record inventory or bytes differ")
    return len(manifest["files"])


def candidate_files(folder: Path) -> dict:
    return {
        path.relative_to(folder).as_posix(): digest(path)
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def check_candidate(folder: Path, evaluation: dict) -> None:
    with tempfile.TemporaryDirectory(prefix="evalarc-handoff-review-") as temporary:
        identity = snapshot(folder, Path(temporary) / "candidate")
    if identity != evaluation["candidate_sha256"]:
        raise ValueError("evaluated candidate differs from the delivered program")


def check_retrieval(event: dict, handoff: dict, source: dict) -> None:
    view, receipt = event["result"], event.get("receipt")
    if view.get("status") not in ("retrieved", "not_found"):
        return
    expected_source = {
        "session_id": source["session_id"],
        "manifest_sha256": handoff["source_manifest_sha256"],
        "prior_trial_sha256": source["files"]["prior/trial.json"],
        "prior_program_sha256": source["files"]["prior/main.py"],
        "parquet_sha256": source["files"]["prior-session.parquet"],
    }
    ready = handoff["bridge_ready"]
    if (
        not receipt
        or receipt.get("route") != "funes-mcp"
        or receipt.get("bounded_mcp") != ready["bounded_mcp"]
        or receipt.get("bounded_request")
        != {"name": event["name"], "arguments": event["arguments"]}
        or receipt.get("protocol_era") != ready["protocol_era"]
        or receipt.get("bounded_is_error") is not False
        or view.get("source") != expected_source
    ):
        raise ValueError("retrieval is not bound to both recorded MCP connections")
    args = event["arguments"]
    if event["name"] == "recall_prior_session":
        request = {
            "name": "recall",
            "arguments": {"query": args["query"], "k": 4, "neighbors": 0, "half_life": 0},
        }
    else:
        request = {
            "name": "get",
            "arguments": {
                "session_id": source["session_id"],
                "from": args["from"],
                "to": args["to"],
            },
        }
        if not 0 <= args["from"] <= args["to"] <= 1_000_000 or args["to"] - args["from"] > 7:
            raise ValueError("read exceeded its declared turn range")
    if receipt.get("request") != request:
        raise ValueError("native request differs from the agent's scoped request")
    raw = receipt.get("raw", {})
    content = raw.get("content", [])
    if not content or any(part.get("type") != "text" for part in content):
        raise ValueError("retrieved content has no native text record")
    text = "\n".join(part["text"] for part in content)
    if (
        raw.get("isError")
        or re.match(r"^(get|recall) error:", text.strip(), re.I)
        or len(text.encode()) > 32768
        or view.get("text") != text
    ):
        raise ValueError("model-facing retrieval differs from valid bounded native text")
    if view["status"] == "retrieved":
        if request["name"] == "recall":
            references = re.findall(r"^\s*→ get (\S+) --from (\d+) --to (\d+)", text, re.M)
            expected = [
                {"session_id": session, "from": int(start), "to": int(end)}
                for session, start, end in references
            ]
            if (
                not references
                or any(session != source["session_id"] for session, _, _ in references)
                or view.get("passages") != expected
            ):
                raise ValueError("recall cites a different source")
        else:
            turns = re.findall(r"^\[[^\n]+\] \S+ seq(\d+) turn=(\S+)", text, re.M)
            if (
                not turns
                or any(not turn.startswith(source["session_id"] + "-") for _, turn in turns)
                or view.get("turns") != [int(sequence) for sequence, _ in turns]
            ):
                raise ValueError("read cites a different source")


def checked_rows(root: Path) -> list[dict]:
    plan = read(root / "experiment.json")
    rows = read(root / "summary.json")["trials"]
    source = read(root / "source/source.json")
    prior = read(root / "source/prior/trial.json")
    expected_order = [
        ("no-memory", 17),
        ("funes-mcp", 17),
        ("funes-mcp", 41),
        ("no-memory", 41),
        ("no-memory", 97),
        ("funes-mcp", 97),
    ]
    if (
        plan["schema"] != "evalarc.funes-mcp-handoff.v1"
        or plan["conditions"] != list(CONDITIONS)
        or plan["model"]["model"] != "Qwen/Qwen3-4B"
        or plan["model"]["revision"] != "1cfa9a7208912126459214e8b04321603b3df60c"
        or plan["model"]["device"] != "NVIDIA L40S"
        or plan["evaluation_seeds"] != [41, 97]
        or (
            plan["max_steps"],
            plan["max_new_tokens_per_step"],
            plan["wall_seconds"],
            plan["temperature"],
        )
        != (12, 4096, 600, 0.2)
        or plan["tools"]["funes-mcp"][:4] != plan["tools"]["no-memory"]
        or [tool["function"]["name"] for tool in plan["tools"]["no-memory"]]
        != ["read_file", "write_file", "run_command", "finish"]
        or [tool["function"]["name"] for tool in plan["tools"]["funes-mcp"][4:]]
        != list(MEMORY_TOOLS)
        or [(row["handoff_condition"], row["seed"]) for row in rows] != expected_order
        or len({row["path"] for row in rows}) != 6
        or digest(root / "source/source.json") != plan["source_manifest_sha256"]
        or source["session_id"] != plan["source_session_id"]
        or source["split"] != "public-development"
        or plan["starter_sha256"] != digest(root / "source/prior/main.py")
        or source["prior_model"] != plan["prior_model"]
        or source["prior_evaluation"] != plan["prior_recorded_evaluation"]
    ):
        raise ValueError("handoff plan, selected source or six scheduled attempts differ")
    observed_source = candidate_files(root / "source")
    del observed_source["source.json"]
    if observed_source != source["files"]:
        raise ValueError("selected public source inventory differs")
    if (
        prior["candidate_files"]["main.py"] != plan["starter_sha256"]
        or prior["independent_evaluation"] != plan["prior_recorded_evaluation"]
    ):
        raise ValueError("prior program or result differs")
    for name, identity in plan["harness_files"].items():
        if Path(name).name != name or digest(root / "harness" / name) != identity:
            raise ValueError("recorded harness changed")
    before, after = root / "memory-models-before.json", root / "memory-models-after.json"
    cache_check = read(root / "memory-models-check.json")
    if (
        read(before) != read(after)
        or digest(before) != plan["memory_models_sha256"]
        or cache_check
        != {
            "unchanged": True,
            "before_sha256": digest(before),
            "after_sha256": digest(after),
        }
        or digest(root / "model-files.json") != plan["model_files_sha256"]
        or plan["model"]["model_files_manifest_sha256"] != plan["model_files_sha256"]
    ):
        raise ValueError("model file evidence changed or the model cache drifted")
    prompts = set()
    budget = {
        key: plan[key]
        for key in ("max_steps", "max_new_tokens_per_step", "wall_seconds", "temperature")
    }
    for index, row in enumerate(rows, 1):
        relative = Path(row["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe trial path")
        folder = root / relative
        trial = read(folder / "trial.json")
        handoff = trial["handoff"]
        condition = row["handoff_condition"]
        tools_hash = hashlib.sha256(
            json.dumps(plan["tools"][condition], sort_keys=True).encode()
        ).hexdigest()
        prompt_hash = hashlib.sha256(
            (trial["messages"][0]["content"] + trial["messages"][1]["content"]).encode()
        ).hexdigest()
        prompts.add(prompt_hash)
        if (
            row["path"] != f"{condition}/{index:02d}-none-{row['seed']}"
            or handoff["condition"] != condition
            or handoff["source_manifest_sha256"] != plan["source_manifest_sha256"]
            or handoff["source_session_id"] != source["session_id"]
            or handoff["starter_sha256"] != plan["starter_sha256"]
            or (
                trial["model"] != plan["model"]
                and not (
                    trial["model"] == {}
                    and not trial["turns"]
                    and trial["status"] == "environment_error"
                )
            )
            or trial["model_seed"] != row["seed"]
            or trial["budget"] != budget
            or trial["condition"] != "none"
            or trial["split"] != "public-development"
            or trial["evaluation_seeds"] != plan["evaluation_seeds"]
            or trial["tools_sha256"] != tools_hash
            or trial["prompt_sha256"] != prompt_hash
            or trial["public_protocol_probe_sha256"] != digest(root / "harness/protocol_probe.py")
            or trial["status"] != row["status"]
            or trial["error"] != row["error"]
            or trial["elapsed_seconds"] != row["elapsed_seconds"]
        ):
            raise ValueError("attempt differs from its preselected context, tools or budget")
        metrics = operation_metrics(trial, plan["starter_sha256"], prior)
        if metrics != handoff["operations"] or metrics != row["operations"]:
            raise ValueError("operation counts differ from original tool events")
        if (
            trial["completion_tokens"] != sum(turn["completion_tokens"] for turn in trial["turns"])
            or trial["prompt_tokens"] != sum(turn["prompt_tokens"] for turn in trial["turns"])
            or trial["completion_tokens"] != row["completion_tokens"]
        ):
            raise ValueError("usage differs from model responses")
        ready = handoff["bridge_ready"]
        if condition == "no-memory" and ready is not None:
            raise ValueError("no-memory condition unexpectedly started a memory bridge")
        if ready is not None:
            if (
                ready["source"] != source
                or ready["manifest_sha256"] != plan["source_manifest_sha256"]
                or ready["executable_sha256"] != source["funes"]["sha256"]
                or ready["server"] != {"name": "funes", "version": "1.3.0"}
                or ready["bounded_mcp"]["server"]
                != {"name": "skills-anywhere-public-handoff", "version": "1.0.0"}
            ):
                raise ValueError("memory bridge startup differs from reviewed identities")
        for event in trial["tool_events"]:
            if event["name"] in MEMORY_TOOLS:
                if condition == "no-memory" and event["result"].get("status") == "retrieved":
                    raise ValueError("no-memory trial claims retrieved evidence")
                check_retrieval(event, handoff, source)
        delivered = candidate_files(folder / "candidate")
        if trial["candidate_files"] != delivered:
            raise ValueError("collected candidate file identities differ")
        grade = row["evaluation"]
        if grade is not None:
            verify_evaluation(folder / "evaluation.json")
            evaluation = read(folder / "evaluation.json")
            check_candidate(folder / "candidate", evaluation)
            if (
                grade != {key: evaluation[key] for key in ("valid", "resolved", "score", "status")}
                or trial["independent_evaluation"] != grade
                or evaluation["seeds"] != plan["evaluation_seeds"]
                or trial["runtime"]
                != {
                    "backend": evaluation["runtime"]["backend"],
                    "image_id": evaluation["runtime"]["image_id"],
                }
            ):
                raise ValueError("independent acceptance differs from the delivered program")
        elif trial["independent_evaluation"] is not None or trial["status"] not in (
            "environment_error",
            "evaluation_error",
        ):
            raise ValueError("missing independent evaluation without a recorded failure")
    if len(prompts) != 1:
        raise ValueError("initial prompts differ across continuation conditions")
    return rows


def checked_baseline(root: Path) -> dict:
    folder = root / "preflight/baseline"
    record = read(folder / "record.json")
    evaluation = read(folder / "evaluation.json")
    verify_evaluation(folder / "evaluation.json")
    check_candidate(folder / "candidate", evaluation)
    if (
        record["kind"] != "scripted-preflight-without-agent-generation"
        or record["program_sha256"] != read(root / "experiment.json")["starter_sha256"]
        or record["program_sha256"] != digest(folder / "candidate/main.py")
        or record["candidate_sha256"] != evaluation["candidate_sha256"]
        or record["evaluation_sha256"] != digest(folder / "evaluation.json")
        or record["evaluation"]
        != {key: evaluation[key] for key in ("valid", "resolved", "score", "status")}
    ):
        raise ValueError("starter baseline differs from its checked program")
    return record["evaluation"]


def checked_preflight(root: Path) -> None:
    record = read(root / "preflight/mcp-entrypoint.json")
    plan = read(root / "experiment.json")
    source = read(root / "source/source.json")
    if (
        record["kind"] != "actual-native-MCP-preflight-not-agent-generation"
        or record["ready"]["source"] != source
        or record["ready"]["manifest_sha256"] != plan["source_manifest_sha256"]
        or [call["view"]["status"] for call in record["calls"]]
        != ["retrieved", "retrieved", "not_found", "request_rejected"]
        or record["source_mutation_control"]["removed"] != "prior-session.parquet"
        or record["source_mutation_control"]["view"]["status"] != "source_unavailable"
    ):
        raise ValueError("native preflight or missing-source control differs")
    for call in record["calls"]:
        check_retrieval(
            {**call, "result": call["view"]},
            {
                "bridge_ready": record["ready"],
                "source_manifest_sha256": plan["source_manifest_sha256"],
            },
            source,
        )


def render(root: Path, rows: list[dict]) -> str:
    plan = read(root / "experiment.json")
    baseline = checked_baseline(root)
    cards, table = [], []
    resolved = sum(bool(row["evaluation"] and row["evaluation"]["resolved"]) for row in rows)
    retrieved = sum(row["operations"]["retrieved_results"] for row in rows)
    changed = sum(row["operations"]["program_changed"] is True for row in rows)
    esc = html.escape
    for index, row in enumerate(rows, 1):
        path = esc(row["path"], quote=True)
        trial = read(root / row["path"] / "trial.json")
        grade, ops = row["evaluation"], row["operations"]
        score = f"{grade['score']:.1%}" if grade and grade["valid"] else "Unassessed"
        verdict = (
            ("Resolved" if grade["resolved"] else "Unresolved")
            if grade and grade["valid"]
            else "Unassessed"
        )
        label = "Funes MCP" if row["handoff_condition"] == "funes-mcp" else "No memory"
        table.append(
            f'<tr><th scope="row"><a href="#attempt-{index}">{label} · {row["seed"]}</a></th>'
            f"<td>{score}</td><td>{verdict}</td><td>{ops['retrieved_results']}</td>"
            f"<td>{ops['successful_file_writes']}</td><td>{ops['command_attempts']}</td></tr>"
        )
        events = []
        for event in trial["tool_events"]:
            memory = event["name"] in MEMORY_TOOLS
            title = event["name"]
            result_text = esc(json.dumps(event["result"], ensure_ascii=False, indent=2))
            if memory:
                title += " · " + event["result"].get("status", "unavailable")
            details = (
                "<details><summary>Read retrieved text and source identity</summary>"
                f'<pre tabindex="0">{result_text}</pre>'
                "</details>"
                if memory
                else ""
            )
            if event["name"] == "run_command":
                details = (
                    "<details><summary>Inspect command output</summary>"
                    f'<pre tabindex="0">{result_text}</pre>'
                    "</details>"
                )
            events.append(
                f'<li data-tool="{esc(event["name"], quote=True)}"><strong>{esc(title)}</strong>'
                f"<pre>{esc(json.dumps(event['arguments'], ensure_ascii=False, indent=2))}</pre>"
                f"{details}</li>"
            )
        cases = read(root / row["path"] / "evaluation.json")["cases"] if grade else []
        failed = [
            f"seed {case['seed']} / {case['case_id']}: "
            + (case.get("error") or ", ".join(k for k, v in case["checks"].items() if v is False))
            for case in cases
            if case["status"] != "passed"
        ]
        case_html = (
            "".join(f"<li>{esc(item)}</li>" for item in failed)
            or "<li>No failed case recorded.</li>"
        )
        program_state = {True: "Changed", False: "Unchanged", None: "Unavailable"}[
            ops["program_changed"]
        ]
        links = [f'<a href="{path}/trial.json" download>Trial JSON</a>']
        if (root / row["path"] / "candidate/main.py").is_file():
            links.append(f'<a href="{path}/candidate/main.py">Program</a>')
        if grade is not None:
            links.append(f'<a href="{path}/evaluation.json" download>Independent grade</a>')
        cards.append(
            f'<article id="attempt-{index}" data-condition="{row["handoff_condition"]}">'
            f"<h3>{index:02d} / {label} · seed {row['seed']}</h3>"
            f"<p><strong>{score} · {verdict}</strong></p><dl>"
            f"<dt>Harness stop</dt><dd>{esc(row['status'])}</dd>"
            f"<dt>Program state</dt><dd>{program_state}</dd>"
            f"<dt>Memory attempts / retrieved</dt><dd>{ops['memory_tool_attempts']} / "
            f"{ops['retrieved_results']}</dd>"
            f"<dt>Memory errors</dt><dd>{ops['memory_error_results']}</dd>"
            f"<dt>Command attempts</dt><dd>{ops['command_attempts']}</dd>"
            "<dt>Command attempts also seen in prior</dt>"
            f"<dd>{ops['command_attempts_seen_in_prior']}</dd>"
            "<dt>Repeated commands within this attempt</dt>"
            f"<dd>{ops['repeated_command_strings']}</dd>"
            f"<dt>Identical writes seen in prior</dt><dd>{ops['writes_seen_in_prior']}</dd>"
            f"<dt>Repeated writes within this attempt</dt><dd>{ops['exact_duplicate_writes']}</dd>"
            f"<dt>Generated tokens</dt><dd>{trial['completion_tokens']:,}</dd>"
            f"<dt>Interaction time</dt><dd>{row['elapsed_seconds']:.1f} s</dd></dl>"
            f"<details><summary>Inspect {len(events)} tool calls</summary>"
            f"<ol>{''.join(events)}</ol></details>"
            f"<details><summary>Inspect {len(failed)} failed cases</summary>"
            f"<ul>{case_html}</ul></details><p>{' · '.join(links)}</p>"
            + (f"<p>Recorded error: {esc(trial['error'])}</p>" if trial["error"] else "")
            + "</article>"
        )
    template = Path(__file__).with_name("handoff_page.html").read_text()
    return (
        template.replace("__RESOLVED__", str(resolved))
        .replace("__RETRIEVED__", str(retrieved))
        .replace("__CHANGED__", str(changed))
        .replace("__BASELINE__", f"{baseline['score']:.1%}")
        .replace("__SESSION__", esc(plan["source_session_id"]))
        .replace("__SOURCE_SHA__", esc(plan["source_manifest_sha256"]))
        .replace("__ROWS__", "".join(table))
        .replace("__CARDS__", "".join(cards))
    )


def copy_public(source: Path, output: Path):
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError("public evidence must not contain symlinks")
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        data = path.read_bytes()
        if len(data) > 16 * 1024 * 1024 or SECRET.search(data):
            raise ValueError("oversized evidence or credential-shaped content")
        destination = output / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)


def build(source: Path, baseline: Path, preflight: Path, output: Path) -> dict:
    rows = checked_rows(source)
    output.mkdir(parents=True, exist_ok=False)
    copy_public(source, output)
    copy_public(baseline, output / "preflight/baseline")
    shutil.copyfile(preflight, output / "preflight/mcp-entrypoint.json")
    (output / "index.html").write_text(render(output, rows))
    project = Path(__file__).resolve().parents[1]
    shutil.copyfile(project / "LICENSE", output / "LICENSE")
    for name in ("ROBOT_DATA_LICENSE.txt", "ROBOT_DATA_NOTICE.md"):
        shutil.copyfile(project / "src/evalarc/assets" / name, output / name)
    (output / "README.md").write_text(
        "# Funes MCP handoff evidence\n\n"
        "Six Qwen3-4B continuations of one public Qwen3-8B program. The selected source, "
        "all attempts, generated or unchanged programs, native MCP receipts and independent "
        "grades are retained. `preflight/` contains scripted controls, "
        "not additional agent trials.\n\n"
        "Open index.html offline. Review experiment.json for the preselected order and budgets, "
        "model-files.json for reviewed model hashes, and harness/ for the recorder snapshot. "
        "Memory embedding/reranking file identities are recorded before and after execution; "
        "model weights and the Funes executable are not redistributed.\n\n"
        "In an EvalArc source checkout with its development environment, verify this bundle:\n\n"
        "```sh\npython -m scripts.build_handoff_mcp --verify --output /path/to/this/folder\n```\n\n"
        "The downloaded ZIP contains records-manifest.json and can be verified after extraction. "
        "The hosted manifest.json additionally binds the complete archive's hash. "
        "Use the verifier from the source revision associated with the publication.\n\n"
        "The verification checks internal consistency, source identities, candidate bytes, "
        "independent grading records and derived page content. It does not authenticate the "
        "producer or rerun model inference. Public seeds are not hidden tests; exact repeated "
        "commands or writes are operation counts, not measured waste or time saved.\n"
    )
    (output / RECORDS_MANIFEST).write_text(
        json.dumps(
            {"schema": "evalarc.funes-mcp-handoff-records.v1", "files": record_inventory(output)},
            indent=2,
        )
        + "\n"
    )
    seal(output, SCHEMA, ARCHIVE)
    return verify_bundle(output)


def verify_bundle(root: Path) -> dict:
    if (root / "manifest.json").exists():
        count = verify_inventory(root, SCHEMA, ARCHIVE)
    else:
        if (root / ARCHIVE).exists():
            raise ValueError("hosted archive has no outer manifest")
        count = sum(p.is_file() for p in root.rglob("*"))
    records = verify_record_inventory(root)
    rows = checked_rows(root)
    checked_baseline(root)
    checked_preflight(root)
    if (root / "index.html").read_text() != render(root, rows):
        raise ValueError("handoff page differs from verified records")
    return {"trials": len(rows), "files": count, "record_files": records}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            verify_bundle(args.output)
            if args.verify
            else build(args.source, args.baseline, args.preflight, args.output)
        )
    )

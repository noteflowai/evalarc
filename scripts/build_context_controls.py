"""Build the matched-context pilot from complete recorded model and task evidence."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

from evalarc.runner import snapshot
from evalarc.verify import verify as verify_evaluation

CONDITIONS = ("relevant", "neutral")
SECRET = re.compile(
    rb"(?:hf_[A-Za-z0-9]{25,}|gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{25,})"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text())


def checked_rows(root: Path) -> list[dict]:
    plan = read(root / "experiment.json")
    match_path = root / "preparation/match.json"
    match = read(match_path)
    tokenization = read(root / "tokenization-check.json")
    rows = read(root / "summary.json")["trials"]
    if (
        plan["schema"] != "evalarc.skill-context-experiment.v1"
        or plan["conditions"] != list(CONDITIONS)
        or plan["model_seeds"] != [17, 41, 97]
        or plan["route"] != "mcp"
        or digest(match_path) != plan["match_sha256"]
        or len(rows) != 6
        or len({r["path"] for r in rows}) != 6
        or {(r["context_condition"], r["seed"]) for r in rows}
        != {(c, s) for c in CONDITIONS for s in (17, 41, 97)}
    ):
        raise ValueError("incomplete or unexpected matched-context plan")
    if plan["model_visible_open_skill_tokens"] != match["model_visible_open_skill_tokens"]:
        raise ValueError("token-match headline differs from preparation")
    profile = plan.get("protocol_profile", "stdin-example")
    if profile not in ("stdin-example", "persistent-request"):
        raise ValueError("unknown protocol profile")
    for name, identity in plan["harness_files"].items():
        if Path(name).name != name or digest(root / "harness" / name) != identity:
            raise ValueError("recorded harness differs")
    for condition in CONDITIONS:
        serialized = json.dumps(match[condition]["view"])
        check = tokenization["conditions"][condition]
        if (
            check["serialized_sha256"] != hashlib.sha256(serialized.encode()).hexdigest()
            or check["token_count"] != match["model_visible_open_skill_tokens"]
            or len(check["token_ids"]) != check["token_count"]
            or tokenization["tokenizer_files"] != match["tokenizer_files"]
            or read(root / f"preflight-{condition}.json")["view"] != match[condition]["view"]
        ):
            raise ValueError("native tokenizer or MCP preflight differs")
    for row in rows:
        relative = Path(row["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe trial path")
        folder = root / relative
        trial = read(folder / "trial.json")
        condition = row["context_condition"]
        expected_budget = {
            "max_steps": plan["max_steps"],
            "max_new_tokens_per_step": plan["max_new_tokens_per_step"],
            "wall_seconds": plan["wall_seconds"],
            "temperature": plan["temperature"],
        }
        if (
            trial["context_control"]["condition"] != condition
            or trial["context_control"]["match_sha256"] != plan["match_sha256"]
            or trial["model"] != plan["model"]
            or trial["model_seed"] != row["seed"]
            or trial["budget"] != expected_budget
            or trial["condition"] != "mcp"
            or row["condition"] != "mcp"
            or trial["task_context"] != "inline"
            or trial["evaluation_seeds"] != plan["evaluation_seeds"]
            or trial["skill_pins"] != match[condition]["pins"]
            or trial["prompt_sha256"]
            != hashlib.sha256(
                (trial["messages"][0]["content"] + trial["messages"][1]["content"]).encode()
            ).hexdigest()
        ):
            raise ValueError("trial differs from its preselected condition")
        if profile == "persistent-request":
            if trial.get("public_protocol_probe_sha256") != digest(
                root / "harness/protocol_probe.py"
            ):
                raise ValueError("public protocol diagnostic differs from the plan")
        elif "public_protocol_probe_sha256" in trial:
            raise ValueError("initial control unexpectedly includes the later protocol diagnostic")
        for event in trial["tool_events"]:
            if event["name"] == "open_skill" and "content" in event["result"]:
                if (
                    event["result"] != match[condition]["view"]
                    or event["receipt"]["route"] != "mcp"
                ):
                    raise ValueError("actual skill delivery differs from matched content")
        if (
            trial["prompt_tokens"] != sum(t["prompt_tokens"] for t in trial["turns"])
            or trial["completion_tokens"] != sum(t["completion_tokens"] for t in trial["turns"])
            or row["completion_tokens"] != trial["completion_tokens"]
            or row["status"] != trial["status"]
            or row["error"] != trial["error"]
            or row["elapsed_seconds"] != trial["elapsed_seconds"]
            or row["skill_loads"] != sum(e["name"] == "open_skill" for e in trial["tool_events"])
        ):
            raise ValueError("usage or execution headline differs from original turns")
        if row["evaluation"] is not None:
            verify_evaluation(folder / "evaluation.json")
            evaluation = read(folder / "evaluation.json")
            expected = {k: evaluation[k] for k in ("valid", "resolved", "score", "status")}
            with tempfile.TemporaryDirectory(prefix="evalarc-context-review-") as temporary:
                candidate_hash = snapshot(folder / "candidate", Path(temporary) / "candidate")
            if (
                candidate_hash != evaluation["candidate_sha256"]
                or trial["candidate_files"]
                != {
                    path.relative_to(folder / "candidate").as_posix(): digest(path)
                    for path in (folder / "candidate").rglob("*")
                    if path.is_file()
                }
                or trial["runtime"]
                != {
                    "backend": evaluation["runtime"]["backend"],
                    "image_id": evaluation["runtime"]["image_id"],
                }
                or evaluation["seeds"] != plan["evaluation_seeds"]
                or row["evaluation"] != expected
                or trial["independent_evaluation"] != expected
            ):
                raise ValueError("task result differs from independently evaluated candidate")
        elif trial["independent_evaluation"] is not None or trial["candidate_files"]:
            raise ValueError("missing evaluation for a collected candidate")
    # The model sees the same initial prompt and tool declarations in both conditions.
    trials = [read(root / row["path"] / "trial.json") for row in rows]
    if (
        len({r["prompt_sha256"] for r in trials}) != 1
        or len({r["tools_sha256"] for r in trials}) != 1
    ):
        raise ValueError("initial prompt or tool declarations differ across conditions")
    return rows


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Same length, different guidance · EvalArc</title>
<style>
:root{color-scheme:dark}body{font:17px/1.65 system-ui,sans-serif;background:#101725;
color:#e6ecf5;max-width:1040px;margin:auto;padding:32px 20px}a{color:#8ee1dc}
a:focus-visible{outline:3px solid #ffc87d}h1{font-size:clamp(30px,5vw,48px);line-height:1.2}
h2{font-size:23px}p{max-width:80ch}.grid{display:grid;
grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:20px}
article,.note{padding:18px 22px;background:#1c293c;border:1px solid #3c4961;border-radius:8px}
article h2{margin:0}dl{display:grid;grid-template-columns:1fr 1fr;gap:6px}
dd{margin:0;text-align:right}dt{color:#b1c4dd}strong{color:#ffc87d}
code{overflow-wrap:anywhere}details{margin:24px 0}summary{cursor:pointer}
</style></head><body>
<nav><a href="https://noteflowai.github.io/evalarc/context-controls/index.html">
Both cohorts online</a> ·
<a href="context-controls.zip?download=true" download>Offline cohort evidence</a></nav>
<h1>Same length. Different guidance.</h1>
<p><strong>__PROFILE__</strong></p>
<p>Six actual Qwen3-8B trials compare relevant robot-review guidance with unrelated
descriptive prose, delivered through the same Skills Anywhere MCP route.
Both skill-load results contain <strong>__TOKENS__ tokens</strong>, including hashes.</p>
<p class="note">The model, initial prompt, task, catalog description, tools and budgets
are fixed. The loaded content changes. EvalArc independently executes the generated
or unchanged starter programs in Docker; a successful skill load alone does not pass the task.</p>
__OUTCOMES__
<div class="grid">__CARDS__</div>
<details><summary>What is matched, and what can still differ?</summary>
<p>The match covers the JSON tool-result payload using the pinned Qwen3 tokenizer.
It includes the skill name, description, instruction body and file/bundle hashes.
Real MCP preflight results must equal the prepared payloads before inference.</p>
<p>Later generated programs, messages, tool calls and total token usage can differ.
Seeds 17, 41 and 97 each receive both conditions in alternating order. Each trial
has 12 model turns, up to 4096 generated tokens per turn and a 600-second wall budget.</p>
<p>This is one public development task with three model seeds, not six independent
tasks or a held-out benchmark. The earlier 27-trial engineering profiles use their
own recorded context and library versions; their results are not pooled here.</p></details>
<h2>Review every attempt</h2>
<p><a href="experiment.json">Preselected plan</a> ·
<a href="summary.json">All six results</a> ·
<a href="preparation/match.json">Both exact skill payloads</a> ·
<a href="tokenization-check.json">Native tokenizer check</a> ·
<a href="README.md">Methods and commands</a> ·
<a href="manifest.json">File identities</a></p>
<p>The page replays saved evidence. It does not call a model or execute a program.
Negative outcomes remain in the download. These small controls do not establish
a general skill benefit, context-length effect size, or client ranking.</p>
</body></html>
"""


def outcome_summary(source: Path, rows: list[dict]) -> dict:
    cases = [
        case
        for row in rows
        if row["evaluation"] is not None
        for case in read(source / row["path"] / "evaluation.json")["cases"]
    ]
    return {
        "trials": len(rows),
        "resolved": sum(bool(r["evaluation"] and r["evaluation"]["resolved"]) for r in rows),
        "cases": len(cases),
        "response_timeouts": sum(c.get("error") == "response timeout" for c in cases),
        "case_statuses": dict(Counter(c["status"] for c in cases)),
    }


def render_cohort(source: Path, rows: list[dict]) -> str:
    cards = []
    for row in rows:
        trial = read(source / row["path"] / "trial.json")
        grade = row["evaluation"]
        score = f"{grade['score']:.1%}" if grade and grade["valid"] else "Invalid / unavailable"
        resolved = (
            ("Yes" if grade["resolved"] else "No") if grade and grade["valid"] else "Unassessed"
        )
        path = html.escape(row["path"], quote=True)
        cases = read(source / row["path"] / "evaluation.json")["cases"] if grade else []
        case_details = "".join(
            "<li>"
            + html.escape(
                f"seed {case['seed']} / {case['case_id']}: "
                + (
                    case.get("error")
                    or ", ".join(k for k, v in case["checks"].items() if v is False)
                    or case["status"]
                )
            )
            + "</li>"
            for case in cases
        )
        cards.append(
            f"<article><h2>{html.escape(row['context_condition'])} · seed {row['seed']}</h2>"
            f"<dl><dt>Program score</dt><dd>{score}</dd><dt>Task resolved</dt><dd>{resolved}</dd>"
            f"<dt>Harness stop</dt><dd>{html.escape(row['status'])}</dd>"
            f"<dt>Skill-open calls</dt><dd>{row['skill_loads']}</dd>"
            f"<dt>Generated tokens</dt><dd>{trial['completion_tokens']:,}</dd>"
            f"<dt>Summed input tokens</dt><dd>{trial['prompt_tokens']:,}</dd>"
            f"<dt>Harness wall time</dt><dd>{row['elapsed_seconds']:.1f} s</dd></dl>"
            f"<details><summary>Inspect {len(cases)} case outcomes</summary>"
            f"<ul>{case_details}</ul></details>"
            f'<p><a href="{path}/trial.json">Original trial</a>'
            + (
                f' · <a href="{path}/candidate/main.py">Program</a>'
                if (source / row["path"] / "candidate/main.py").is_file()
                else ""
            )
            + (f' · <a href="{path}/evaluation.json">Independent grade</a>' if grade else "")
            + "</p></article>"
        )
    plan = read(source / "experiment.json")
    followup = plan.get("protocol_profile") == "persistent-request"
    profile = (
        "Follow-up: the same persistent-request diagnostic is available to both conditions."
        if followup
        else "Initial cohort: an EOF example is the supplied execution check."
    )
    results = outcome_summary(source, rows)
    explanation = (
        "This follow-up was planned after the initial failures. It is a separate "
        "public-development cohort. The helper checks two JSONL responses; it does not "
        "grade their numerical answers."
        if followup
        else "An EOF example can appear to work while a persistent JSONL service waits on buffered "
        "output. The original failures remain here; the subsequent cohort supplies a protocol "
        "diagnostic to both conditions."
    )
    outcomes = (
        f'<section class="note"><h2>{results["resolved"]} / {results["trials"]} tasks resolved</h2>'
        f"<p>{results['response_timeouts']} / {results['cases']} recorded cases had a response "
        f"timeout. {explanation}</p><p>A harness stop of <code>finished</code> means the agent "
        "called finish. The independent grader decides whether the task was resolved.</p></section>"
    )
    return (
        PAGE.replace("__CARDS__", "".join(cards))
        .replace("__TOKENS__", str(plan["model_visible_open_skill_tokens"]))
        .replace("__PROFILE__", profile)
        .replace("__OUTCOMES__", outcomes)
    )


def build(source: Path, output: Path) -> dict:
    rows = checked_rows(source)
    output.mkdir(parents=True, exist_ok=False)
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError("public records cannot contain symlinks")
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        data = path.read_bytes()
        if len(data) > 16 * 1024 * 1024 or SECRET.search(data):
            raise ValueError("oversized record or credential-shaped content")
        target = output / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (output / "index.html").write_text(render_cohort(source, rows))
    project = Path(__file__).resolve().parents[1]
    shutil.copyfile(project / "LICENSE", output / "LICENSE")
    for name in ("ROBOT_DATA_LICENSE.txt", "ROBOT_DATA_NOTICE.md"):
        shutil.copyfile(project / "src/evalarc/assets" / name, output / name)
    seal(output, "evalarc.skill-context-bundle.v1", "context-controls.zip")
    return verify_bundle(output)


def seal(output: Path, schema: str, archive_name: str):
    with zipfile.ZipFile(output / archive_name, "x", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob("*")):
            if path.is_file() and path != output / archive_name:
                info = zipfile.ZipInfo(path.relative_to(output).as_posix(), (2026, 9, 19, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, path.read_bytes())
    manifest = {
        "schema": schema,
        "files": {
            p.relative_to(output).as_posix(): {"sha256": digest(p), "bytes": p.stat().st_size}
            for p in sorted(output.rglob("*"))
            if p.is_file()
        },
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def verify_inventory(root: Path, schema: str, archive_name: str) -> int:
    manifest = read(root / "manifest.json")
    if manifest["schema"] != schema:
        raise ValueError("unexpected context bundle")
    files = manifest["files"]
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != set(files) | {"manifest.json"} or any(p.is_symlink() for p in root.rglob("*")):
        raise ValueError("context bundle inventory differs")
    for name, identity in files.items():
        path = root / name
        if identity != {"sha256": digest(path), "bytes": path.stat().st_size}:
            raise ValueError(f"context bundle file differs: {name}")
    with zipfile.ZipFile(root / archive_name) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(files) - {archive_name}:
            raise ValueError("context archive inventory differs")
        if any(archive.read(name) != (root / name).read_bytes() for name in names):
            raise ValueError("context archive content differs")
    return len(files)


def verify_bundle(root: Path) -> dict:
    count = verify_inventory(root, "evalarc.skill-context-bundle.v1", "context-controls.zip")
    rows = checked_rows(root)
    if (root / "index.html").read_text() != render_cohort(root, rows):
        raise ValueError("cohort page differs from verified trial evidence")
    return {"trials": len(rows), "files": count}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(verify_bundle(args.output) if args.verify else build(args.source, args.output))
    )

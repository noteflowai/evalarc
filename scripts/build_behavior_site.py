"""Build a browsable, offline record of native behavior controls and model attempts."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import re
import shutil
import zipfile
from pathlib import Path

from evalarc.behavior_review import review

ROOT = Path(__file__).resolve().parents[1]
SECRET = re.compile(rb"(?:hf_[A-Za-z0-9]{25,}|gh[pousr]_[A-Za-z0-9]{25,})")
IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
DIMENSIONS = (
    ("valid", "Evidence valid"),
    ("artifact_accepted", "Final file"),
    ("service_complete", "Service complete"),
    ("behavior_accepted", "Authorized behavior"),
    ("accepted", "Overall accepted"),
)


def document(path: Path):
    return json.loads(path.read_text())


def identity(path: Path) -> dict:
    return {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def safe_path(root: Path, name: str) -> Path:
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("unsafe record path")
    target = root / path
    if target.is_symlink() or any(p.is_symlink() for p in target.parents if p != root.parent):
        raise ValueError("symlink in record path")
    return target


def checked_cases(source: Path) -> list[dict]:
    """Recompute native reviews; never use a model finish claim as acceptance."""
    cases = []
    for group in ("controls", "service-controls"):
        folder = source / group
        plan = document(folder / "plan.json")
        summary = document(folder / "summary.json")
        if (
            plan["schema"] != "evalarc.behavior-controls-plan.v1"
            or summary["schema"] != "evalarc.behavior-controls.v1"
            or [c["id"] for c in plan["cases"]] != [c["id"] for c in summary["rows"]]
        ):
            raise ValueError("control inventory differs from plan")
        for name, expected in document(folder / "sources.json")["files"].items():
            if identity(safe_path(folder / "harness", name))["sha256"] != expected:
                raise ValueError("control harness differs")
        for row in document(folder / "base-dependencies.json")["files"]:
            expected = {key: row[key] for key in ("sha256", "bytes")}
            if identity(safe_path(folder / "base-dependencies", row["path"])) != expected:
                raise ValueError("post-collected base dependency differs")
        for planned, row in zip(plan["cases"], summary["rows"], strict=True):
            name = row["id"]
            if not IDENTIFIER.fullmatch(name):
                raise ValueError("unsafe case ID")
            case = folder / name
            if (case / "program.py").read_text() != (planned["program"] or ""):
                raise ValueError("executed control differs from plan")
            computed = review(case)
            if computed != document(case / "review.json"):
                raise ValueError("saved control review differs from raw evidence")
            for key, _ in DIMENSIONS:
                if row[key] != computed[key]:
                    raise ValueError("control headline differs from raw evidence")
            for key, default in (
                ("expected_valid", True),
                ("expected_behavior_accepted", None),
                ("expected_task_complete", None),
                ("expected_acceptance", None),
            ):
                if row[key] != planned.get(key, default):
                    raise ValueError("control expectation differs from frozen plan")
            cases.append({"group": group, "row": row, "review": computed})
    folder = source / "pilot"
    if not folder.exists():
        return cases
    plan = document(folder / "plan.json")
    summary = document(folder / "summary.json")
    completion = document(folder / "completion.json")
    if (
        plan["schema"] != "evalarc.behavior-pilot-plan.v1"
        or summary["schema"] != "evalarc.behavior-pilot.v1"
        or completion["scheduled"] != len(plan["trials"])
        or completion["recorded"] != len(plan["trials"])
        or completion["source_files_unchanged"] is not True
        or [r["id"] for r in plan["trials"]] != [r["id"] for r in summary["rows"]]
    ):
        raise ValueError("model cohort differs from frozen plan")
    for name, expected in plan["sources"].items():
        if identity(safe_path(folder / "harness", name)) != expected:
            raise ValueError("model harness differs")
    if (
        identity(folder / "model-files.json")["sha256"]
        != plan["model"]["model_files_manifest_sha256"]
    ):
        raise ValueError("model file manifest differs from loaded identity")
    for planned, row in zip(plan["trials"], summary["rows"], strict=True):
        name = row["id"]
        if not IDENTIFIER.fullmatch(name):
            raise ValueError("unsafe trial ID")
        case = folder / name
        trial = document(case / "trial.json")
        computed = review(case)
        if (
            any(trial[k] != v for k, v in planned.items())
            or trial["model"] != plan["model"]
            or trial["image_id"] != plan["image_id"]
            or computed != trial["independent_review"]
            or computed != document(case / "review.json")
            or trial["valid"] != (not trial["errors"] and computed["valid"])
            or trial["accepted"] != (trial["valid"] and computed["accepted"])
        ):
            raise ValueError("trial identity or review differs")
        selected = plan["conditions"][planned["condition"]]
        if trial["selected_skills"] != selected:
            raise ValueError("selected skills differ from condition")
        loaded = []
        for delivery in trial["deliveries"]:
            if "reply" not in delivery:
                continue
            reply = delivery["reply"]
            receipt = reply["receipt"]
            opened = receipt["raw"]["structuredContent"]
            pin = plan["pins"][delivery["name"]]
            if (
                delivery["name"] not in selected
                or receipt["route"] != "mcp"
                or opened["sha256"] != pin["sha256"]
                or opened["bundle"]["sha256"] != pin["bundle_sha256"]
                or reply["view"]["sha256"] != opened["sha256"]
                or reply["view"]["content"] != opened["content"]
            ):
                raise ValueError("actual MCP delivery differs from frozen skill identity")
            if delivery["phase"] == "preload":
                loaded.append(delivery["name"])
        if trial["valid"] and loaded != selected:
            raise ValueError("missing actual selected MCP preload")
        for turn in trial["turns"]:
            response = turn.get("response")
            if response and any(response.get(k) != v for k, v in plan["model"].items()):
                raise ValueError("generation used a different model service identity")
        for key, value in row.items():
            expected = trial[key] if key in trial else computed[key]
            if value != expected:
                raise ValueError("trial headline differs from recorded attempt")
        cases.append({"group": "pilot", "row": row, "review": computed})
    return cases


def escape(value) -> str:
    return html.escape(str(value), quote=True)


def link(path: str, label: str) -> str:
    return f'<a href="{escape(path)}">{escape(label)}</a>'


def result_list(row: dict) -> str:
    def label(key: str) -> str:
        if key == "behavior_accepted" and not row["valid"]:
            return "Not established"
        return "Yes" if row[key] else "No"

    return (
        '<dl class="results">'
        + "".join(f"<div><dt>{title}</dt><dd>{label(key)}</dd></div>" for key, title in DIMENSIONS)
        + "</dl>"
    )


STYLE = """
:root{color-scheme:dark}*{box-sizing:border-box}
body{margin:0;background:#111a28;color:#ecf1f7;font:17px/1.65 system-ui,sans-serif}
main,nav{max-width:1120px;margin:auto;padding:24px}
h1{font-size:clamp(30px,5vw,48px);line-height:1.15;max-width:24ch}
h2{font-size:24px;line-height:1.3}a{color:#8fe0d6;overflow-wrap:anywhere}
a:focus-visible,summary:focus-visible,input:focus-visible,select:focus-visible{
outline:3px solid #ffd58a;outline-offset:4px}
p{max-width:82ch}code,pre{overflow-wrap:anywhere;white-space:pre-wrap}
pre{font-size:13px;padding:16px;background:#0c1420;max-width:100%}
article,details.method{border:1px solid #394c65;border-radius:12px;padding:20px;margin:20px 0}
summary{cursor:pointer;min-height:44px;padding:10px 0;font-weight:650}
.results{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px}
.results div{border-left:3px solid #86cfc6;padding-left:12px}
dt{font-size:14px;color:#b9c8da}dd{margin:0;font-size:22px;font-weight:650}
.tag{color:#ffd58a}.scope{color:#bbcbdf}.violation{border-left:4px solid #ffc17c}
.events{list-style:none;padding:0}.events>li{padding:16px;margin:16px 0;background:#19263a}
label{display:block;margin-top:12px}input,select{font:inherit;min-height:44px;max-width:100%;
width:100%;background:#19263a;color:inherit;padding:8px;border:1px solid #657e9c;border-radius:6px}
.filters{display:grid;grid-template-columns:2fr 1fr 1fr;gap:20px}
[hidden]{display:none!important}.lines span{display:block;scroll-margin-top:20px}
:target{background:#3b3840}nav a{display:inline-block;min-height:44px;padding:10px 0}
@media(max-width:600px){main,nav{padding:16px}.filters{grid-template-columns:1fr;gap:0}}
"""


def page(title: str, body: str, navigation: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(title)} · EvalArc</title><style>{STYLE}</style></head>"
        f"<body><nav>{navigation}</nav><main>{body}</main></body></html>"
    )


def render_case(output: Path, entry: dict) -> None:
    group, row, computed = entry["group"], entry["row"], entry["review"]
    case = output / group / row["id"]
    sources: dict[str, set[int]] = {}
    events = []
    for event in computed["events"]:
        source = event["source"]
        if "trace" in source:
            path = safe_path(case / "evidence", source["trace"])
            name = path.name.removesuffix(".gz") + ".html"
            sources.setdefault(source["trace"], set()).update(source["lines"])
            evidence = link(f"{name}#L{source['lines'][0]}", "System-call source lines")
        else:
            evidence = link("evidence/service.json", f"Service journal, row {source['sequence']}")
        facts = {
            key: event[key]
            for key in (
                "path",
                "observed_path",
                "method",
                "status",
                "completed",
                "bytes",
                "errno",
                "permitted",
                "body_correct",
            )
            if key in event
        }
        css = ' class="violation"' if not event["permitted"] else ""
        events.append(
            f'<li{css} id="{escape(event["id"])}"><b>{escape(event["operation"])}</b>'
            f" · {escape(event['id'])}<pre>{escape(json.dumps(facts, indent=2))}</pre>"
            f"{evidence}</li>"
        )
    for name, numbers in sources.items():
        path = safe_path(case / "evidence", name)
        lines = gzip.decompress(path.read_bytes()).decode().splitlines()
        selected = sorted(
            {
                n
                for number in numbers
                for n in range(max(1, number - 1), min(len(lines), number + 1) + 1)
            }
        )
        excerpt = "".join(
            f'<span id="L{n}">{n:5d}  {escape(lines[n - 1])}</span>' for n in selected
        )
        target = path.name.removesuffix(".gz") + ".html"
        body = (
            "<h1>System-call source excerpts</h1><p>Line numbers refer to the complete "
            "decompressed trace. This page includes event lines and one line of context.</p>"
            f"<p>{link('evidence/' + name, 'Download the complete compressed trace')}</p>"
            f'<pre class="lines">{excerpt}</pre>'
        )
        (case / target).write_text(page("Trace excerpts", body, link("index.html", "Back to case")))
    status = row.get("status", "declared scripted control")
    errors = list(computed["coverage_errors"]) + ([row["error"]] if row.get("error") else [])
    errors += row.get("errors", [])
    failure = (
        "<h2>Evidence or execution errors</h2><pre>"
        + escape(json.dumps(errors, indent=2))
        + "</pre>"
        if errors
        else ""
    )
    body = (
        f'<p class="tag">{escape(group)}</p><h1>{escape(row["id"])}</h1>'
        f"<p>Recorded status: <b>{escape(status)}</b>. Status and acceptance are separate.</p>"
        + result_list(row)
        + "<p>"
        + " · ".join(
            [
                link("review.json", "Computed review"),
                link("policy.json", "Authorization contract"),
                link("evidence/observation.json", "Observation record"),
                link("evidence/final-inventory.json", "Final file inventory"),
                link("evidence/service.json", "Actual service journal"),
                link(
                    "trial.json" if group == "pilot" else "program.py",
                    "Full model attempt" if group == "pilot" else "Executed program",
                ),
            ]
        )
        + "</p>"
        + failure
        + "<h2>Observed operations</h2><p>Highlighted entries violate the declared contract. "
        "A failed attempt, a successful open, a read that returns bytes and a committed service "
        "write have different meanings. No listed operation is inferred from model prose.</p>"
        + (
            f'<ol class="events">{"".join(events)}</ol>'
            if events
            else "<p>No candidate operations recorded.</p>"
        )
    )
    (case / "index.html").write_text(
        page(row["id"], body, link("../../index.html", "All controls and attempts"))
    )


def render_index(output: Path, cases: list[dict]) -> None:
    cards = []
    for entry in cases:
        group, row = entry["group"], entry["row"]
        outcome = "invalid" if not row["valid"] else ("accepted" if row["accepted"] else "rejected")
        extra = (
            f"Condition: {escape(row['condition'])} · generation seed: {row['seed']} · "
            f"status: {escape(row['status'])}"
            if group == "pilot"
            else "Predeclared native control"
        )
        cards.append(
            f'<article data-group="{group}" data-outcome="{outcome}">'
            f'<p class="tag">{escape(group)} · {outcome}</p>'
            f"<h2>{link(group + '/' + row['id'] + '/index.html', row['id'])}</h2>"
            f"<p>{extra}</p>{result_list(row)}</article>"
        )
    body = """
<p class="tag">Runtime behavior review</p>
<h1>A correct final file can hide an unauthorized operation.</h1>
<p>Inspect what happened while a synthetic order report was produced: file access,
temporary writes and actual submissions to an isolated HTTP service. Every case
links its final-file check to recorded operations and source lines.</p>
<details class="method"><summary>Read the experiment method and interpretation</summary>
<p>The 24 file/composition controls and eight service controls are authored
maintainer cases. They check supported observer behavior; they are not independent
real-world tasks. Incomplete traces or requests cannot receive acceptance.</p>
<p>The model pilot uses one fixed task, four preloaded MCP conditions and three public
generation seeds per condition. Instruction lengths differ. All attempts remain
visible, including failed outputs and execution errors. A finish signal alone
does not establish task completion.</p>
<p>Candidate tools run as UID 65534 without effective capabilities. A trusted root
observer records supported system calls and local service receipts in a disposable,
network-isolated container. This is scoped observation, without general taint
tracking, kernel attestation or a claim about unseen reward hacking.</p>
<p>All cases come from the same AI-assisted maintainer process. File hashes check
record consistency. An independent human-authored final fault set remains future work.</p>
<p><a href="README.md">Reproduction commands and full scope</a> ·
<a href="controls/plan.json">File-control plan</a> ·
<a href="service-controls/plan.json">Service-control plan</a> ·
<a href="pilot/plan.json">Frozen model plan</a> ·
<a href="manifest.json">Bundle file identities</a></p></details>
<div class="filters" hidden id="filters">
<label>Find a case<input id="query" type="search"
placeholder="For example: write-then-delete"></label>
<label>Record type<select id="group"><option value="">All records</option>
<option value="controls">File/composition controls</option>
<option value="service-controls">Service controls</option>
<option value="pilot">Model attempts</option></select></label>
<label>Overall result<select id="outcome"><option value="">All outcomes</option>
<option value="accepted">Accepted</option><option value="rejected">Valid rejection</option>
<option value="invalid">Invalid evidence or execution</option></select></label></div>
<p id="count" aria-live="polite">__COUNT__ records; all shown.</p>
<section id="cases" aria-label="Controls and model attempts">__CARDS__</section>
<p hidden id="empty">No matching records. Clear the search or choose all records and outcomes.</p>
<script>
const cards = [...document.querySelectorAll("#cases article")];
const query = document.querySelector("#query"), group = document.querySelector("#group");
const outcome = document.querySelector("#outcome");
function filter() {
  let count = 0;
  for (const card of cards) {
    const visible = (!group.value || card.dataset.group === group.value) &&
      (!outcome.value || card.dataset.outcome === outcome.value) &&
      card.textContent.toLowerCase().includes(query.value.trim().toLowerCase());
    card.hidden = !visible; if (visible) count++;
  }
  document.querySelector("#count").textContent = `${count} of ${cards.length} records shown.`;
  document.querySelector("#empty").hidden = count !== 0;
}
for (const control of [query, group, outcome]) control.addEventListener("input", filter);
document.querySelector("#filters").hidden = false;
if (location.protocol === "file:") document.querySelector("#archive").hidden = true;
</script>
"""
    navigation = link("https://github.com/noteflowai/evalarc", "EvalArc project (online)") + (
        ' <span id="archive">· '
        '<a href="behavior-evidence.zip?download=true" download>'
        "Download complete offline evidence</a></span>"
    )
    (output / "index.html").write_text(
        page(
            "Inspect runtime behavior",
            body.replace("__COUNT__", str(len(cases))).replace("__CARDS__", "".join(cards)),
            navigation,
        )
    )


def build(source: Path, output: Path) -> dict:
    cases = checked_cases(source)
    output.mkdir(parents=True, exist_ok=False)
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError("symlinks are not public evidence")
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        data = path.read_bytes()
        if len(data) > 32 * 1024 * 1024 or SECRET.search(data):
            raise ValueError("oversized file or credential-shaped text")
        target = output / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    shutil.copyfile(ROOT / "LICENSE", output / "LICENSE")
    for case in cases:
        render_case(output, case)
    render_index(output, cases)
    manifest = {
        "schema": "evalarc.behavior-bundle.v1",
        "files": {
            p.relative_to(output).as_posix(): identity(p)
            for p in sorted(output.rglob("*"))
            if p.is_file()
        },
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with zipfile.ZipFile(output / "behavior-evidence.zip", "x", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob("*")):
            if path.is_file() and path.name != "behavior-evidence.zip":
                info = zipfile.ZipInfo(path.relative_to(output).as_posix(), (2026, 9, 19, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())
    return verify_bundle(output)


def verify_bundle(root: Path) -> dict:
    manifest = document(root / "manifest.json")
    if manifest["schema"] != "evalarc.behavior-bundle.v1":
        raise ValueError("unknown behavior bundle schema")
    files = manifest["files"]
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    archive_path = root / "behavior-evidence.zip"
    expected_files = set(files) | {"manifest.json"}
    if actual != expected_files | ({"behavior-evidence.zip"} if archive_path.exists() else set()):
        raise ValueError("behavior bundle inventory differs")
    for name, expected in files.items():
        if identity(safe_path(root, name)) != expected:
            raise ValueError(f"behavior bundle file differs: {name}")
    if archive_path.exists():
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or set(names) != expected_files:
                raise ValueError("offline archive inventory differs")
            for name in names:
                if archive.read(name) != safe_path(root, name).read_bytes():
                    raise ValueError("offline archive differs from public evidence")
    return {"cases": len(checked_cases(root)), "files": len(files)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    result = verify_bundle(args.output) if args.verify else build(args.source, args.output)
    print(json.dumps(result))

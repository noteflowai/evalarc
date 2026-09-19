"""Publish the initial and protocol-aware cohorts without pooling their outcomes."""

from __future__ import annotations

import argparse
import html
import json
import shutil
import tempfile
from pathlib import Path

from evalarc.runner import snapshot
from evalarc.verify import verify as verify_evaluation
from scripts.build_context_controls import (
    build as build_cohort,
)
from scripts.build_context_controls import (
    checked_rows,
    outcome_summary,
    read,
    seal,
    verify_inventory,
)
from scripts.build_context_controls import (
    verify_bundle as verify_cohort,
)

SCHEMA = "evalarc.skill-context-collection.v1"
COHORTS = ("initial", "protocol")


def summarize(root: Path) -> dict:
    plans = [read(root / name / "experiment.json") for name in COHORTS]
    if plans[0].get("protocol_profile", "stdin-example") != "stdin-example":
        raise ValueError("initial cohort must retain its original protocol profile")
    if plans[1].get("protocol_profile") != "persistent-request":
        raise ValueError("follow-up must declare the persistent-request diagnostic")
    for key in (
        "model",
        "conditions",
        "route",
        "model_seeds",
        "evaluation_seeds",
        "task_context",
        "max_steps",
        "max_new_tokens_per_step",
        "wall_seconds",
        "temperature",
        "model_visible_open_skill_tokens",
        "match_sha256",
    ):
        if plans[0][key] != plans[1][key]:
            raise ValueError(f"cross-cohort controlled input differs: {key}")
    cohorts, prompts, tools, evaluation_conditions = [], [], [], []
    for name in COHORTS:
        rows = checked_rows(root / name)
        trials = [read(root / name / row["path"] / "trial.json") for row in rows]
        prompts.append(trials[0]["prompt_sha256"])
        tools.append(trials[0]["tools_sha256"])
        cohorts.append({"id": name, **outcome_summary(root / name, rows)})
        for row in rows:
            if row["evaluation"] is not None:
                evaluation = read(root / name / row["path"] / "evaluation.json")
                evaluation_conditions.append(
                    {
                        key: evaluation[key]
                        for key in ("task", "grader_sha256", "cases_sha256", "runtime", "seeds")
                    }
                )
    if prompts[0] == prompts[1] or tools[0] != tools[1]:
        raise ValueError("expected an explicit prompt change and the same tool definitions")
    if cohorts[0]["cases"] != 48 or cohorts[0]["response_timeouts"] != 48:
        raise ValueError("initial evidence no longer supports the featured protocol failure")
    if len({json.dumps(row, sort_keys=True) for row in evaluation_conditions}) != 1:
        raise ValueError("independent evaluation conditions differ across the controls")
    reference_path = root / "initial/diagnostics/evaluation.json"
    verify_evaluation(reference_path)
    reference = read(reference_path)
    with tempfile.TemporaryDirectory(prefix="evalarc-context-reference-") as temporary:
        identity = snapshot(reference_path.parent / "candidate", Path(temporary) / "candidate")
    if (
        not reference["valid"]
        or not reference["resolved"]
        or reference["candidate_sha256"] != identity
        or any(reference[key] != value for key, value in evaluation_conditions[0].items())
    ):
        raise ValueError("reference diagnostic differs from the recorded evaluation conditions")
    diagnostic = read(root / "initial/diagnostics/buffering-diagnostic.json")
    original = read(root / "initial/neutral/02-mcp-17/evaluation.json")
    if (
        diagnostic["trial"] != "neutral/02-mcp-17"
        or diagnostic["candidate_sha256"] != original["candidate_sha256"]
        or diagnostic["image_id"] != original["runtime"]["image_id"]
        or [row["command"] for row in diagnostic["runs"]]
        != [
            ["{python}", "-I", "-B", "main.py"],
            ["{python}", "-I", "-B", "-u", "main.py"],
        ]
        or diagnostic["runs"][0]["error"] != "response timeout"
        or diagnostic["runs"][1]["error"] is not None
        or not isinstance(diagnostic["runs"][1]["response"], dict)
    ):
        raise ValueError("buffering diagnostic no longer supports the described comparison")
    for name in COHORTS:
        if read(root / name / "runtime-image.json")["Id"] != reference["runtime"]["image_id"]:
            raise ValueError("native runtime image identity differs from the evaluations")
    return {
        "schema": SCHEMA,
        "tokens_per_skill_load": plans[0]["model_visible_open_skill_tokens"],
        "cohorts": cohorts,
        "outcomes_are_pooled": False,
    }


def render(root: Path, summary: dict) -> str:
    sections = []
    for cohort in summary["cohorts"]:
        name = cohort["id"]
        rows = checked_rows(root / name)
        title = (
            "01 · Initial EOF example"
            if name == "initial"
            else "02 · Persistent-request diagnostic available"
        )
        lines = []
        for seed in (17, 41, 97):
            cells = []
            for condition in ("relevant", "neutral"):
                row = next(
                    r for r in rows if r["seed"] == seed and r["context_condition"] == condition
                )
                grade = row["evaluation"]
                score = f"{grade['score']:.1%}" if grade and grade["valid"] else "unassessed"
                resolved = (
                    ("resolved" if grade["resolved"] else "unresolved")
                    if grade and grade["valid"]
                    else "unassessed"
                )
                cells.append(
                    f'<td><a href="{name}/{html.escape(row["path"])}/evaluation.json">'
                    f"{score}</a><br><span>{resolved}</span></td>"
                    if grade
                    else "<td>Unassessed</td>"
                )
            lines.append(f'<tr><th scope="row">{seed}</th>{"".join(cells)}</tr>')
        sections.append(
            f'<section class="card"><h2>{title}</h2>'
            f"<p><strong>{cohort['resolved']} / {cohort['trials']} tasks resolved.</strong> "
            f"{cohort['response_timeouts']} response timeouts "
            f"in {cohort['cases']} recorded cases.</p>"
            "<table><caption>Each seed receives both conditions. "
            "Scores are independent program checks.</caption><thead><tr>"
            '<th scope="col">Model seed</th><th scope="col">Relevant guidance</th>'
            '<th scope="col">Unrelated prose</th></tr></thead>'
            f"<tbody>{''.join(lines)}</tbody></table>"
            f'<p><a class="button" href="{name}/index.html">Inspect all six attempts →</a> '
            f'<a href="{name}/context-controls.zip?download=true" download>'
            "Download cohort</a></p></section>"
        )
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Context Controls · EvalArc</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:auto;max-width:1080px;
padding:32px 22px;background:#101725;color:#e6ecf5;font:17px/1.65 system-ui,sans-serif}
a{color:#8ee1dc}a:focus-visible{outline:3px solid #ffc87d;outline-offset:4px}
h1{font-size:clamp(32px,5vw,54px);line-height:1.1;max-width:24ch}h2{font-size:24px}
p{max-width:82ch}.eyebrow{color:#8ee1dc;letter-spacing:.08em;font-size:13px}
.card,.method{border:1px solid #3c4961;border-radius:10px;background:#1c293c;
padding:20px;margin:28px 0}.method{background:#142d31}strong{color:#ffc87d}
table{border-collapse:collapse;width:100%;margin:18px 0}caption{text-align:left;
color:#b1c4dd;font-size:14px;margin-bottom:12px}th,td{text-align:left;padding:10px;
border-bottom:1px solid #3c4961}td span{font-size:14px;color:#b1c4dd}
.button{display:inline-block;padding:8px 14px;border:1px solid #8ee1dc;
border-radius:6px;margin:5px 12px 5px 0}code{overflow-wrap:anywhere}
@media(max-width:540px){body{padding:20px 12px}.card,.method{padding:14px}
th,td{padding:8px 5px;font-size:14px}h2{font-size:21px}}
</style></head><body><nav><a href="https://noteflowai.github.io/evalarc/">EvalArc online</a> ·
<a href="experiment.zip?download=true" download>Complete offline evidence</a></nav>
<p class="eyebrow">RECORDED GPU CONTEXT CONTROLS · QWEN3-8B / L40S</p>
<h1>Check the protocol before interpreting the score.</h1>
<p>Twelve recorded model attempts compare relevant robot-review guidance with
unrelated descriptive text. Both MCP skill-load payloads contain <strong>__TOKENS__ tokens</strong>,
including file hashes. The original six attempts and the six-attempt follow-up remain separate.</p>
<div class="method"><h2>What changed between the cohorts?</h2>
<p>The initial programs timed out waiting for a JSON response. Their EOF example could finish
without testing persistent interaction. A separate reference run passed under the same grader.
The follow-up gives both conditions the same two-request protocol diagnostic and a flush
instruction. It was planned after observing the original failures.</p>
<p>The task, model, skill texts, seeds, tools and budgets remain fixed. Initial instructions and
the supplied helper differ between cohorts; outcomes are not pooled into an efficacy estimate.
The helper checks JSONL interaction and does not grade numerical correctness.</p></div>
__SECTIONS__
<section><h2>Inspect the failure before trusting a finish signal</h2>
<p>An agent can call <code>finish</code> without implementing the program. A program can
return JSON correctly while computing a metric incorrectly. Each cohort preserves submitted
programs, complete messages, tool receipts and independent case checks. A declared finish,
program score and resolved task are separate outcomes.</p>
<p>The unrelated control is descriptive prose, not a second task-specific reference. It retains
the same catalog name and description; inspect both exact payloads before interpreting any
difference. This is one public-development task and three model seeds, not a model ranking
or evidence of general skill efficacy.</p></section>
<section><h2>Reproduce and review</h2><p>
<a href="README.md">Methods and exact commands</a> ·
<a href="cohorts.json">Separate cohort summaries</a> ·
<a href="manifest.json">File identities</a> ·
<a href="initial/diagnostics/evaluation.json">Reference environment check</a> ·
<a href="initial/diagnostics/buffering-diagnostic.json">Unchanged-program buffering diagnostic</a>
</p><p>The page displays saved records and works offline. No inference or candidate execution
runs in the browser. Offline verification checks consistency;
it does not authenticate a producer.</p>
</section></body></html>""".replace("__TOKENS__", str(summary["tokens_per_skill_load"])).replace(
        "__SECTIONS__", "".join(sections)
    )


def build(initial: Path, protocol: Path, methods: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    for name, source in zip(COHORTS, (initial, protocol), strict=True):
        build_cohort(source, output / name)
    shutil.copyfile(methods, output / "README.md")
    summary = summarize(output)
    (output / "cohorts.json").write_text(json.dumps(summary, indent=2) + "\n")
    (output / "index.html").write_text(render(output, summary))
    seal(output, SCHEMA, "experiment.zip")
    return verify(output)


def verify(root: Path) -> dict:
    count = verify_inventory(root, SCHEMA, "experiment.zip")
    for name in COHORTS:
        verify_cohort(root / name)
    summary = summarize(root)
    if read(root / "cohorts.json") != summary:
        raise ValueError("cohort headline differs from the independent evidence")
    if (root / "index.html").read_text() != render(root, summary):
        raise ValueError("collection page differs from its separate cohort evidence")
    return {"cohorts": len(COHORTS), "trials": 12, "files": count}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial", type=Path)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--methods", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    result = (
        verify(args.output)
        if args.verify
        else build(args.initial, args.protocol, args.methods, args.output)
    )
    print(json.dumps(result))

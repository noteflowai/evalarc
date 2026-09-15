"""Self-contained, accessible trace review; all imported text is escaped."""

from __future__ import annotations

import html
import json
from pathlib import Path

STYLE = """
:root{color-scheme:dark;font:16px/1.6 system-ui,sans-serif;background:#101618;color:#edf1e9}
*{box-sizing:border-box}body{margin:0}main,header,footer{max-width:1160px;margin:auto;padding:24px}
a{color:#c4efaa;text-underline-offset:4px}h1{font-size:clamp(2.4rem,6vw,4.4rem);line-height:1.08;
letter-spacing:-.04em;margin:32px 0 20px}h1 em{color:#c4efaa;font-style:normal}
h2{line-height:1.25}h3{margin:10px 0}p{max-width:80ch}.muted{color:#b5c0b7}
.eyebrow{font-size:.8rem;letter-spacing:.12em;text-transform:uppercase}
header{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:28px 0}
.stats div,article,details.panel{border:1px solid #46534b;border-radius:12px;
padding:20px;background:#18201e}
.stats strong{display:block;font-size:2rem}
.badge{display:inline-block;border:1px solid currentColor;
padding:3px 9px;border-radius:8px;font-size:.8rem;letter-spacing:.04em}
.accepted,.matched{color:#c4efaa}.rejected,.changed,.not_called{color:#ffbb9a}
.incomplete,.unknown,.missing,.skipped,.error,.unassessed{color:#f0d48b}
.tools{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:22px 0}
button,input{font:inherit;background:#17201d;color:inherit;border:1px solid #708275;
border-radius:8px;padding:10px 14px;min-height:44px}
input{width:100%;max-width:450px}button{cursor:pointer}
button[aria-pressed=true]{background:#c4efaa;color:#17201d}
:focus-visible{outline:3px solid #e4c783;outline-offset:4px}
article{margin:18px 0;scroll-margin-top:12px}article[hidden]{display:none}
.case-top{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.table-scroll{max-width:100%;overflow-x:auto}table{width:100%;border-collapse:collapse}
caption{text-align:left;font-weight:600;margin:18px 0 8px}
td,th{text-align:left;vertical-align:top;padding:12px 8px;border-bottom:1px solid #46534b}
th{color:#b5c0b7}td:first-child{min-width:180px}pre,code{font-size:.88rem}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#101618;padding:14px;border-radius:8px}
summary{cursor:pointer;padding:12px 0;min-height:44px}small{display:block;color:#b5c0b7}
.links{display:flex;flex-wrap:wrap;gap:18px;margin:20px 0}
.scope{border-left:3px solid #c4efaa;padding-left:18px}
.skip{position:absolute;left:8px;top:-80px}.skip:focus{top:8px;background:#101618;padding:12px}
@media(max-width:480px){main,header,footer{padding:16px}article{padding:14px}.stats{gap:6px}
.stats div{padding:10px}.stats span{font-size:.82rem}.stats strong{font-size:1.6rem}}
"""

SCRIPT = """
const buttons = [...document.querySelectorAll('[data-filter]')];
const search = document.querySelector('#search');
let filter = 'all';
function update() {
  let count = 0;
  const query = search.value.toLowerCase();
  document.querySelectorAll('article[data-gate]').forEach(card => {
    card.hidden = !(filter === 'all' || card.dataset.gate === filter)
      || !card.textContent.toLowerCase().includes(query);
    if (!card.hidden) count++;
  });
  document.querySelector('#filter-status').textContent = count + ' cases shown';
}
buttons.forEach(button => button.addEventListener('click', () => {
  filter = button.dataset.filter;
  buttons.forEach(other => other.setAttribute('aria-pressed', String(other === button)));
  update();
}));
search.addEventListener('input', update);
update();
"""


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def pretty(value: object) -> str:
    return escape(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def badge(state: str) -> str:
    return f'<span class="badge {escape(state)}">{escape(state.replace("_", " ").upper())}</span>'


def render(record: dict, target: Path) -> None:
    cards = []
    for index, case in enumerate(record["cases"]):
        coverage = "complete" if case["skill_observation_complete"] else "incomplete"
        rows = []
        for row in case["results"]:
            verdict = (
                "accepted"
                if row["accepted"] is True
                else "rejected"
                if row["accepted"] is False
                else row["status"]
            )
            value = row["value"] if row["value"] is not None else row["label"]
            display = escape(value) if row["status"] == "assessed" else "—"
            rows.append(
                f"<tr><td>{escape(row['evaluator'])}<small>{escape(row['revision'])}</small>"
                f"<small>{escape(row['span_id'] or row['trace_id'] or 'Session')}</small></td>"
                f"<td>{display}</td><td>{badge(verdict)}</td>"
                f"<td>{escape(row['explanation'])}"
                f"<small>{escape(row['error'] or '')}</small></td></tr>"
            )
        skills = (
            "".join(
                f"<li>{escape(s['name'])} {badge(s['status'])}</li>"
                for s in case["expected_skills"]
            )
            or "<li>No skill required by this case.</li>"
        )
        calls = (
            "".join(
                f"<details><summary>{escape(call['name'])} — bundle {escape(call['identity'])}"
                f"</summary><pre>{pretty(call)}</pre></details>"
                for call in case["skill_calls"]
            )
            or "<p>No annotated skill calls.</p>"
        )
        cards.append(
            f'<article id="case-{index}" data-gate="{case["gate"]}">'
            f'<div class="case-top"><h2>{escape(case["case_id"])}</h2>{badge(case["gate"])}</div>'
            f"<p>{escape(case['goal'])}</p>"
            f'<p class="muted">{case["span_count"]} exported spans · '
            f"Skill observation declared {coverage}"
            f"</p><h3>Expected skills</h3><ul>{skills}</ul>"
            f'<div class="table-scroll" tabindex="0" role="region" aria-label="Evaluator results">'
            f"<table><caption>Imported evaluator results</caption>"
            f'<thead><tr><th scope="col">Evaluator / target</th><th scope="col">Value</th>'
            f'<th scope="col">Configured gate</th><th scope="col">Explanation</th></tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table></div>"
            f"<details><summary>Skill deliveries and recording identity</summary>{calls}"
            f"<pre>{pretty({'session_id': case['session_id'], 'trace_ids': case['trace_ids']})}"
            f"</pre></details></article>"
        )
    comparison = ""
    if "comparison" in record:
        compared = record["comparison"]
        transitions = "".join(
            f"<tr><td>{escape(row['case_id'])}</td><td>{badge(row['baseline'])}</td>"
            f"<td>{badge(row['current'])}</td><td>"
            f"{'Previously accepted; now needs review' if row['regressed'] else '—'}</td></tr>"
            for row in compared["cases"]
        )
        comparison = (
            '<section aria-label="Paired comparison"><h2>What changed between runs?</h2>'
            '<div class="table-scroll" tabindex="0" role="region" aria-label="Case comparison">'
            "<table><caption>Same golden set and evaluator rules</caption><thead><tr>"
            '<th scope="col">Case</th><th scope="col">Baseline</th><th scope="col">Current</th>'
            f'<th scope="col">Change</th></tr></thead><tbody>{transitions}</tbody></table></div>'
            "<details><summary>Changed model, prompt, tool and skill configuration</summary>"
            f"<pre>{pretty(compared['configuration_changes'])}</pre></details>"
            f'<p class="muted">{escape(compared["interpretation"])}</p>'
            '<a href="baseline-input.json" download>Download baseline input</a></section>'
        )
    stats = "".join(
        f"<div><strong>{record['summary'][state]}</strong><span>{state.title()} cases</span></div>"
        for state in ("accepted", "rejected", "incomplete")
    )
    filters = "".join(
        f'<button type="button" data-filter="{state}" aria-pressed="{str(state == "all").lower()}">'
        f"{state.title()}</button>"
        for state in ("all", "accepted", "rejected", "incomplete")
    )
    identity = {
        k: record[k]
        for k in ("run_id", "source_sha256", "dataset_sha256", "configuration", "evaluators")
    }
    target.write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="referrer" content="no-referrer">'
        "<title>EvalArc · Trace Workbench</title>"
        f'<style>{STYLE}</style></head><body><a class="skip" href="#cases">Skip to cases</a>'
        "<header><strong>EvalArc / Trace Workbench</strong>"
        '<a href="https://github.com/noteflowai/evalarc">Source &amp; documentation</a></header>'
        '<main><p class="eyebrow">Golden cases · skill deliveries · evaluator results</p>'
        "<h1>Follow the run.<br><em>Keep the evidence.</em></h1>"
        f"<p>{badge(record['provenance']['kind'])} "
        f"{escape(record['provenance']['description'])}</p>"
        "<p>Inspect each case against its declared acceptance rules. Missing results, skipped "
        "evaluations and assessed zero scores remain distinct.</p>"
        f'<p class="scope">{escape(record["scope"])}</p><div class="stats">{stats}</div>'
        '<div class="links"><a href="input.json" download>Download original input</a>'
        '<a href="review.json" download>Download review JSON</a></div>'
        '<details class="panel"><summary>Review your own AgentCore export locally</summary>'
        "<p>Wrap the saved spans and Evaluate responses with your versioned golden cases and "
        "rubrics, following the input contract. The CLI runs offline and creates this report.</p>"
        "<pre>evalarc trace-import input.json --output runs/review-001\n"
        "evalarc trace-import current.json --baseline baseline.json --output runs/compare-001\n"
        "evalarc trace-verify runs/review-001</pre>"
        '<a href="https://github.com/noteflowai/evalarc/blob/main/docs/trace-workbench.md">'
        "Input contract and preparation guide</a></details>"
        f'{comparison}<section id="cases"><h2>Follow each golden case</h2>'
        '<label for="search">Find a case, skill, evaluator or explanation</label>'
        '<p><input id="search" type="search" autocomplete="off"></p>'
        f'<div class="tools" role="group" aria-label="Filter cases">{filters}</div>'
        '<p id="filter-status" role="status" aria-live="polite"></p>'
        f'{"".join(cards)}</section><details class="panel">'
        "<summary>Frozen configuration, dataset and source identity</summary>"
        f"<pre>{pretty(identity)}</pre>"
        "</details></main><footer>No automatic upload, model call or cloud deployment. "
        "Raw input may contain private trace data; choose what you share.</footer>"
        f"<script>{SCRIPT}</script></body></html>",
        encoding="utf-8",
    )

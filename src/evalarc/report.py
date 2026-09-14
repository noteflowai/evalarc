"""Offline HTML audit reports with no scripts or remote assets."""

from __future__ import annotations

import html
import json
from pathlib import Path


def render_audit(data: dict, destination: Path) -> None:
    esc = lambda value: html.escape(str(value), quote=True)  # noqa: E731
    score_text = lambda value: "unassessed" if value is None else f"{value:.3f}"  # noqa: E731
    rows = []
    for row in data["mutants"]:
        state = (
            "UNASSESSED"
            if row.get("valid") is False
            else ("Detected" if row["killed"] else "SURVIVED")
        )
        rows.append(
            f"<tr><td><code>{esc(row['name'])}</code></td>"
            f"<td>{esc(row['target_dimension'])}</td>"
            f"<td>{score_text(row['score'])}</td><td>{state}</td>"
            f"<td>{esc(', '.join(row['failing_cases']))}</td></tr>"
        )
    reference = data["reference"]
    bars = "".join(
        f'<div class="dimension"><span>{esc(name)}</span>'
        + (
            "<span>unassessed</span>"
            if group["score"] is None
            else f'<meter min="0" max="1" value="{group["score"]}">{group["score"]:.2f}</meter>'
        )
        + f"<span>{group['passed']}/{group['total']}</span></div>"
        for name, group in reference["dimensions"].items()
    )
    document = """<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy"
 content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>EvalArc · Grader audit</title>
<style>
:root{color-scheme:dark;font:16px/1.6 system-ui,sans-serif;background:#101618;color:#e0ece7}
body{max-width:1080px;margin:60px auto;padding:0 24px}
.eyebrow{color:#86dbaf;letter-spacing:.18em;font-size:12px;font-weight:700}
h1{font-size:clamp(32px,6vw,64px);letter-spacing:-.045em;line-height:1.1;margin:16px 0}
p{color:#acbeb5;max-width:760px}.cards{display:flex;gap:20px;flex-wrap:wrap;margin:36px 0}
.card{border:1px solid #33463d;border-radius:12px;padding:18px 26px;flex:1;min-width:180px}
.number{font-size:38px;color:#96e8b9;font-weight:650}.label{color:#b7c6bf}
.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}
td,th{text-align:left;padding:14px;border-bottom:1px solid #33463d}th{color:#86dbaf}
code{font-family:ui-monospace,monospace}h2{margin-top:42px}
.dimension{display:flex;gap:16px;align-items:center;max-width:620px;margin:10px 0}
.dimension span:first-child{width:150px}meter{flex:1;accent-color:#86dbaf}
footer{margin-top:48px;border-top:1px solid #33463d;padding-top:20px;font-size:13px}
.metadata{overflow-wrap:anywhere;font-size:13px}
pre{overflow:auto;padding:18px;background:#17221c;font-size:12px;max-height:480px}
summary{cursor:pointer;color:#96e8b9}details{margin:16px 0}
</style>
<div class="eyebrow">EVALARC / DEVELOPMENT AUDIT</div>
<h1>Test the grader.<br>Then trust the signal.</h1>
<p>Behavioral controls for task-specific agent evaluations. Correct and faulty
submissions are evaluated against the same externally enforced contract.</p>
"""
    if data.get("valid") is False:
        document += (
            "<p><strong>Invalid audit: environment failure.</strong> "
            "Unassessed outcomes are not agent failures or surviving controls.</p>"
        )
    document += (
        f'<div class="cards"><div class="card"><div class="number">'
        f'{data["killed"]}/{data["total"]}</div><div class="label">'
        "declared faults detected</div></div>"
        f'<div class="card"><div class="number">{score_text(reference["score"])}</div>'
        '<div class="label">reference correctness</div></div>'
        f'<div class="card"><div class="number">{esc(reference["runtime"]["backend"])}</div>'
        '<div class="label">execution backend</div></div></div>'
        '<h2>Does the grader detect plausible defects?</h2><div class="scroll">'
        "<table><thead><tr><th>Negative control</th><th>Target</th>"
        "<th>Candidate score</th><th>Result</th><th>Evidence</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
        "<h2>Positive control</h2>" + bars
    )
    traces = [case for case in reference.get("cases", []) if "trace" in case]
    if traces:
        document += "<h2>Reference execution evidence</h2>"
        for case in traces:
            document += (
                f"<details><summary>{esc(case['case_id'])} · seed {esc(case['seed'])} · "
                f"{esc(case['status'])}</summary><pre>"
                f"{esc(json.dumps(case, ensure_ascii=False, indent=2))}</pre></details>"
            )
    document += (
        '<h2>Reproduction record</h2><p class="metadata">'
        f"Task: {esc(reference['task']['id'])} v{esc(reference['task']['version'])}<br>"
        f"Seeds: {esc(reference['seeds'])}<br>"
        f"Grader SHA-256: {esc(reference['grader_sha256'])}<br>"
        f"Cases SHA-256: {esc(reference['cases_sha256'])}<br>"
        f"Image ID: {esc(reference['runtime']['image_id'])}<br>"
        f"Created: {esc(reference['created_at'])}</p>"
        '<p><a href="audit.json">Complete JSON evidence for all controls</a></p>'
        "<footer><strong>Scope:</strong> This is a scripted grader audit, not an AI "
        "leaderboard. Public seeds are not held-out evaluation data. "
        "Detection rates apply only to the listed fault models. "
        "No human time horizon, model quality, or RL improvement is inferred.</footer></html>"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document)

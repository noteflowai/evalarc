"""Offline HTML reports: self-contained, no remote assets, one CSP-pinned inline script."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
from importlib.resources import files
from pathlib import Path

STYLE = """
:root{color-scheme:light dark;--bg:#101618;--surface:#152019;--surface-2:#17221c;
--text:#e0ece7;--muted:#acbeb5;--border:#33463d;--accent:#96e8b9;--accent-2:#86dbaf;
--bad:#edb68d;--warn:#e6d48a;--pass-bg:#152019;--fail-bg:#211b16;--warn-bg:#1f1d14;
--radius:12px;font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif;
background:var(--bg);color:var(--text)}
@media(prefers-color-scheme:light){:root{--bg:#ffffff;--surface:#f3f7f5;--surface-2:#eef3f0;
--text:#142019;--muted:#46564e;--border:#c9d6cf;--accent:#0b6b43;--accent-2:#0b6b43;
--bad:#a3420c;--warn:#7a5d00;--pass-bg:#eef8f2;--fail-bg:#fff4ec;--warn-bg:#fffbe6}}
*,*::before,*::after{box-sizing:border-box}
body{max-width:1120px;margin:40px auto;padding:0 24px}
.eyebrow{color:var(--accent-2);letter-spacing:.14em;font-size:12px;font-weight:700}
h1{font-size:clamp(28px,4vw,44px);letter-spacing:-.03em;line-height:1.15;margin:10px 0 18px}
h2{margin-top:40px;font-size:22px}h3{font-size:17px}
p{color:var(--muted);max-width:76ch}.cards{display:flex;gap:16px;flex-wrap:wrap;margin:24px 0}
.card{border:1px solid var(--border);border-radius:var(--radius);padding:16px 22px;flex:1;
min-width:150px;background:var(--surface)}
.number{font-size:32px;color:var(--accent);font-weight:650;font-variant-numeric:tabular-nums}
.label{color:var(--muted)}
.scroll{overflow:auto;max-height:70vh;border:1px solid var(--border);border-radius:var(--radius)}
table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}
td,th{text-align:left;padding:10px 14px;border-bottom:1px solid var(--border);vertical-align:top}
th{color:var(--accent-2);background:var(--surface);position:sticky;top:0;z-index:1}
tbody tr:hover{background:var(--surface-2)}tbody tr:last-child td{border-bottom:0}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.92em}
.dimension{display:flex;gap:16px;align-items:center;max-width:620px;margin:10px 0}
.dimension span:first-child{width:150px}meter{flex:1;accent-color:var(--accent)}
footer{margin-top:48px;border-top:1px solid var(--border);padding-top:20px;font-size:13px;
color:var(--muted)}
.metadata{overflow-wrap:anywhere;font-size:13px}
pre{overflow:auto;padding:16px;background:var(--surface-2);font-size:12px;max-height:480px;
border-radius:8px;white-space:pre-wrap}
summary{cursor:pointer;color:var(--accent)}details{margin:12px 0}
summary{min-height:44px;padding:10px 0}
a:focus-visible,summary:focus-visible,button:focus-visible,input:focus-visible,
.scroll:focus-visible{outline:3px solid var(--accent);outline-offset:3px}
.audit-control{border:1px solid var(--border);border-radius:var(--radius);padding:12px 18px}
.audit-control summary{overflow-wrap:anywhere}.audit-control p{overflow-wrap:anywhere}
.audit-coverage{border-left:3px solid var(--bad);padding:12px 20px;background:var(--surface-2)}
a{color:var(--accent)}.failed,.agent_error,.environment_error{color:var(--bad)}
.passed{color:var(--accent)}td{overflow-wrap:anywhere}
.scroll table{min-width:680px}td:first-child{min-width:150px;overflow-wrap:normal}
.change-cards{display:none}
.change-card{border:1px solid var(--border);border-radius:var(--radius);padding:16px}
.change-card h3{font-size:16px;margin:0;overflow-wrap:anywhere}.change-card p{margin:10px 0 0}
.verdict{border:1px solid var(--border);border-left:6px solid var(--accent);
border-radius:var(--radius);padding:16px 22px;margin:20px 0 8px;background:var(--pass-bg)}
.verdict.fail{border-left-color:var(--bad);background:var(--fail-bg)}
.verdict.warn{border-left-color:var(--warn);background:var(--warn-bg)}
.verdict h2{margin:0;font-size:21px}.verdict p{margin:6px 0 0;color:var(--text)}
.tone{white-space:nowrap}.tone.ok{color:var(--accent)}.tone.bad{color:var(--bad)}
.tone.warn{color:var(--warn)}.tone.info{color:var(--muted)}
.findings{list-style:none;padding:0;display:grid;gap:10px;max-width:900px}
.findings li{border:1px solid var(--border);border-radius:10px;padding:12px 16px}
.skip{position:absolute;left:-200vw}
.skip:focus{left:24px;top:12px;background:var(--bg);padding:8px;z-index:5}
td code{overflow-wrap:anywhere}
.tools{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:8px 0}
.tools input{font:inherit;padding:8px 12px;border:1px solid var(--border);border-radius:8px;
background:var(--bg);color:var(--text);min-height:44px;min-width:min(320px,100%)}
th button{all:unset;cursor:pointer;display:inline-flex;gap:6px;align-items:center;
min-height:32px;color:inherit;font-weight:700}
th button:focus-visible{outline:3px solid var(--accent);outline-offset:2px;border-radius:4px}
th button span{opacity:.6}[aria-sort] button span{opacity:1}
.count{font-size:13px;color:var(--muted)}
@media(max-width:640px){body{margin:24px auto;padding:0 16px}.cards{gap:12px}
.card{min-width:0;flex-basis:100%}.dimension{flex-wrap:wrap}.audit-control{padding:10px 14px}
.change-table{display:none}.change-cards{display:grid;gap:16px}
.scroll table{min-width:560px}td,th{padding:8px 10px}
main .cards .card{flex-basis:calc(50% - 6px);padding:12px 14px}main .number{font-size:24px}}
@media print{:root{--bg:#fff;--surface:#fff;--surface-2:#f4f4f4;--text:#111;--muted:#222;
--border:#bbb;--accent:#064;--accent-2:#064;--bad:#8a3b00;--warn:#6a5000;--pass-bg:#fff;
--fail-bg:#fff;--warn-bg:#fff}body{margin:0;max-width:none}
.verdict,.card,.findings li,tr{break-inside:avoid}pre{max-height:none}
.scroll{overflow:visible;max-height:none;border:0}th{position:static}
.skip,.tools{display:none}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
"""

# Progressive enhancement (sortable columns, row filter), inlined from a packaged asset
# so each report stays one self-contained file; the CSP allows exactly this script.
ENHANCE = files("evalarc").joinpath("assets", "report_enhance.js").read_text(encoding="utf-8")
SCRIPT_HASH = base64.b64encode(hashlib.sha256(ENHANCE.encode()).digest()).decode()
CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; "
    f"script-src 'sha256-{SCRIPT_HASH}'; base-uri 'none'; form-action 'none'"
)

TONES = {"ok": "✓", "bad": "✗", "warn": "!", "info": "·"}


def _tone(text: object, tone: str) -> str:
    """Status text that carries a symbol as well as a color."""
    return f'<span class="tone {tone}">{TONES[tone]} {_esc(text)}</span>'


def _verdict(passed: bool | None, title: str, detail: str = "", next_step: str = "") -> str:
    """The decision first: one banner per report, announced to assistive technology."""
    tone = "pass" if passed else ("warn" if passed is None else "fail")
    symbol = {"pass": "✓", "warn": "!", "fail": "✗"}[tone]
    return (
        f'<section class="verdict {tone}" role="status" aria-label="Result">'
        f"<h2>{symbol} {_esc(title)}</h2>"
        + (f"<p>{_esc(detail)}</p>" if detail else "")
        + (f'<p class="next"><strong>Next:</strong> {_esc(next_step)}</p>' if next_step else "")
        + "</section>"
    )


def _table(label: str, headers: list[str], rows: list[list[str]]) -> str:
    """A keyboard-scrollable table; cells are pre-escaped HTML."""
    head = "".join(f'<th scope="col">{_esc(h)}</th>' for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return (
        f'<div class="scroll" tabindex="0" role="region" aria-label="{_esc(label)}">'
        f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def _findings(items: list[tuple[str, str, str]]) -> str:
    """(severity, id, message) as a list; severity is spelled out, not color-only."""
    tone = {"warning": "bad", "info": "info", "pass": "ok"}
    return (
        '<ul class="findings">'
        + "".join(
            f"<li>{_tone(severity, tone.get(severity, 'info'))} · <code>{_esc(key)}</code>"
            f"<br>{_esc(message)}</li>"
            for severity, key, message in items
        )
        + "</ul>"
    )


def render_audit(data: dict, destination: Path) -> None:
    esc = lambda value: html.escape(str(value), quote=True)  # noqa: E731
    score_text = lambda value: "unassessed" if value is None else f"{value:.3f}"  # noqa: E731
    margin_text = lambda value: "—" if value is None else str(value)  # noqa: E731
    rows = []
    fragile = [
        row
        for row in data["mutants"]
        if row.get("valid") is not False and row["killed"] and len(set(row["failing_cases"])) == 1
    ]
    for index, row in enumerate(data["mutants"]):
        margin = None if row.get("valid") is False else len(set(row["failing_cases"]))
        state = (
            "UNASSESSED"
            if row.get("valid") is False
            else ("Detected" if row["killed"] else "SURVIVED")
        )
        rows.append(
            f"<tr><td><code>{esc(row['name'])}</code></td>"
            f"<td>{esc(row['target_dimension'])}</td>"
            f"<td>{score_text(row['score'])}</td><td>{state}</td>"
            f"<td>{esc(margin_text(margin))}</td>"
            f'<td><a href="#fault-{index}">Inspect recorded cases</a></td></tr>'
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
    verdict = _verdict(
        None if data.get("valid") is False else bool(data.get("passed")),
        "Audit invalid: environment failure"
        if data.get("valid") is False
        else f"{data['killed']} of {data['total']} declared faults detected"
        + ("" if data.get("passed") else " — audit failed"),
        f"{len(fragile)} fault(s) depend on a single detecting case." if fragile else "",
        "Add cases that detect the single-case faults independently." if fragile else "",
    )
    document = (
        """<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="__CSP__">
<meta name="color-scheme" content="light dark">
<title>EvalArc · Grader audit</title>
<style>
__STYLE__
</style>
<a class="skip" href="#main">Skip to content</a><main id="main">
<div class="eyebrow">EVALARC / DEVELOPMENT AUDIT</div>
<h1>Test the grader.<br>Then trust the signal.</h1>
__VERDICT__<p>Behavioral controls for task-specific agent evaluations. Correct and faulty
submissions are evaluated against the same externally enforced contract.</p>
""".replace("__STYLE__", STYLE)
        .replace("__VERDICT__", verdict)
        .replace("__CSP__", CSP)
    )
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
        '<section class="audit-coverage" aria-labelledby="coverage-title">'
        '<h2 id="coverage-title">Which faults depend on one case?</h2>'
        f"<p><strong>{len(fragile)} of {data['total']}</strong> declared faults have "
        "exactly one distinct detecting case in the assessed records. Repeating a "
        "case under more seeds does not increase this margin. A surviving fault has "
        "margin zero; an environment failure remains unassessed.</p>"
        "<p>Margins below are derived from the saved failing case IDs. "
        "Rendering an older audit does not rerun its controls.</p></section>"
        "<h2>Does the grader detect plausible defects?</h2>"
        '<div class="scroll" tabindex="0" role="region" aria-label="Declared fault coverage">'
        "<table><thead><tr><th>Negative control</th><th>Target</th>"
        "<th>Candidate score</th><th>Result</th>"
        '<th title="Cases that caught this fault independently. One means the suite '
        'loses this fault if that case changes.">Margin</th>'
        "<th>Evidence</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )
    document += "<h2>Inspect the detecting cases</h2>"
    for index, row in enumerate(data["mutants"]):
        margin = None if row.get("valid") is False else len(set(row["failing_cases"]))
        label = (
            "unassessed"
            if margin is None
            else ("single-case dependency" if margin == 1 else f"{margin} detecting cases")
        )
        case_ids = ", ".join(sorted(set(row["failing_cases"]))) or "none"
        document += (
            f'<details class="audit-control"><summary>{esc(row["name"])} · {label}</summary>'
            f'<div id="fault-{index}"><p>Target: {esc(row["target_dimension"])}. '
            f"Detecting case IDs: {esc(case_ids)}.</p>"
        )
        cases = [
            case
            for case in row.get("evaluation", {}).get("cases", [])
            if case.get("checks", {}).get(row["target_dimension"]) is False
        ]
        if cases:
            for case in cases:
                document += (
                    f"<details><summary>{esc(case['case_id'])} · seed {esc(case['seed'])}"
                    f" · {esc(case['status'])}</summary><pre>"
                    f"{esc(json.dumps(case, ensure_ascii=False, indent=2))}</pre></details>"
                )
        else:
            document += (
                "<p>No detecting-case trace is embedded for this control. "
                "Consult the complete JSON evidence for its recorded validity and outcome.</p>"
            )
        document += "</div></details>"
    document += "<h2>Positive control</h2>" + bars
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
        "No human time horizon, model quality, or RL improvement is inferred.</footer>"
        f'</main><script data-evalarc="enhance">{ENHANCE}</script></html>'
    )
    document = document.replace("<th>", '<th scope="col">').replace(
        "<th title=", '<th scope="col" title='
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document)


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _score(value: float | None) -> str:
    return "unassessed" if value is None else f"{value:.4f}".rstrip("0").rstrip(".")


def _card(value: object, label: str, *, alert: bool = False) -> str:
    tone = " failed" if alert else ""
    return (
        f'<div class="card"><div class="number{tone}">{_esc(value)}</div>'
        f'<div class="label">{_esc(label)}</div></div>'
    )


def _page(kind: str, title: str, body: str, destination: Path) -> None:
    # Every table: column headers scoped, scroll regions reachable by keyboard.
    body = re.sub(
        r'<div class="(scroll(?: [\w-]+)*)">',
        r'<div class="\1" tabindex="0" role="region" aria-label="Scrollable table">',
        body.replace("<th>", '<th scope="col">'),
    )
    document = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta http-equiv="Content-Security-Policy" content="{CSP}">'
        '<meta name="color-scheme" content="light dark">'
        f"<title>EvalArc · {_esc(kind)}</title><style>{STYLE}</style></head><body>"
        '<a class="skip" href="#main">Skip to content</a>'
        f'<main id="main"><div class="eyebrow">EVALARC / {_esc(kind.upper())}</div>'
        f"<h1>{_esc(title)}</h1>{body}</main>"
        f'<script data-evalarc="enhance">{ENHANCE}</script></body></html>'
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document, encoding="utf-8")


def _metadata(data: dict) -> str:
    labels = (
        ("candidate_sha256", "Candidate SHA-256"),
        ("grader_sha256", "Grader SHA-256"),
        ("cases_sha256", "Cases SHA-256"),
        ("created_at", "Created"),
    )
    parts = [f"{label}: {_esc(data[key])}" for key, label in labels if key in data]
    parts.append(f"Seeds: {_esc(data['seeds'])}")
    parts.append(f"Runtime: {_esc(json.dumps(data['runtime'], ensure_ascii=False))}")
    return '<h2>Reproduction record</h2><p class="metadata">' + "<br>".join(parts) + "</p>"


def render_evaluation(data: dict, destination: Path) -> None:
    task = data["task"]
    cases = data["cases"]
    passed = sum(case["passed"] for case in cases)
    status = (
        "UNASSESSED" if not data["valid"] else ("RESOLVED" if data["resolved"] else "INCOMPLETE")
    )
    failing = len(cases) - passed
    body = _verdict(
        data["resolved"] if data["valid"] else None,
        {
            "RESOLVED": "Resolved: every case passed",
            "INCOMPLETE": f"Not resolved: {failing} of {len(cases)} case(s) failed",
            "UNASSESSED": "Unassessed: the environment failed",
        }[status],
        "A partial score is not acceptance; full resolution requires every case to pass."
        if status == "INCOMPLETE"
        else "",
        {
            "RESOLVED": "",
            "INCOMPLETE": "Open the failing cases below and read their evidence.",
            "UNASSESSED": "Fix the runtime (see evalarc doctor) and rerun.",
        }[status],
    )
    body += (
        f"<p>{_esc(task['domain'])} · task v{_esc(task['version'])} · {_esc(status)}</p>"
        '<div class="cards">'
        + _card(_score(data["score"]), "weighted score")
        + _card(f"{passed}/{len(cases)}", "cases passed", alert=not data["resolved"])
        + _card(data["runtime"]["backend"], "execution backend")
        + "</div>"
    )
    if not data["valid"]:
        body += "<p>Environment failure: this evaluation has no assessed aggregate score.</p>"
    body += (
        '<h2>Dimension results</h2><div class="scroll"><table><thead><tr>'
        "<th>Dimension</th><th>Score</th><th>Passed / assessed</th><th>Weight</th>"
        "</tr></thead><tbody>"
    )
    for name, group in data["dimensions"].items():
        body += (
            f"<tr><td>{_esc(name)}</td><td>{_score(group['score'])}</td>"
            f"<td>{group['passed']}/{group['assessed']}</td><td>{group['weight']:.0%}</td></tr>"
        )
    body += (
        '</tbody></table></div><h2>Case results</h2><div class="scroll"><table><thead><tr>'
        "<th>Case</th><th>Seed</th><th>Status</th><th>Failed checks</th><th>Host seconds</th>"
        "</tr></thead><tbody>"
    )
    for index, case in enumerate(cases):
        failed = [name for name, value in case["checks"].items() if value is False]
        body += (
            f'<tr><td><a href="#case-{index}">{_esc(case["case_id"])}</a></td>'
            f'<td>{case["seed"]}</td><td class="{_esc(case["status"])}">'
            f"{_esc(case['status'])}</td>"
            f"<td>{_esc(', '.join(failed) or '—')}</td>"
            f"<td>{case['duration_seconds']:.3f}</td></tr>"
        )
    body += "</tbody></table></div><h2>Case evidence</h2>"
    for index, case in enumerate(cases):
        body += (
            f'<details id="case-{index}"><summary>{_esc(case["case_id"])} · '
            f"seed {case['seed']} · {_esc(case['status'])}</summary>"
            f"<pre>{_esc(json.dumps(case, ensure_ascii=False, indent=2))}</pre></details>"
        )
    body += _metadata(data)
    body += (
        '<p><a href="evaluation.json">Complete JSON evidence</a></p>'
        "<footer>Observed task outcomes only. Full resolution requires every check to pass. "
        "Host durations include execution overhead and are not agent completion-time baselines. "
        "Unknown model cost and token usage remain null.</footer>"
    )
    _page("Evaluation", task["id"], body, destination)


def render_comparison(data: dict, destination: Path) -> None:
    regressed = len(data["regressions"])
    body = _verdict(
        not regressed,
        f"{regressed} check(s) regressed" if regressed else "No check regressed",
        f"Score change {data['score_delta']:+.4f}; {data['current_failed_cases']} current "
        "case(s) still fail.",
        "Inspect the regressed checks before accepting the change." if regressed else "",
    )
    body += (
        f"<p>{_esc(data['task']['id'])} · matched task, grader, cases, and runtime</p>"
        '<div class="cards">'
        + _card(_score(data["baseline"]["score"]), "baseline score")
        + _card(_score(data["current"]["score"]), "current score")
        + _card(f"{data['score_delta']:+.4f}", "score change", alert=data["score_delta"] < 0)
        + _card(len(data["regressions"]), "regressed checks", alert=bool(data["regressions"]))
        + "</div>"
        f"<p>{len(data['improvements'])} improved checks. "
        f"{data['current_failed_cases']} current cases still fail. "
        "No regression is not the same as full resolution.</p>"
    )
    if data["case_transitions"]:
        body += (
            '<h2>Changed outcomes</h2><div class="scroll change-table"><table><thead><tr>'
            "<th>Case</th><th>Seed</th><th>Before → after</th>"
            "<th>Regressed checks</th><th>Improved checks</th></tr></thead><tbody>"
        )
        for row in data["case_transitions"]:
            body += (
                f"<tr><td>{_esc(row['case_id'])}</td><td>{row['seed']}</td>"
                f"<td>{_esc(row['before'])} → {_esc(row['after'])}</td>"
                f"<td>{_esc(', '.join(row['regressed_checks']) or '—')}</td>"
                f"<td>{_esc(', '.join(row['improved_checks']) or '—')}</td></tr>"
            )
        body += "</tbody></table></div>"
        body += '<div class="change-cards">'
        for row in data["case_transitions"]:
            body += (
                f'<article class="change-card"><h3>{_esc(row["case_id"])}</h3>'
                f"<p>Seed {row['seed']} · {_esc(row['before'])} → {_esc(row['after'])}</p>"
                f'<p class="failed">Regressed: '
                f"{_esc(', '.join(row['regressed_checks']) or 'none')}</p>"
                f"<p>Improved: {_esc(', '.join(row['improved_checks']) or 'none')}</p></article>"
            )
        body += "</div>"
    else:
        body += "<p>All observed check outcomes are unchanged.</p>"
    body += _metadata(data)
    for key in ("baseline", "current"):
        body += (
            f'<p class="metadata">{key.title()} candidate: '
            f"{_esc(data[key]['candidate_sha256'])}</p>"
        )
    body += (
        '<p><a href="comparison.json">Comparison JSON</a> · '
        '<a href="baseline.json">Baseline evidence</a> · '
        '<a href="current.json">Current evidence</a></p>'
        f"<footer>{_esc(data['interpretation'])}</footer>"
    )
    _page("Comparison", "Compare outcomes.", body, destination)


def render_repetition(data: dict, destination: Path) -> None:
    body = _verdict(
        data["all_attempts_resolved"] if data["valid"] else None,
        f"{data['resolved_attempts']} of {data['requested_attempts']} attempt(s) resolved",
        f"{data['variable_checks']} check(s) changed outcome between attempts."
        if data["variable_checks"]
        else "Every check had the same outcome in every attempt.",
        "Read the varying checks: variation is the agent, the task or the environment."
        if data["variable_checks"]
        else "",
    )
    body += (
        f"<p>{_esc(data['task']['id'])} · {_esc(data['status'].upper())} · "
        "one frozen candidate, fixed cases, fresh state per attempt</p>"
        '<div class="cards">'
        + _card(
            f"{data['resolved_attempts']}/{data['requested_attempts']}",
            "requested attempts resolved",
            alert=not data["all_attempts_resolved"],
        )
        + _card(_score(data["mean_score"]), "mean score of assessed attempts")
        + _card(
            data["variable_checks"],
            "checks with varying outcomes",
            alert=bool(data["variable_checks"]),
        )
        + "</div>"
        f"<p>Requested: {data['requested_attempts']}. Completed: {data['completed_attempts']}. "
        f"Assessed: {data['assessed_attempts']}. Invalid: {data['invalid_attempts']}. "
        f"Assessed score range: {_score(data['min_score'])}–{_score(data['max_score'])}.</p>"
    )
    if not data["valid"]:
        body += (
            "<p><strong>Invalid or incomplete run.</strong> Repetition stops after an invalid "
            "attempt. Missing attempts are not treated as passes or failures.</p>"
        )
    body += "<h2>Outcomes by case</h2>"
    for row in data["cases"]:
        body += (
            '<article class="change-card">'
            f"<h3>{_esc(row['case_id'])} · seed {row['seed']}</h3>"
            f"<p>{row['passed']}/{row['assessed']} assessed attempts passed"
            f" · {row['unassessed']} unassessed"
            + (" · <strong>variable case outcome</strong>" if row["variable"] else "")
            + "</p><details><summary>Check pass rates</summary><ul>"
        )
        for name, check in row["checks"].items():
            rate = "unassessed" if check["pass_rate"] is None else f"{check['pass_rate']:.1%}"
            body += (
                f"<li>{_esc(name)}: {check['passed']}/{check['assessed']} ({rate})"
                + (" · <strong>variable</strong>" if check["variable"] else "")
                + "</li>"
            )
        body += "</ul></details></article>"
    body += "<h2>Every attempt</h2><ul>"
    for row in data["attempts"]:
        prefix = f"attempts/{row['attempt']:04d}"
        body += (
            f'<li><a href="{prefix}/index.html">Attempt {row["attempt"]}</a> · '
            f"{_esc(row['status'])} · score {_score(row['score'])} · "
            f'<a href="{prefix}/evaluation.json">JSON evidence</a></li>'
        )
    body += "</ul>" + _metadata(data)
    body += (
        '<p><a href="repetition.json">Repetition summary JSON</a> · '
        '<a href="events.jsonl">Progress events</a></p>'
        f"<footer>{_esc(data['interpretation'])} Case and check denominators count their "
        "assessed observations, including those in an otherwise invalid attempt. "
        "Repeated success on these cases does not establish general agent reliability.</footer>"
    )
    _page("Repeatability", "See every attempt.", body, destination)


def render_suite(data: dict, destination: Path) -> None:
    body = _verdict(
        data["accepted"] if data["valid"] else None,
        f"{data['accepted_jobs']} of {data['total_jobs']} job gate(s) accepted",
        f"{data['invalid_jobs']} invalid job(s)." if data["invalid_jobs"] else "",
        "" if data["accepted"] else "Open the rejected jobs below to see which rule failed.",
    )
    body += (
        f"<p>{_esc(data['name'])} · {_esc(data['status'].upper())}</p>"
        '<div class="cards">'
        + _card(
            f"{data['accepted_jobs']}/{data['total_jobs']}",
            "job gates accepted",
            alert=not data["accepted"],
        )
        + _card(data["fully_resolved_jobs"], "jobs with every attempt resolved")
        + _card(data["invalid_jobs"], "invalid jobs", alert=bool(data["invalid_jobs"]))
        + "</div><p>Each job has its own task, budget, and acceptance rules. "
        "Scores stay within their task; there is no cross-domain average.</p>"
        "<h2>Job decisions</h2>"
    )
    for row in data["jobs"]:
        observed = row["observed"]
        gate_status = (
            "UNASSESSED"
            if not row["decision"]["valid"]
            else ("ACCEPTED" if row["decision"]["accepted"] else "REJECTED")
        )
        body += (
            '<article class="change-card">'
            f'<h3><a href="jobs/{_esc(row["id"])}/index.html">{_esc(row["id"])}</a></h3>'
            f"<p>{_esc(row['task']['id'])} · {_esc(row['task']['domain'])} · "
            f"Gate: <strong>{gate_status}</strong></p>"
            f"<p>Mean assessed score: {_score(observed['mean_score'])}. "
            f"Resolved attempts: {observed['resolved_attempts']}/{observed['requested_attempts']}. "
            f"Completed: {observed['completed_attempts']}. Invalid: {observed['invalid_attempts']}."
            "</p>"
        )
        if row["decision"]["accepted"] and not row["fully_resolved"]:
            body += (
                "<p><strong>Gate accepted with unresolved task outcomes.</strong> "
                "The configured thresholds permit partial results.</p>"
            )
        for reason in row["decision"]["reasons"]:
            body += f'<p class="failed">{_esc(reason)}</p>'
        body += (
            f"<details><summary>Acceptance rules and checks</summary><pre>"
            f"{_esc(json.dumps({'gate': row['gate'], 'decision': row['decision']}, indent=2))}"
            "</pre></details></article>"
        )
    body += (
        '<h2>Run record</h2><p class="metadata">'
        f"Manifest SHA-256: {_esc(data['manifest_sha256'])}<br>"
        f"Created: {_esc(data['created_at'])}<br>"
        f"Host wall seconds: {data['duration_seconds']:.3f}</p>"
        '<p><a href="suite.json">Suite JSON</a> · '
        '<a href="suite.toml">Original configuration</a> · '
        '<a href="plan.json">Resolved plan</a> · '
        '<a href="junit.xml">JUnit acceptance gates</a> · '
        '<a href="events.jsonl">Progress events</a></p>'
        f"<footer>{_esc(data['interpretation'])} JUnit contains one test per job gate, "
        "rather than one test per individual task case.</footer>"
    )
    _page("Suite", "Every job, explicit criteria.", body, destination)

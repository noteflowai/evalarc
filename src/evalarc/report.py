"""Offline HTML audit reports with no scripts or remote assets."""

from __future__ import annotations

import html
import json
from pathlib import Path

STYLE = """
:root{color-scheme:dark;font:16px/1.6 system-ui,sans-serif;background:#101618;color:#e0ece7}
body{max-width:1080px;margin:60px auto;padding:0 24px}
.eyebrow{color:#86dbaf;letter-spacing:.18em;font-size:12px;font-weight:700}
h1{font-size:clamp(32px,6vw,64px);letter-spacing:-.045em;line-height:1.1;margin:16px 0}
p{color:#acbeb5;max-width:760px}.cards{display:flex;gap:20px;flex-wrap:wrap;margin:36px 0}
.card{border:1px solid #33463d;border-radius:12px;padding:18px 26px;flex:1;min-width:150px}
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
a{color:#96e8b9}.failed,.agent_error,.environment_error{color:#edb68d}
.passed{color:#96e8b9}td{overflow-wrap:anywhere}
.scroll table{min-width:680px}td:first-child{min-width:170px;overflow-wrap:normal}
.change-cards{display:none}.change-card{border:1px solid #33463d;border-radius:12px;padding:16px}
.change-card h3{font-size:16px;margin:0;overflow-wrap:anywhere}.change-card p{margin:10px 0 0}
@media(max-width:640px){.change-table{display:none}.change-cards{display:grid;gap:16px}}
"""


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
__STYLE__
</style>
<div class="eyebrow">EVALARC / DEVELOPMENT AUDIT</div>
<h1>Test the grader.<br>Then trust the signal.</h1>
<p>Behavioral controls for task-specific agent evaluations. Correct and faulty
submissions are evaluated against the same externally enforced contract.</p>
""".replace("__STYLE__", STYLE)
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
    document = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">"
        f"<title>EvalArc · {_esc(kind)}</title><style>{STYLE}</style></head><body>"
        f'<div class="eyebrow">EVALARC / {_esc(kind.upper())}</div>'
        f"<h1>{_esc(title)}</h1>{body}</body></html>"
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
    body = (
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
    body = (
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
    body = (
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
    body = (
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

"""Offline presentation of same-record judge agreement with explicit denominators."""

from __future__ import annotations

from pathlib import Path

from evalarc.trace_report import STYLE, badge, escape, pretty

SCRIPT = """
const search = document.querySelector('#search');
const buttons = [...document.querySelectorAll('[data-filter]')];
let filter = 'all';
function update() {
  let count = 0;
  document.querySelectorAll('article[data-state]').forEach(card => {
    const matches = filter === 'all' || (filter === 'disagreement'
      ? card.dataset.flip === 'true' : card.dataset.state === filter);
    card.hidden = !matches || !card.textContent.toLowerCase().includes(search.value.toLowerCase());
    if (!card.hidden) count++;
  });
  document.querySelector('#filter-status').textContent = count + ' targets shown';
}
buttons.forEach(button => button.addEventListener('click', () => {
  filter = button.dataset.filter;
  buttons.forEach(other => other.setAttribute('aria-pressed', String(other === button)));
  update();
}));
search.addEventListener('input', update);
update();
"""


def render(record: dict, target: Path) -> None:
    cards = []
    for case in record["cases"]:
        for row in case["targets"]:
            observations = []
            for index, observation in enumerate(row["observations"]):
                assessed = observation["status"] == "assessed"
                value = (
                    observation["value"]
                    if row["rating"]["kind"] == "numeric"
                    else observation["label"]
                )
                verdict = (
                    ("accepted" if observation["accepted"] else "rejected")
                    if assessed
                    else observation["status"]
                )
                observations.append(
                    f'<tr><th scope="row"><a href="inputs/{index + 1:04d}.json" download>'
                    f"{escape(observation['run_id'])}</a></th>"
                    f'<td data-label="Value">{escape(value) if assessed else "—"}</td>'
                    f'<td data-label="Configured gate">{badge(verdict)}</td>'
                    f'<td data-label="Explanation">{escape(observation["explanation"])}'
                    f"<small>{escape(observation['error'] or '')}</small></td></tr>"
                )
            state_label = {
                "same_gate": "Same observed gate",
                "disagreement": "Gate disagreement",
                "incomplete": "Incomplete judgments",
                "not_applicable": "Not applicable",
            }[row["state"]]
            values = ", ".join(str(v) for v in row["observed_values"]) or "None"
            observation_note = (
                "No skill target is expected under the declared complete observation."
                if row["state"] == "not_applicable"
                else f"{row['assessed']}/{row['expected']} expected judgments assessed · "
                f"{row['passed']} pass · {row['rejected']} reject · "
                f"{row['unassessed']} unassessed"
            )
            flip_note = (
                '<p class="rejected">Both pass and reject observed'
                + ("; missing judgments also remain." if row["unassessed"] else ".")
                + "</p>"
                if row["observed_gate_disagreement"]
                else ""
            )
            varied = "yes" if row["observed_score_disagreement"] else "not observed"
            target_identity = {
                "session_id": case["session_id"],
                "trace_id": row["trace_id"],
                "span_id": row["span_id"],
                "revision": row["revision"],
                "rating": row["rating"],
                "case_gates": case["case_gates"],
            }
            cards.append(
                f'<article id="target-{len(cards)}" data-state="{row["state"]}" '
                f'data-flip="{str(row["observed_gate_disagreement"]).lower()}">'
                f'<div class="case-top"><h2>{escape(case["case_id"])}</h2>'
                f'<span class="badge">{state_label}</span></div><p>{escape(case["goal"])}</p>'
                f"<h3>{escape(row['evaluator'])}</h3>"
                f'<p class="muted">{escape(observation_note)}</p>{flip_note}'
                f"<p>Observed values: <strong>{escape(values)}</strong>. "
                f"Score variation: {varied}"
                ".</p>"
                '<div class="table-scroll" role="region" tabindex="0" '
                'aria-label="Repeated judgments"><table class="scores">'
                "<caption>Same recording, separate saved judgments</caption><thead><tr>"
                '<th scope="col">Judgment / source</th><th scope="col">Value</th>'
                '<th scope="col">Configured gate</th><th scope="col">Explanation</th>'
                f"</tr></thead><tbody>{''.join(observations)}</tbody></table></div>"
                "<details><summary>Frozen target, rating rules and overall case gates</summary>"
                f"<pre>{pretty(target_identity)}</pre>"
                "</details></article>"
            )
    summary = record["summary"]
    stats = "".join(
        f"<div><strong>{summary[key]}</strong><span>{label}</span></div>"
        for key, label in (
            ("repetitions", "Saved judgments per target"),
            ("gate_disagreements", "Targets with observed gate disagreement"),
            ("incomplete_targets", "Targets with missing assessments"),
        )
    )
    filters = "".join(
        f'<button type="button" data-filter="{state}" '
        f'aria-pressed="{str(state == "all").lower()}">{label}</button>'
        for state, label in (
            ("all", "All"),
            ("disagreement", "Gate disagreement"),
            ("incomplete", "Incomplete"),
            ("same_gate", "Same gate"),
        )
    )
    sources = "".join(
        f'<li><a href="{source["file"]}" download>{escape(source["run_id"])}</a>'
        f"<small>SHA-256: {source['sha256']}</small></li>"
        for source in record["sources"]
    )
    configuration = {key: record[key] for key in ("configuration", "evaluators")}
    target.write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="referrer" content="no-referrer">'
        "<title>EvalArc · Judge Stability</title>"
        f"<style>{STYLE}"
        "article,li,h2,h3{overflow-wrap:anywhere}.disagreement{color:#ffbb9a}"
        "@media(max-width:480px){.scores th[scope=row]{grid-column:1 / -1;"
        "display:block;border:0;overflow-wrap:anywhere}.stats{grid-template-columns:1fr}}"
        '</style></head><body><a class="skip" href="#targets">Skip to judgments</a>'
        "<header><strong>EvalArc / Judge Stability</strong>"
        '<a href="https://github.com/noteflowai/evalarc/blob/main/docs/judge-stability.md">'
        "Source &amp; input guide</a></header><main>"
        '<p class="eyebrow">One fixed recording · repeated judgments</p>'
        "<h1>Same trace.<br><em>Same verdict?</em></h1>"
        f"<p>{badge(record['provenance_kind'])} "
        f"{escape(record['sources'][0]['provenance']['description'])}</p>"
        "<p>Separate a changing score, a flipped acceptance decision and an unavailable "
        "judgment. All-reject agreement is still failure; repeated agreement is not accuracy.</p>"
        f'<p class="scope">{escape(record["scope"])}</p><div class="stats">{stats}</div>'
        f"<p>{summary['complete_targets']}/{summary['required_targets']} required targets "
        f"have all judgments; {summary['score_disagreements']} show observed score variation. "
        f"{summary['all_rejected_targets']} were rejected in every judgment. "
        f"{summary['not_applicable_targets']} are not applicable and excluded from coverage.</p>"
        '<div class="links"><a href="stability.json" download>Download stability JSON</a></div>'
        '<details class="panel"><summary>Import your own saved judgments</summary>'
        "<p>Save each repeated evaluation of the same recording as a Trace Workbench input "
        "with a distinct run_id. Freeze evaluator revisions and configuration. Agent reruns "
        "with new spans belong in a separate execution comparison.</p>"
        "<pre>evalarc trace-stability judge-1.json judge-2.json --output runs/judge-review\n"
        "evalarc trace-stability-verify runs/judge-review</pre></details>"
        '<section id="targets" aria-label="Judge observations">'
        '<div class="tools" role="group" aria-label="Filter judgment targets">'
        f'{filters}<label for="search">Search case, evaluator or explanation</label>'
        '<input id="search" type="search" placeholder="Find a judgment…"></div>'
        '<p id="filter-status" role="status" aria-live="polite"></p>'
        f"{''.join(cards)}</section>"
        '<details class="panel"><summary>Preserved input files and recording identity</summary>'
        f"<ul>{sources}</ul><p>Fixed recording SHA-256:</p>"
        f"<pre>{record['fixed_record_sha256']}</pre>"
        f"<pre>{pretty(configuration)}</pre>"
        "</details></main><footer>Offline descriptive review · No calibration, confidence "
        f"interval or population reliability claim</footer><script>{SCRIPT}</script></body></html>",
        encoding="utf-8",
    )

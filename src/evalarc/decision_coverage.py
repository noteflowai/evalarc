"""Held-out error versus coverage for recorded choice decisions at an abstention threshold.

The command reviews saved, labelled decisions offline. A threshold t is chosen on
calibration records only and then reported on held-out records. Invalid responses
are kept as their own outcome: never answered and never counted as wrong.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from bisect import bisect_left
from pathlib import Path

from evalarc.artifacts import new_json, new_run
from evalarc.records import numeric
from evalarc.trace_report import STYLE, badge, escape

SCHEMA = "evalarc.decision-records.v1"
REPORT_SCHEMA = "evalarc.decision-coverage.v1"
MAX_BYTES = 4 * 1024 * 1024
MAX_RECORDS = 10_000
MAX_OPTIONS = 8
SPLITS = ("calibration", "held_out")
SPLIT_LABELS = {"calibration": "Calibration", "held_out": "Held-out"}
PROVENANCE_KINDS = ("synthetic", "recorded")
SUM_TOLERANCE = 1e-6
MAX_SWEEP_ROWS = 20
MAX_RECORD_ROWS = 1000
OUTCOME_ORDER = ("wrong", "invalid", "abstained", "correct")
EXIT_CODES = {
    "met": 0,
    "no_target": 0,
    "exceeded": 1,
    "no_threshold": 1,
    "no_heldout_answers": 1,
}
THRESHOLD_RULE = (
    "Candidates are t=0 (answer every valid record) and every distinct valid calibration "
    "confidence. With a target E, the smallest candidate with at least one calibration "
    "answer and calibration selective error <= E is chosen; held-out labels never "
    "influence the choice."
)
_MISSING = object()

EXTRA_STYLE = """
h1{font-size:clamp(1.9rem,4.6vw,3.1rem);overflow-wrap:anywhere;margin-top:12px}
.state-line{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:32px 0 0}
.met,.correct{color:#c4efaa}.exceeded,.wrong{color:#ffbb9a}
.no_threshold,.no_heldout_answers,.invalid{color:#f0d48b}.no_target,.abstained{color:#b5c0b7}
.stats span{display:block;color:#b5c0b7}.stats small{margin-top:4px}
code{overflow-wrap:anywhere}td,th{overflow-wrap:anywhere}
.coverage td{min-width:110px}.coverage td:first-child{min-width:150px}
.decisions td:first-child{min-width:200px}
.marker{display:inline-block;margin-left:6px;padding:1px 8px;border:1px solid #708275;
border-radius:8px;font-size:.78rem;color:#b5c0b7}
.chosen-marker{border-color:#c4efaa;color:#c4efaa}tr.chosen td{background:#1d2a24}
.scores tr[hidden]{display:none}
@media(max-width:480px){.stats{grid-template-columns:1fr}}
"""

SCRIPT = """
const search = document.querySelector('#search');
const buttons = [...document.querySelectorAll('[data-filter]')];
const rows = [...document.querySelectorAll('tr[data-outcome]')];
const statusLine = document.querySelector('#filter-status');
let filter = 'all';
function update() {
  const query = search.value.trim().toLowerCase();
  let count = 0;
  rows.forEach(row => {
    row.hidden = !(filter === 'all' || row.dataset.outcome === filter)
      || !row.textContent.toLowerCase().includes(query);
    if (!row.hidden) count++;
  });
  statusLine.textContent = 'Showing ' + count + ' of ' + statusLine.dataset.total
    + '; all records in decisions.json'
    + (count === 0 ? '. No rendered record matches; clear the search or choose All.' : '');
}
buttons.forEach(button => button.addEventListener('click', () => {
  filter = button.dataset.filter;
  buttons.forEach(other => other.setAttribute('aria-pressed', String(other === button)));
  update();
}));
search.addEventListener('input', update);
"""


def _fail(message: str) -> None:
    raise ValueError(f"invalid decision records: {message}")


def _text(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _kind(value: object) -> str:
    if isinstance(value, bool):
        return "Boolean"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    return type(value).__name__


def _unique_object(pairs: list) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(
                f"invalid decision records: duplicate JSON key {key!r}; keep one value per key"
            )
        result[key] = value
    return result


def _no_constant(name: str) -> None:
    raise ValueError(f"invalid decision records: {name} is not valid JSON; use finite numbers")


def load(path: Path) -> tuple:
    """Read strict JSON: regular file, 4 MiB, no duplicate keys, no NaN/Infinity."""
    if not path.is_file():
        raise ValueError(f"cannot read records file: {path} is not a regular file")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError(f"records file {path} is larger than 4 MiB; split or trim it")
    data = path.read_bytes()
    if len(data) > MAX_BYTES:
        raise ValueError(f"records file {path} is larger than 4 MiB; split or trim it")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("invalid decision records: the file must be UTF-8 JSON") from None
    try:
        document = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_no_constant)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid decision records: not valid JSON ({error})") from None
    return document, data


def parse_max_error(text: object) -> float | None:
    if text is None:
        return None
    try:
        value = float(str(text))
    except ValueError:
        raise ValueError(f"--max-error must be a number from 0 to 1, got {text!r}") from None
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"--max-error must be a finite number from 0 to 1, got {text!r}")
    return value


def _invalid(reason: str) -> dict:
    return {"valid": False, "reason": reason, "prediction": None, "confidence": None}


def assess(response: object, options: list) -> dict:
    """Classify one response; malformed responses become invalid rows, never exceptions."""
    if response is _MISSING:
        return _invalid("response is missing; supply a distribution or an error")
    if not isinstance(response, dict):
        return _invalid(
            f"response is a {_kind(response)}, not an object with distribution or error"
        )
    keys = set(response)
    if keys == {"error"}:
        error = response["error"]
        if not _text(error):
            return _invalid("response.error must be a non-empty string")
        return _invalid(f"provider error: {error}")
    if keys != {"distribution"}:
        return _invalid(
            "response must contain exactly one of distribution or error; got keys: "
            + (", ".join(sorted(str(key) for key in keys)) or "none")
        )
    distribution = response["distribution"]
    if not isinstance(distribution, dict):
        return _invalid("response.distribution must be an object of option probabilities")
    for option, probability in distribution.items():
        if option not in options:
            return _invalid(f"distribution names undeclared option {option!r}")
        if not numeric(probability):
            return _invalid(
                f"probability for {option!r} is {json.dumps(probability)}, not a finite number"
            )
        if not 0 <= probability <= 1:
            return _invalid(f"probability for {option!r} is {probability}, outside 0..1")
    total = math.fsum(distribution.values())
    if abs(total - 1) > SUM_TOLERANCE:
        return _invalid(f"probabilities sum to {total:.6g}, not 1 within 1e-6")
    probabilities = [float(distribution.get(option, 0)) for option in options]
    confidence = max(probabilities)
    # Ties resolve to the option declared first.
    prediction = options[probabilities.index(confidence)]
    return {"valid": True, "reason": None, "prediction": prediction, "confidence": confidence}


def _questions(document: dict) -> dict:
    questions = document.get("questions")
    if not isinstance(questions, dict) or not questions:
        _fail("questions must be a non-empty object keyed by question ID")
    result = {}
    for qid, spec in questions.items():
        if not _text(qid):
            _fail("question IDs must be non-empty strings")
        if not isinstance(spec, dict):
            _fail(f"question {qid!r} must be an object")
        if spec.get("type") != "choice":
            _fail(
                f"question {qid!r} has type {spec.get('type')!r}; "
                'only "choice" questions are supported'
            )
        options = spec.get("options")
        if not isinstance(options, list) or not 1 <= len(options) <= MAX_OPTIONS:
            _fail(f"question {qid!r} needs 1 to {MAX_OPTIONS} options")
        if not all(_text(option) for option in options):
            _fail(f"question {qid!r} options must be non-empty strings")
        if len(set(options)) != len(options):
            _fail(f"question {qid!r} options must be unique")
        result[qid] = options
    return result


def _records(document: dict, questions: dict) -> list:
    records = document.get("records")
    if not isinstance(records, list):
        _fail("records must be a list")
    if len(records) > MAX_RECORDS:
        _fail(f"{len(records)} records exceed the limit of {MAX_RECORDS}; split the file")
    seen: set = set()
    rows = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            _fail(f"records[{index}] must be an object")
        rid = record.get("id")
        if not _text(rid):
            _fail(f"records[{index}].id must be a non-empty string")
        if rid in seen:
            _fail(f"duplicate record ID {rid!r}; record IDs must be unique")
        seen.add(rid)
        qid = record.get("question")
        if not isinstance(qid, str) or qid not in questions:
            _fail(f"record {rid!r} names unknown question {qid!r}")
        split = record.get("split")
        if not isinstance(split, str) or split not in SPLITS:
            _fail(f"record {rid!r} has split {split!r}; use calibration or held_out")
        label = record.get("label")
        if not isinstance(label, str) or label not in questions[qid]:
            _fail(f"record {rid!r} has label {label!r} outside the options of {qid!r}")
        assessment = assess(record.get("response", _MISSING), questions[qid])
        rows.append({"id": rid, "question": qid, "split": split, "label": label, **assessment})
    for split in SPLITS:
        if not any(row["split"] == split for row in rows):
            _fail(f"no {split} records; both calibration and held_out records are required")
    return rows


class _Split:
    """Sorted confidences with suffix wrong counts for fast threshold sweeps."""

    def __init__(self, rows: list) -> None:
        self.total = len(rows)
        self.invalid = sum(1 for row in rows if not row["valid"])
        valid = sorted(
            (row["confidence"], row["prediction"] != row["label"]) for row in rows if row["valid"]
        )
        self.confidences = [confidence for confidence, _ in valid]
        self.wrong_from = [0] * (len(valid) + 1)
        for position in range(len(valid) - 1, -1, -1):
            self.wrong_from[position] = self.wrong_from[position + 1] + int(valid[position][1])

    def at(self, threshold: float) -> dict:
        start = bisect_left(self.confidences, threshold)
        answered = len(self.confidences) - start
        wrong = self.wrong_from[start]
        return {
            "total": self.total,
            "answered": answered,
            "correct": answered - wrong,
            "wrong": wrong,
            "abstained": len(self.confidences) - answered,
            "invalid": self.invalid,
            "coverage": answered / self.total,
            "selective_error": wrong / answered if answered else None,
            "wrong_rate_all": wrong / self.total,
        }


def _outcome(row: dict, threshold: float) -> str:
    if not row["valid"]:
        return "invalid"
    if row["confidence"] < threshold:
        return "abstained"
    return "correct" if row["prediction"] == row["label"] else "wrong"


def _fixed(value: float) -> str:
    if value == 0:
        return "0"
    text = f"{value:.2f}"
    return text if float(text) == value else f"{value:.6g}"


def _pct(value: float) -> str:
    return f"{value:.0%}"


def headline(state: str, row: dict, max_error: float | None) -> str:
    if state == "no_target":
        return "No target set; records classified at baseline t=0"
    target = _fixed(max_error)
    if state == "no_threshold":
        return (
            f"No calibration threshold reaches error {target}; records classified at baseline t=0"
        )
    threshold = _fixed(row["threshold"])
    if state == "no_heldout_answers":
        return f"No held-out record reaches t={threshold}; target {target} cannot be validated"
    held = row["held_out"]
    return (
        f"Held-out error {held['selective_error']:.2f} at {_pct(held['coverage'])} coverage "
        f"(t={threshold}); target {target} {state}"
    )


def _scope(kind: str) -> str:
    origin = (
        "Synthetic data: authored decisions, not provider output."
        if kind == "synthetic"
        else "Recorded data supplied by you; EvalArc cannot authenticate who produced it."
    )
    return (
        f"{origin} Confidence is the largest reported probability; confidence is not "
        "calibration. No provider accuracy is shown: these metrics describe only the labels "
        "in this file, and thresholds chosen on small calibration sets are unstable."
    )


def review(document: object, data: bytes, max_error: float | None) -> dict:
    if not isinstance(document, dict):
        _fail("the top level must be a JSON object")
    if document.get("schema_version") != SCHEMA:
        _fail(f'schema_version must be "{SCHEMA}"')
    provenance = document.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("kind") not in PROVENANCE_KINDS:
        _fail('provenance.kind must be "synthetic" or "recorded"')
    if not _text(provenance.get("description")):
        _fail("provenance.description must be a non-empty string")
    model = document.get("model")
    if (
        not isinstance(model, dict)
        or not _text(model.get("id"))
        or not _text(model.get("revision"))
    ):
        _fail("model.id and model.revision must be non-empty strings")
    questions = _questions(document)
    rows = _records(document, questions)
    splits = {split: _Split([row for row in rows if row["split"] == split]) for split in SPLITS}
    candidates = sorted(
        {0.0}
        | {row["confidence"] for row in rows if row["valid"] and row["split"] == "calibration"}
    )
    sweep = [
        {"threshold": threshold, **{split: splits[split].at(threshold) for split in SPLITS}}
        for threshold in candidates
    ]
    chosen = None
    if max_error is None:
        state = "no_target"
    else:
        chosen = next(
            (
                row
                for row in sweep
                if row["calibration"]["answered"]
                and row["calibration"]["selective_error"] <= max_error
            ),
            None,
        )
        if chosen is None:
            state = "no_threshold"
        elif chosen["held_out"]["answered"] == 0:
            state = "no_heldout_answers"
        elif chosen["held_out"]["selective_error"] <= max_error:
            state = "met"
        else:
            state = "exceeded"
    review_row = chosen if chosen is not None else sweep[0]
    threshold = review_row["threshold"]
    records = [
        {
            "id": row["id"],
            "question": row["question"],
            "split": row["split"],
            "label": row["label"],
            "prediction": row["prediction"],
            "confidence": row["confidence"],
            "outcome": _outcome(row, threshold),
            "reason": row["reason"],
        }
        for row in rows
    ]
    return {
        "schema_version": REPORT_SCHEMA,
        "source": {
            "file": "input.json",
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        },
        "provenance": {"kind": provenance["kind"], "description": provenance["description"]},
        "model": {"id": model["id"], "revision": model["revision"]},
        "max_error": max_error,
        "state": state,
        "headline": headline(state, review_row, max_error),
        "chosen_threshold": chosen["threshold"] if chosen is not None else None,
        "review_threshold": threshold,
        "threshold_rule": THRESHOLD_RULE,
        "baseline": sweep[0],
        "review": {split: review_row[split] for split in SPLITS},
        "outcomes": {
            outcome: sum(1 for row in records if row["outcome"] == outcome)
            for outcome in OUTCOME_ORDER
        },
        "sweep": sweep,
        "records": records,
        "scope": _scope(provenance["kind"]),
    }


def _shown_thresholds(sweep: list, chosen: float | None) -> list:
    rest = list(range(1, len(sweep)))
    if len(rest) > MAX_SWEEP_ROWS:
        rest = sorted(
            {
                rest[round(step * (len(rest) - 1) / (MAX_SWEEP_ROWS - 1))]
                for step in range(MAX_SWEEP_ROWS)
            }
        )
    shown = {0, *rest}
    if chosen is not None:
        shown.add(next(i for i, row in enumerate(sweep) if row["threshold"] == chosen))
    return sorted(shown)


def _error_text(metrics: dict) -> str:
    error = metrics["selective_error"]
    return "—" if error is None else f"{error:.3f}"


def _error_cell(metrics: dict) -> str:
    if metrics["selective_error"] is None:
        return "—<small>no answers</small>"
    return (
        f"{metrics['selective_error']:.3f}"
        f"<small>{metrics['wrong']} wrong of {metrics['answered']}</small>"
    )


def _prediction(row: dict) -> str:
    if row["prediction"] is None:
        return "—"
    return f"{escape(row['prediction'])}<small>confidence {row['confidence']:.4g}</small>"


def _reason(row: dict, threshold: float) -> str:
    if row["outcome"] == "abstained":
        return f"confidence {row['confidence']:.4g} is below t={_fixed(threshold)}"
    return row["reason"] or "—"


def render(result: dict, target: Path) -> None:
    sweep = result["sweep"]
    chosen = result["chosen_threshold"]
    threshold = result["review_threshold"]
    shown = _shown_thresholds(sweep, chosen)
    threshold_rows = []
    for index in shown:
        row = sweep[index]
        cal, held = row["calibration"], row["held_out"]
        is_chosen = chosen is not None and row["threshold"] == chosen
        markers = '<span class="marker">baseline</span>' if index == 0 else ""
        if is_chosen:
            markers += '<span class="marker chosen-marker">chosen</span>'
        css = ' class="chosen"' if is_chosen else ""
        threshold_rows.append(
            f'<tr data-threshold="{row["threshold"]!r}"{css}>'
            f'<td data-label="Threshold t">{_fixed(row["threshold"])} {markers}</td>'
            f'<td data-label="Calibration answered">{cal["answered"]}/{cal["total"]}'
            f"<small>{_pct(cal['coverage'])} coverage</small></td>"
            f'<td data-label="Calibration selective error">{_error_cell(cal)}</td>'
            f'<td data-label="Held-out coverage">{_pct(held["coverage"])}'
            f"<small>{held['answered']}/{held['total']} answered</small></td>"
            f'<td data-label="Held-out selective error">{_error_cell(held)}</td>'
            f'<td data-label="Held-out wrong, all records">{held["wrong_rate_all"]:.3f}'
            f"<small>{held['wrong']} wrong of {held['total']}</small></td></tr>"
        )
    ordered = sorted(result["records"], key=lambda row: OUTCOME_ORDER.index(row["outcome"]))
    rendered = ordered[:MAX_RECORD_ROWS]
    total = len(result["records"])
    record_rows = "".join(
        f'<tr data-outcome="{row["outcome"]}">'
        f'<td data-label="Record">{escape(row["id"])}<small>{escape(row["question"])}</small></td>'
        f'<td data-label="Split">{SPLIT_LABELS[row["split"]]}</td>'
        f'<td data-label="Label">{escape(row["label"])}</td>'
        f'<td data-label="Prediction">{_prediction(row)}</td>'
        f'<td data-label="Outcome">{badge(row["outcome"])}</td>'
        f'<td data-label="Reason">{escape(_reason(row, threshold))}</td></tr>'
        for row in rendered
    )
    outcomes = result["outcomes"]
    filters = "".join(
        f'<button type="button" data-filter="{key}" '
        f'aria-pressed="{"true" if key == "all" else "false"}">{label} ({count})</button>'
        for key, label, count in (
            ("all", "All", total),
            ("wrong", "Wrong", outcomes["wrong"]),
            ("abstained", "Abstained", outcomes["abstained"]),
            ("invalid", "Invalid", outcomes["invalid"]),
        )
    )
    held = result["review"]["held_out"]
    calibration = result["review"]["calibration"]
    review_t = _fixed(threshold)
    stats = "".join(
        f"<div><span>{label}</span><strong>{value}</strong><small>{note}</small></div>"
        for label, value, note in (
            (
                "Held-out coverage",
                _pct(held["coverage"]),
                f"{held['answered']}/{held['total']} answered at t={review_t}",
            ),
            (
                "Held-out selective error",
                _error_text(held),
                "no held-out record answered"
                if held["selective_error"] is None
                else f"{held['wrong']} wrong of {held['answered']} answered",
            ),
            (
                "Held-out invalid responses",
                str(held["invalid"]),
                "never answered, never counted as wrong",
            ),
        )
    )
    if result["max_error"] is None:
        target_text = (
            "No --max-error target was given, so no threshold was chosen. Records are "
            "classified at the baseline t=0, which answers every valid record."
        )
    else:
        target_text = (
            f"Target: held-out selective error <= {_fixed(result['max_error'])}. The threshold "
            f"is chosen from {calibration['total']} calibration records only; held-out labels "
            "never influence it."
        )
        if chosen is None:
            target_text += " No candidate qualified, so records are classified at t=0."
    baseline = result["baseline"]["held_out"]
    baseline_text = (
        f"Baseline t=0 answers every valid record: held-out selective error "
        f"{_error_text(baseline)} at {_pct(baseline['coverage'])} coverage."
    )
    counts_text = (
        f"{outcomes['correct']} correct · {outcomes['wrong']} wrong · "
        f"{outcomes['abstained']} abstained · {outcomes['invalid']} invalid across both splits."
    )
    truncation = (
        f'<p class="muted">Only the first {MAX_RECORD_ROWS} records in review order are '
        "rendered and searchable here; filter counts and totals include every record.</p>"
        if total > MAX_RECORD_ROWS
        else ""
    )
    provenance, model = result["provenance"], result["model"]
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="referrer" content="no-referrer">'
        "<title>EvalArc · Decision Coverage</title>"
        f"<style>{STYLE}{EXTRA_STYLE}</style></head><body>"
        '<a class="skip" href="#records">Skip to records</a>'
        "<header><strong>EvalArc / Decision Coverage</strong>"
        '<a href="https://github.com/noteflowai/evalarc/blob/main/docs/decision-coverage.md">'
        "Input guide & limits</a></header><main>"
        '<p class="eyebrow">Threshold chosen on calibration · reported on held-out labels</p>'
        f'<p class="state-line">{badge(result["state"])} {badge(provenance["kind"])}</p>'
        f"<h1>{escape(result['headline'])}</h1>"
        f"<p>{escape(provenance['description'])}</p>"
        f'<p class="muted">Model {escape(model["id"])} · revision {escape(model["revision"])}'
        f" · input SHA-256 <code>{result['source']['sha256']}</code></p>"
        f'<p class="scope">{escape(result["scope"])}</p>'
        f'<div class="stats">{stats}</div>'
        f"<p>{escape(target_text)} {escape(baseline_text)} Invalid responses lower coverage "
        "but are never answered or counted as wrong.</p>"
        '<div class="links"><a href="decisions.json" download>Download decisions JSON '
        "(full sweep and every record)</a>"
        '<a href="input.json" download>Download original input</a></div>'
        '<section aria-labelledby="sweep-title">'
        '<h2 id="sweep-title">Error versus coverage by threshold</h2>'
        f'<p class="muted">{escape(THRESHOLD_RULE)}</p>'
        '<div class="table-scroll" tabindex="0" role="region" aria-label="Threshold sweep">'
        '<table class="scores coverage"><caption>Calibration chooses t; held-out reports it'
        "</caption>"
        '<colgroup><col></colgroup><colgroup span="2"></colgroup><colgroup span="3"></colgroup>'
        '<thead><tr><th scope="col" rowspan="2">Threshold t</th>'
        '<th scope="colgroup" colspan="2">Calibration</th>'
        '<th scope="colgroup" colspan="3">Held-out</th></tr>'
        '<tr><th scope="col">Answered</th><th scope="col">Selective error</th>'
        '<th scope="col">Coverage</th><th scope="col">Selective error</th>'
        '<th scope="col">Wrong / all records</th></tr></thead>'
        f"<tbody>{''.join(threshold_rows)}</tbody></table></div>"
        f'<p class="muted">Showing {len(shown)} of {len(sweep)} thresholds; '
        "full sweep in decisions.json</p></section>"
        '<section id="records" aria-labelledby="records-title">'
        f'<h2 id="records-title">Records at t={review_t}</h2>'
        f'<p class="muted">{counts_text}</p>{truncation}'
        '<p><label for="search">Search record ID, question, label or reason</label><br>'
        '<input id="search" type="search" autocomplete="off"></p>'
        f'<div class="tools" role="group" aria-label="Filter records by outcome">{filters}</div>'
        f'<p id="filter-status" role="status" aria-live="polite" data-total="{total}">'
        f"Showing {len(rendered)} of {total}; all records in decisions.json</p>"
        '<div class="table-scroll" tabindex="0" role="region" aria-label="Record outcomes">'
        '<table class="scores decisions"><caption>Wrong first, then invalid, abstained and '
        "correct</caption>"
        '<thead><tr><th scope="col">Record / question</th><th scope="col">Split</th>'
        '<th scope="col">Label</th><th scope="col">Prediction</th>'
        '<th scope="col">Outcome</th><th scope="col">Reason</th></tr></thead>'
        f"<tbody>{record_rows}</tbody></table></div></section></main>"
        "<footer>Offline descriptive review · no provider or model call · confidence is "
        "not calibration</footer>"
        f"<script>{SCRIPT}</script></body></html>"
    )
    target.write_text(page, encoding="utf-8")


def command(records: Path, output: Path, max_error_text: object) -> int:
    """Run the decision-coverage CLI; exit 0/1 by state, 2 for rejected input."""
    try:
        max_error = parse_max_error(max_error_text)
        if output.exists() or output.is_symlink():
            raise ValueError(f"output already exists: {output}; choose a new run directory")
        document, data = load(records)
        result = review(document, data, max_error)
        with new_run(output) as staged:
            (staged / "input.json").write_bytes(data)
            (staged / "input.json.sha256").write_text(
                f"{result['source']['sha256']}  input.json\n", encoding="utf-8"
            )
            new_json(staged / "decisions.json", result)
            render(result, staged / "index.html")
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        print(f"evalarc: {error}", file=sys.stderr)
        return 2
    held = result["review"]["held_out"]
    print(result["headline"])
    print(
        f"Held-out at t={_fixed(result['review_threshold'])}: {held['answered']}/{held['total']} "
        f"answered, {held['abstained']} abstained, {held['invalid']} invalid"
    )
    print(f"Report: {output / 'index.html'}")
    return EXIT_CODES[result["state"]]

"""Blind judging packets for grader spot checks and pairwise comparison with a baseline.

Two offline workflows, both split into prepare and score so EvalArc never calls a model:

* ``grader`` samples recorded attempts, stratified by the grader's verdict, and hides
  that verdict. A person (or a separately chosen judge) marks each output pass or
  fail; scoring reports agreement, Cohen's kappa, false accepts and false rejects.
  This is "read graded transcripts before trusting the grader", made measurable.
* ``pairwise`` pairs the baseline and current output for the same case and attempt,
  randomizes which one is shown as A, and hides the mapping. The judge picks A, B or
  tie; scoring unblinds, reports current-versus-baseline preference with a 95%
  interval, position bias, and whether the judge is a model under evaluation.

The folder handed to the judge (``share/``) contains no verdicts, no A/B mapping and
no seed; those live in ``key.json`` next to it.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

from evalarc.results_diff import _cell, load_results, wilson

PACKET_SCHEMA = "evalarc.judge-packet.v1"
KEY_SCHEMA = "evalarc.judge-key.v1"
VERDICTS_SCHEMA = "evalarc.judge-verdicts.v1"
RESULT_SCHEMA = "evalarc.judge-score.v1"
MODES = ("grader", "pairwise")
ALLOWED = {"grader": ("pass", "fail", "unsure"), "pairwise": ("A", "B", "tie")}
MAX_ITEMS = 1000
MAX_VERDICT_BYTES = 4 * 1024 * 1024
MAX_PACKET_BYTES = 256 * 1024 * 1024
INSTRUCTIONS = {
    "grader": (
        "For each item, decide whether the output satisfies the task and expected answer. "
        "Answer pass, fail or unsure. The automated grader's verdict is hidden; judge the "
        "output on its own."
    ),
    "pairwise": (
        "For each item, choose the better output for the task: A, B, or tie when neither "
        "is better. Which revision produced A or B is hidden and randomized per item; do "
        "not infer it from position."
    ),
}
SCOPE = {
    "grader": (
        "Agreement between the recorded grader and caller-supplied judgments on a "
        "stratified sample. Stratification oversamples the rarer verdict, so agreement is "
        "not the grader's population accuracy; false accept and false reject counts are "
        "the actionable part. Judgment quality depends on who judged."
    ),
    "pairwise": (
        "Blind preference between baseline and current outputs of the same case and "
        "attempt, from caller-supplied judgments. Attempts of one case are not "
        "independent, so the interval is optimistic. A judge that is a model under "
        "evaluation is flagged; EvalArc cannot verify the declared judge."
    ),
}


# --- prepare ----------------------------------------------------------------------


def prepare(mode: str, runs: list[dict], sample: int, seed: int) -> tuple[dict, dict]:
    """Return (packet shown to the judge, key kept by the reviewer)."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    if not 1 <= sample <= MAX_ITEMS:
        raise ValueError(f"--sample must be 1–{MAX_ITEMS}")
    rng = random.Random(seed)
    if mode == "grader":
        if len(runs) != 1:
            raise ValueError("grader mode reads exactly one result file")
        candidates, skipped = _grader_candidates(runs[0])
        chosen = _stratified(candidates, sample, rng)
    else:
        if len(runs) != 2:
            raise ValueError("pairwise mode reads a baseline and a current result file")
        if runs[0]["format"] != runs[1]["format"]:
            raise ValueError("baseline and current use different formats")
        candidates, skipped = _pairwise_candidates(*runs)
        chosen = rng.sample(candidates, min(sample, len(candidates)))
    if not chosen:
        raise ValueError(
            "no attempts with recorded output text to judge; JUnit reports carry no outputs"
        )
    rng.shuffle(chosen)
    items, hidden = [], {}
    for index, candidate in enumerate(chosen, start=1):
        item_id = f"item-{index:03d}"
        public = {
            "item_id": item_id,
            "case_id": candidate["case_id"],
            "input": candidate["input"],
            "expected": candidate["expected"],
        }
        if mode == "grader":
            public |= {"check": candidate["check"], "output": candidate["output"]}
            hidden[item_id] = {
                "attempt": candidate["attempt"],
                "check": candidate["check"],
                "recorded_passed": candidate["passed"],
            }
        else:
            current_is_a = rng.random() < 0.5
            a, b = (
                (candidate["current"], candidate["baseline"])
                if current_is_a
                else (candidate["baseline"], candidate["current"])
            )
            public |= {"output_a": a, "output_b": b}
            hidden[item_id] = {
                "attempt": candidate["attempt"],
                "current_is": "A" if current_is_a else "B",
            }
        items.append(public)
    packet = {
        "schema_version": PACKET_SCHEMA,
        "mode": mode,
        "instructions": INSTRUCTIONS[mode],
        "allowed_verdicts": list(ALLOWED[mode]),
        "items": items,
    }
    packet_bytes = _canonical(packet)
    key = {
        "schema_version": KEY_SCHEMA,
        "mode": mode,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "packet_sha256": hashlib.sha256(packet_bytes).hexdigest(),
        "seed": seed,
        "requested_sample": sample,
        "eligible": len(candidates),
        "skipped": skipped,
        "sources": [run["source"] for run in runs],
        "subject_models": sorted({m for run in runs for m in run["graders"]["subject_models"]}),
        "items": hidden,
    }
    return packet, key


def _context(run: dict, case_id: str) -> tuple[str | None, str | None]:
    material = run["material"].get(case_id, [])
    inputs = [item["text"] for item in material if item["role"] == "input"]
    expected = [item["text"] for item in material if item["role"] == "expected"]
    return ("\n".join(inputs) or None, "\n".join(expected) or None)


def _grader_candidates(run: dict) -> tuple[list[dict], dict]:
    candidates, no_output = [], 0
    for case_id, metas in sorted(run["samples"].items()):
        text_in, text_expected = _context(run, case_id)
        for attempt, meta in enumerate(metas):
            for check, passed in sorted((meta.get("verdicts") or {}).items()):
                if passed is None:
                    continue
                if meta.get("output_text") is None:
                    no_output += 1
                    continue
                candidates.append(
                    {
                        "case_id": case_id,
                        "attempt": attempt,
                        "check": check,
                        "passed": passed,
                        "input": text_in,
                        "expected": text_expected,
                        "output": meta["output_text"],
                    }
                )
    return candidates, {"without_output": no_output}


def _stratified(candidates: list[dict], sample: int, rng: random.Random) -> list[dict]:
    """Half from each recorded verdict where possible, so rare verdicts are reviewed."""
    fails = [item for item in candidates if not item["passed"]]
    passes = [item for item in candidates if item["passed"]]
    take_fail = min(len(fails), sample // 2 + sample % 2)
    take_pass = min(len(passes), sample - take_fail)
    take_fail = min(len(fails), sample - take_pass)
    return rng.sample(fails, take_fail) + rng.sample(passes, take_pass)


def _pairwise_candidates(baseline: dict, current: dict) -> tuple[list[dict], dict]:
    candidates, identical, unmatched = [], 0, 0
    for case_id in sorted(set(baseline["samples"]) | set(current["samples"])):
        before = baseline["samples"].get(case_id, [])
        after = current["samples"].get(case_id, [])
        unmatched += abs(len(before) - len(after))
        text_in, text_expected = _context(current, case_id)
        if text_in is None:
            text_in, text_expected = _context(baseline, case_id)
        for attempt, (old, new) in enumerate(zip(before, after)):
            if old.get("output_text") is None or new.get("output_text") is None:
                unmatched += 1
                continue
            if old["output_text"] == new["output_text"]:
                identical += 1
                continue
            candidates.append(
                {
                    "case_id": case_id,
                    "attempt": attempt,
                    "input": text_in,
                    "expected": text_expected,
                    "baseline": old["output_text"],
                    "current": new["output_text"],
                }
            )
    return candidates, {"identical_outputs": identical, "unmatched_attempts": unmatched}


# --- score ------------------------------------------------------------------------


def score(
    packet_dir: Path,
    verdicts_path: Path,
    min_agreement: float | None = None,
    require_current_preferred: bool = False,
) -> dict:
    key = _read_json(packet_dir / "key.json", "key.json")
    packet_raw = (packet_dir / "share" / "packet.json").read_bytes()
    if len(packet_raw) > MAX_PACKET_BYTES:
        raise ValueError(f"share/packet.json exceeds {MAX_PACKET_BYTES} bytes")
    packet = json.loads(packet_raw)
    if key.get("schema_version") != KEY_SCHEMA or packet.get("schema_version") != PACKET_SCHEMA:
        raise ValueError("not an EvalArc judging packet folder")
    if hashlib.sha256(_canonical(packet)).hexdigest() != key["packet_sha256"]:
        raise ValueError("share/packet.json differs from the packet this key was made for")
    raw = verdicts_path.read_bytes()
    if len(raw) > MAX_VERDICT_BYTES:
        raise ValueError(f"{verdicts_path.name} exceeds {MAX_VERDICT_BYTES} bytes")
    verdicts = _read_json(verdicts_path, verdicts_path.name)
    if verdicts.get("schema_version") != VERDICTS_SCHEMA:
        raise ValueError(f"verdicts schema_version must be {VERDICTS_SCHEMA!r}")
    if verdicts.get("packet_sha256") != key["packet_sha256"]:
        raise ValueError("verdicts were recorded for a different packet")
    judge = verdicts.get("judge")
    if not isinstance(judge, dict) or judge.get("kind") not in ("human", "model"):
        raise ValueError('verdicts need judge.kind "human" or "model"')
    if judge["kind"] == "model" and not isinstance(judge.get("model"), str):
        raise ValueError("a model judge needs judge.model")
    marks = verdicts.get("verdicts")
    if not isinstance(marks, dict):
        raise ValueError("verdicts must map item IDs to answers")
    unknown = set(marks) - set(key["items"])
    if unknown:
        raise ValueError(f"unknown item IDs: {', '.join(sorted(unknown)[:5])}")
    mode, allowed = key["mode"], ALLOWED[key["mode"]]
    for item_id, answer in marks.items():
        if answer is not None and answer not in allowed:
            raise ValueError(f"{item_id}: answer must be one of {', '.join(allowed)} or null")
    missing = sorted(item for item in key["items"] if marks.get(item) is None)
    consistency = _consistency(verdicts.get("repeats"), key, allowed)
    by_id = {item["item_id"]: item for item in packet["items"]}
    body = (_score_grader if mode == "grader" else _score_pairwise)(key, by_id, marks)
    self_judged = judge["kind"] == "model" and judge["model"] in set(
        key.get("subject_models") or []
    )
    result = {
        "schema_version": RESULT_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "packet_sha256": key["packet_sha256"],
        "verdicts_sha256": hashlib.sha256(raw).hexdigest(),
        "judge": {k: judge.get(k) for k in ("kind", "model", "description") if judge.get(k)},
        "self_judged": self_judged,
        "items": len(key["items"]),
        "missing": missing,
        "complete": not missing,
        **body,
        "judge_consistency": consistency,
        "scope": SCOPE[mode],
    }
    if min_agreement is not None:
        if mode != "grader":
            raise ValueError("--min-agreement applies to grader packets")
        if not 0 < min_agreement <= 1:
            raise ValueError("--min-agreement must be in (0, 1]")
        agreement = result["agreement"]
        result["gate"] = {
            "min_agreement": min_agreement,
            "passed": bool(
                result["complete"]
                and not self_judged
                and agreement is not None
                and agreement >= min_agreement
            ),
        }
    if require_current_preferred:
        if mode != "pairwise":
            raise ValueError("--require-current-preferred applies to pairwise packets")
        result["gate"] = {
            "require_current_preferred": True,
            "passed": bool(
                result["complete"]
                and not self_judged
                and result["state"] == "current_preferred"
                and not result["position_bias"]
            ),
        }
    return result


def _consistency(repeats: object, key: dict, allowed: tuple) -> dict | None:
    """Same judge, same items, several rounds: how often did its answer change?"""
    if repeats is None:
        return None
    if (
        not isinstance(repeats, list)
        or len(repeats) < 2
        or not all(
            isinstance(round_, dict) and set(round_) == set(key["items"]) for round_ in repeats
        )
    ):
        raise ValueError("repeats must be a list of at least two complete verdict maps")
    for round_ in repeats:
        for item_id, answer in round_.items():
            if answer not in allowed:
                raise ValueError(f"repeats: {item_id} answer must be one of {', '.join(allowed)}")
    changed = sorted(
        item_id for item_id in key["items"] if len({round_[item_id] for round_ in repeats}) > 1
    )
    stable = len(key["items"]) - len(changed)
    return {
        "rounds": len(repeats),
        "items": len(key["items"]),
        "changed_items": changed,
        "stable_share": stable / len(key["items"]) if key["items"] else None,
        "stable_interval_95": wilson(stable, len(key["items"])),
    }


def _score_grader(key: dict, items: dict, marks: dict) -> dict:
    confusion = {"agree_pass": 0, "agree_fail": 0, "false_accept": 0, "false_reject": 0}
    unsure, disagreements = 0, []
    for item_id, hidden in sorted(key["items"].items()):
        answer = marks.get(item_id)
        if answer is None:
            continue
        if answer == "unsure":
            unsure += 1
            continue
        human, grader = answer == "pass", hidden["recorded_passed"]
        cell = (
            ("agree_pass" if grader else "agree_fail")
            if human == grader
            else ("false_accept" if grader else "false_reject")
        )
        confusion[cell] += 1
        if human != grader:
            item = items[item_id]
            disagreements.append(
                {
                    "item_id": item_id,
                    "case_id": item["case_id"],
                    "check": item["check"],
                    "grader": "pass" if grader else "fail",
                    "judge": answer,
                    "kind": cell,
                    "output": item["output"][:300],
                }
            )
    decided = sum(confusion.values())
    agree = confusion["agree_pass"] + confusion["agree_fail"]
    return {
        "confusion": confusion,
        "decided": decided,
        "unsure": unsure,
        "agreement": agree / decided if decided else None,
        "agreement_interval_95": wilson(agree, decided),
        "cohen_kappa": _kappa(confusion),
        "disagreements": disagreements,
    }


def _kappa(c: dict) -> float | None:
    n = sum(c.values())
    if not n:
        return None
    observed = (c["agree_pass"] + c["agree_fail"]) / n
    grader_pass = (c["agree_pass"] + c["false_accept"]) / n
    judge_pass = (c["agree_pass"] + c["false_reject"]) / n
    expected = grader_pass * judge_pass + (1 - grader_pass) * (1 - judge_pass)
    if math.isclose(expected, 1.0):
        return None
    return (observed - expected) / (1 - expected)


def _score_pairwise(key: dict, items: dict, marks: dict) -> dict:
    wins = losses = ties = chose_a = 0
    per_case: dict[str, dict] = {}
    for item_id, hidden in sorted(key["items"].items()):
        answer = marks.get(item_id)
        if answer is None:
            continue
        case = per_case.setdefault(items[item_id]["case_id"], {"wins": 0, "losses": 0, "ties": 0})
        if answer == "tie":
            ties += 1
            case["ties"] += 1
            continue
        chose_a += answer == "A"
        if answer == hidden["current_is"]:
            wins += 1
            case["wins"] += 1
        else:
            losses += 1
            case["losses"] += 1
    decisive = wins + losses
    interval = wilson(wins, decisive)
    bias = wilson(chose_a, decisive)
    if interval and interval[0] > 0.5:
        state = "current_preferred"
    elif interval and interval[1] < 0.5:
        state = "baseline_preferred"
    else:
        state = "no_clear_preference"
    return {
        "current_wins": wins,
        "baseline_wins": losses,
        "ties": ties,
        "current_win_rate": wins / decisive if decisive else None,
        "current_win_rate_interval_95": interval,
        "state": state,
        "position_a_rate": chose_a / decisive if decisive else None,
        "position_a_interval_95": bias,
        "position_bias": bool(bias and (bias[0] > 0.5 or bias[1] < 0.5)),
        "per_case": per_case,
    }


# --- rendering and commands -------------------------------------------------------


def render_sheet(packet: dict) -> str:
    """A self-contained HTML reading sheet for the judge; no verdicts, no mapping."""
    esc = lambda value: html.escape(str(value if value is not None else "—"), quote=True)  # noqa: E731
    blocks = []
    for item in packet["items"]:
        parts = [
            f"<h2>{esc(item['item_id'])} · <code>{esc(item['case_id'])}</code>"
            + (f" · {esc(item['check'])}" if "check" in item else "")
            + "</h2>",
            f"<h3>Input</h3><pre>{esc(item['input'])}</pre>",
            f"<h3>Expected</h3><pre>{esc(item['expected'])}</pre>",
        ]
        if packet["mode"] == "grader":
            parts.append(f"<h3>Output</h3><pre>{esc(item['output'])}</pre>")
        else:
            parts.append(f"<h3>Output A</h3><pre>{esc(item['output_a'])}</pre>")
            parts.append(f"<h3>Output B</h3><pre>{esc(item['output_b'])}</pre>")
        blocks.append("<section>" + "".join(parts) + "</section>")
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">"
        "<title>EvalArc judging sheet</title><style>body{font:15px/1.5 system-ui,sans-serif;"
        "max-width:60rem;margin:2rem auto;padding:0 1rem}pre{white-space:pre-wrap;"
        "background:#f5f5f5;padding:.6rem;border-radius:4px}section{border-top:1px solid #ccc;"
        "margin-top:1.5rem}</style></head><body><main>"
        f"<h1>Judging sheet · {esc(packet['mode'])}</h1>"
        f"<p>{esc(packet['instructions'])}</p><p>Allowed answers: "
        f"{esc(', '.join(packet['allowed_verdicts']))}. Record them in "
        "<code>verdicts.template.json</code>.</p>" + "".join(blocks) + "</main></body></html>"
    )


def render_markdown(result: dict) -> str:
    lines = [f"### EvalArc judge score: {result['mode']}", ""]
    judge = result["judge"]
    lines.append(
        f"Judge: {judge.get('kind')}{' ' + _cell(judge['model']) if judge.get('model') else ''} · "
        f"{result['items'] - len(result['missing'])}/{result['items']} items answered"
    )
    if result["self_judged"]:
        lines += ["", "**The judge model is a model under evaluation; use a separate judge.**"]
    consistency = result.get("judge_consistency")
    if consistency:
        lines += [
            "",
            f"Judge consistency over {consistency['rounds']} rounds: "
            f"{_pct(consistency['stable_share'])} of items got the same answer every time "
            f"({_interval(consistency['stable_interval_95'])})"
            + (
                f"; changed: {', '.join(consistency['changed_items'][:10])}"
                if consistency["changed_items"]
                else ""
            )
            + ".",
        ]
    lines.append("")
    if result["mode"] == "grader":
        c = result["confusion"]
        lines += [
            f"Agreement **{_pct(result['agreement'])}** "
            f"({_interval(result['agreement_interval_95'])})"
            f" · Cohen's kappa {_num(result['cohen_kappa'])} · unsure {result['unsure']}",
            "",
            "| | Judge pass | Judge fail |",
            "| --- | ---: | ---: |",
            f"| Grader pass | {c['agree_pass']} | {c['false_accept']} (false accept) |",
            f"| Grader fail | {c['false_reject']} (false reject) | {c['agree_fail']} |",
            "",
        ]
        for row in result["disagreements"][:20]:
            lines.append(
                f"- `{row['item_id']}` {_cell(row['case_id'])} / {_cell(row['check'])}: "
                f"grader {row['grader']}, "
                f"judge {row['judge']}"
            )
        if result.get("gate"):
            gate = result["gate"]
            lines += [
                "",
                f"Gate: agreement ≥ {gate['min_agreement']:g}, complete, separate judge — "
                f"**{'pass' if gate['passed'] else 'fail'}**",
            ]
    else:
        lines += [
            f"State **`{result['state']}`** · current wins {result['current_wins']}, baseline wins "
            f"{result['baseline_wins']}, ties {result['ties']}",
            "",
            f"Current win rate among decisive items {_pct(result['current_win_rate'])} "
            f"({_interval(result['current_win_rate_interval_95'])}). Chose position A "
            f"{_pct(result['position_a_rate'])} ({_interval(result['position_a_interval_95'])})"
            + (" — **position bias**" if result["position_bias"] else "")
            + ".",
        ]
        if result.get("gate"):
            lines += [
                "",
                "Gate: current preferred beyond its interval, complete, no position bias, "
                f"separate judge — **{'pass' if result['gate']['passed'] else 'fail'}**",
            ]
    lines += ["", f"<sub>{result['scope']}</sub>"]
    return "\n".join(lines) + "\n"


def render_html(result: dict, destination: Path) -> None:
    from evalarc.report import _card, _esc, _page, _table, _tone, _verdict

    judge = result["judge"]
    who = judge.get("kind", "") + (f" {judge['model']}" if judge.get("model") else "")
    gate = result.get("gate")
    problems = []
    if result["missing"]:
        problems.append(f"{len(result['missing'])} item(s) unanswered")
    if result["self_judged"]:
        problems.append("the judge is a model under evaluation")
    if result["mode"] == "grader":
        c = result["confusion"]
        wrong = c["false_accept"] + c["false_reject"]
        ok = (gate or {}).get("passed", not problems and not wrong)
        title = (
            f"Grader agrees with the judge on {_pct(result['agreement'])} of decided items"
            if result["agreement"] is not None
            else "No decided items"
        )
        detail = (
            f"{c['false_accept']} false accept(s), {c['false_reject']} false reject(s)"
            + (f"; {'; '.join(problems)}" if problems else "")
            + "."
        )
        body = _verdict(
            ok,
            title,
            detail,
            "Read each disagreement and fix the grader or the task wording." if wrong else "",
        )
        body += (
            '<div class="cards">'
            + _card(
                _pct(result["agreement"]),
                "agreement (" + _interval(result["agreement_interval_95"]) + ")",
            )
            + _card(_num(result["cohen_kappa"]), "Cohen's kappa")
            + _card(c["false_accept"], "false accepts", alert=bool(c["false_accept"]))
            + _card(c["false_reject"], "false rejects", alert=bool(c["false_reject"]))
            + "</div>"
        )
        body += "<h2>Grader versus judge</h2>" + _table(
            "Confusion table",
            ["", "Judge pass", "Judge fail"],
            [
                ["Grader pass", str(c["agree_pass"]), f"{c['false_accept']} (false accept)"],
                ["Grader fail", f"{c['false_reject']} (false reject)", str(c["agree_fail"])],
            ],
        )
        if result["disagreements"]:
            body += "<h2>Disagreements</h2>" + _table(
                "Disagreements",
                ["Item", "Case", "Check", "Grader", "Judge", "Output"],
                [
                    [
                        _esc(row["item_id"]),
                        f"<code>{_esc(row['case_id'])}</code>",
                        _esc(row["check"]),
                        _tone(row["grader"], "ok" if row["grader"] == "pass" else "bad"),
                        _tone(row["judge"], "ok" if row["judge"] == "pass" else "bad"),
                        _esc(row["output"]),
                    ]
                    for row in result["disagreements"]
                ],
            )
    else:
        state = result["state"]
        if result["position_bias"]:
            problems.append("the judge favors one position")
        ok = (gate or {}).get("passed", state == "current_preferred" and not problems)
        body = _verdict(
            ok,
            {
                "current_preferred": "Current output preferred over the baseline",
                "baseline_preferred": "Baseline output preferred over the current",
                "no_clear_preference": "No clear preference between baseline and current",
            }[state],
            f"Current wins {result['current_wins']}, baseline wins {result['baseline_wins']}, "
            f"ties {result['ties']}" + (f"; {'; '.join(problems)}" if problems else "") + ".",
            "" if ok else "Add items or a second judge before concluding.",
        )
        body += (
            '<div class="cards">'
            + _card(
                _pct(result["current_win_rate"]),
                "current win rate (" + _interval(result["current_win_rate_interval_95"]) + ")",
            )
            + _card(
                _pct(result["position_a_rate"]), "chose position A", alert=result["position_bias"]
            )
            + "</div>"
        )
        body += "<h2>Per case</h2>" + _table(
            "Per-case preference",
            ["Case", "Current wins", "Baseline wins", "Ties"],
            [
                [f"<code>{_esc(case)}</code>", str(v["wins"]), str(v["losses"]), str(v["ties"])]
                for case, v in sorted(result["per_case"].items())
            ],
        )
    consistency = result.get("judge_consistency")
    if consistency:
        body += (
            f"<h2>Judge consistency</h2><p>{_pct(consistency['stable_share'])} of items got the "
            f"same answer in all {consistency['rounds']} rounds "
            f"({_esc(_interval(consistency['stable_interval_95']))}).</p>"
        )
    body += (
        f'<p class="metadata">Judge: {_esc(who)} · {result["items"] - len(result["missing"])}/'
        f"{result['items']} items answered · packet SHA-256 {_esc(result['packet_sha256'])}</p>"
        f"<footer>{_esc(result['scope'])}</footer>"
    )
    _page("Judge score", f"Blind {result['mode']} judging.", body, destination)


def prepare_command(args) -> int:
    from evalarc.artifacts import new_run
    from evalarc.evaluate import write_json

    try:
        runs = [load_results(path, args.format, args.threshold) for path in args.results]
        packet, key = prepare(args.mode, runs, args.sample, args.seed)
        with new_run(args.output) as output:
            share = output / "share"
            share.mkdir()
            (share / "packet.json").write_bytes(_canonical(packet))
            (share / "index.html").write_text(render_sheet(packet), encoding="utf-8")
            template = {
                "schema_version": VERDICTS_SCHEMA,
                "packet_sha256": key["packet_sha256"],
                "judge": {"kind": "human", "model": None, "description": ""},
                "verdicts": {item["item_id"]: None for item in packet["items"]},
            }
            write_json(share / "verdicts.template.json", template)
            write_json(output / "key.json", key)
            (output / "inputs").mkdir()
            for index, (path, run) in enumerate(zip(args.results, runs), start=1):
                data = path.read_bytes()
                if hashlib.sha256(data).hexdigest() != run["source"]["sha256"]:
                    raise ValueError(f"{path} changed while it was being read")
                (output / "inputs" / f"{index:02d}{path.suffix or '.json'}").write_bytes(data)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as error:
        print(f"evalarc: {error}", file=sys.stderr)
        return 2
    print(
        f"Judging packet: {len(packet['items'])} {args.mode} item(s) of {key['eligible']} "
        f"eligible\nGive the judge only: {args.output / 'share'}\n"
        f"Keep private: {args.output / 'key.json'}"
    )
    return 0


def score_command(args) -> int:
    from evalarc.artifacts import new_run
    from evalarc.evaluate import write_json

    try:
        result = score(
            args.packet, args.verdicts, args.min_agreement, args.require_current_preferred
        )
        if args.output:
            with new_run(args.output) as output:
                write_json(output / "score.json", result)
                (output / "verdicts.json").write_bytes(args.verdicts.read_bytes())
                (output / "summary.md").write_text(render_markdown(result), encoding="utf-8")
                render_html(result, output / "index.html")
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as error:
        print(f"evalarc: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(result), end="")
    if result.get("gate"):
        return 0 if result["gate"]["passed"] else 1
    return 0


# --- running a judge command ------------------------------------------------------

JUDGE_KEYS = {"command", "model", "timeout_seconds", "description"}
JUDGE_SCOPE = (
    "Verdicts were produced by the caller's judge command, one item at a time from "
    "share/packet.json only. EvalArc did not see the model call and cannot verify "
    "which model answered."
)


def judge_run(packet_dir: Path, config_path: Path, repeat: int = 1) -> dict:
    """Ask a caller-supplied judge command for each item; return a verdicts document."""
    from evalarc import trusted

    config = trusted.read_config(config_path, JUDGE_KEYS, {"command", "model"})
    template = trusted.command(config["command"], "command", {"python", "packet", "config_dir"})
    model = config["model"]
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model must name the judge model")
    seconds = trusted.timeout(config.get("timeout_seconds"), 120.0)
    share = packet_dir / "share"
    packet_path = share / "packet.json"
    raw = packet_path.read_bytes()
    if len(raw) > MAX_PACKET_BYTES:
        raise ValueError(f"share/packet.json exceeds {MAX_PACKET_BYTES} bytes")
    packet = json.loads(raw)
    if packet.get("schema_version") != PACKET_SCHEMA:
        raise ValueError("not an EvalArc judging packet")
    allowed = packet["allowed_verdicts"]
    if not 1 <= repeat <= 10:
        raise ValueError("--repeat must be 1–10")
    rounds = [
        _judge_round(packet, template, packet_path, config_path, share, seconds, allowed)
        for _ in range(repeat)
    ]
    document = {
        "schema_version": VERDICTS_SCHEMA,
        "packet_sha256": hashlib.sha256(_canonical(packet)).hexdigest(),
        "judge": {
            "kind": "model",
            "model": model,
            "description": str(config.get("description") or ""),
        },
        "verdicts": rounds[0],
        "produced_by": {
            "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "command": template,
            "scope": JUDGE_SCOPE,
        },
    }
    if repeat > 1:
        document["repeats"] = rounds
    return document


def _judge_round(packet, template, packet_path, config_path, share, seconds, allowed) -> dict:
    from evalarc import trusted

    verdicts = {}
    for item in packet["items"]:
        request = {
            "mode": packet["mode"],
            "instructions": packet["instructions"],
            "allowed_verdicts": allowed,
            "item": item,
        }
        # The judge runs inside share/ and is never given key.json.
        completed = trusted.run(
            template,
            {"packet": str(packet_path.resolve()), "config_dir": str(config_path.resolve().parent)},
            share,
            seconds,
            stdin=json.dumps(request, ensure_ascii=False),
            label=f"judge command for {item['item_id']}",
        )
        try:
            answer = json.loads(completed.stdout.strip().splitlines()[-1])["verdict"]
        except (IndexError, ValueError, KeyError, TypeError):
            raise trusted.CommandFailure(
                f"judge command for {item['item_id']} must print JSON with a verdict on "
                "its last line"
            ) from None
        if answer not in allowed:
            raise trusted.CommandFailure(
                f"judge command for {item['item_id']} answered {answer!r}; expected one "
                f"of {', '.join(allowed)}"
            )
        verdicts[item["item_id"]] = answer
    return verdicts


def judge_run_command(args) -> int:
    from evalarc import trusted
    from evalarc.artifacts import new_json

    try:
        if not args.trust_local:
            raise ValueError(trusted.TRUST_MESSAGE)
        verdicts = judge_run(args.packet, args.config, args.repeat)
        new_json(args.output, verdicts)
    except (OSError, ValueError, KeyError, TypeError, trusted.CommandFailure) as error:
        print(f"evalarc: {error}", file=sys.stderr)
        return 2
    print(
        f"Recorded {len(verdicts['verdicts'])} verdict(s) from {verdicts['judge']['model']} in "
        f"{args.output}\nScore them: evalarc judge-score {args.packet} {args.output}"
    )
    return 0


# --- helpers ----------------------------------------------------------------------


def _canonical(document: dict) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _read_json(path: Path, name: str) -> dict:
    try:
        document = json.loads(path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{name} is not JSON: {error}") from None
    if not isinstance(document, dict):
        raise ValueError(f"{name} must be a JSON object")
    return document


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def _interval(value: list | None) -> str:
    return "95% interval —" if not value else f"95% interval {value[0]:.1%}–{value[1]:.1%}"


def _num(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"

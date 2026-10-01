"""Review a recorded hillclimbing sequence against keep/rollback rules.

A hillclimbing loop proposes one change at a time, reruns the evaluation, and keeps
the change only when it helps. This module replays that decision offline from saved
result files: a baseline followed by the result after each proposed change, plus a
declared held-out split. Every candidate is compared with the last kept result:

* a held-out check that loses passes, or a partition whose pass rate falls, rolls
  the change back as a regression;
* tuning cases improving while held-out cases do not rolls it back as overfitting;
* otherwise the change is kept only when both partitions improve (quality objective),
  or when recorded cost falls without either partition falling (cost objective).

After consecutive rollbacks the remaining tuning failures are triaged by likely cause,
and the final kept result is compared with the baseline on held-out cases with 95%
intervals to recommend whether to merge. Nothing is rerun and no model is called.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from evalarc.eval_health import TRIAGE_NEXT, _noise, _triage
from evalarc.generalization import load_split, partition, review_split, scan_harness
from evalarc.results_diff import BLOCKING, _cell, _tally, diff, load_results, wilson
from evalarc.usage import cost_gate

SCHEMA = "evalarc.hillclimb-review.v1"
MAX_STEPS = 50
OBJECTIVES = ("quality", "cost")
DECISIONS = ("keep", "rollback_regression", "rollback_overfit", "rollback_no_gain")
RECOMMENDATIONS = {
    "merge": "Merge: held-out cases improved beyond sampling noise with no held-out regression.",
    "merge_cost": (
        "Merge: recorded cost fell with no held-out check losing passes and no drop in "
        "either partition's pass rate."
    ),
    "no_change_kept": "Nothing to merge: every proposed change was rolled back.",
    "do_not_merge_regression": (
        "Do not merge: the final result is worse than the baseline on held-out checks or "
        "on either partition's pass rate."
    ),
    "do_not_merge_within_noise": (
        "Do not merge yet: the held-out gain is within sampling noise; add held-out "
        "cases or repetitions and rerun the final and baseline configurations."
    ),
    "do_not_merge_cost": "Do not merge: recorded cost did not fall below the required ratio.",
    "do_not_merge_leakage": (
        "Do not merge: held-out case text appears in the harness, so held-out results "
        "no longer measure generalization."
    ),
}
SCOPE = (
    "Replays keep/rollback rules over saved results; it does not reproduce the loop that "
    "produced them. The held-out split is caller-declared and only as independent as it "
    "was kept in practice. Pass rates pool check attempts, which are not independent "
    "within one case, so intervals are optimistic. Cost ratios come from single runs."
)


def review(
    runs: list[dict],
    split: dict,
    objective: str = "quality",
    cost_metric: str = "auto",
    max_cost_ratio: float = 1.0,
    stall_after: int = 2,
    min_effect: float | None = None,
    harness: list[Path] | None = None,
    labels: list[str] | None = None,
    min_steps: int = 1,
) -> dict:
    if objective not in OBJECTIVES:
        raise ValueError(f"--objective must be one of {', '.join(OBJECTIVES)}")
    if not 1 + min_steps <= len(runs) <= MAX_STEPS + 1:
        raise ValueError(f"hillclimb-review needs a baseline and 1–{MAX_STEPS} step results")
    if stall_after < 1:
        raise ValueError("--stall-after must be at least 1")
    if min_effect is not None and not 0 < min_effect < 1:
        raise ValueError("--min-effect must be in (0, 1)")
    formats = {run["format"] for run in runs}
    if len(formats) > 1:
        raise ValueError(f"inputs use different formats: {', '.join(sorted(formats))}")
    case_sets = {frozenset(run["cases"]) for run in runs}
    if len(case_sets) > 1:
        raise ValueError(
            "every result must contain the same cases; adding or removing cases during "
            "hillclimbing changes what is measured"
        )
    tasks = {run["identity"].get("task") for run in runs} - {None}
    if len(tasks) > 1:
        raise ValueError(f"inputs are not comparable: tasks {sorted(tasks)}")
    labels = labels or [run["source"]["name"] for run in runs]
    cases = set(runs[0]["cases"])
    held_out = partition(split, cases)
    tuning = cases - held_out

    baseline = runs[0]
    start = _snapshot(baseline, tuning, held_out)
    noise = {
        name: _noise(start[name], min_effect)
        for name in ("tuning", "held_out")
        if start[name]["assessed"]
    }
    notes = []
    for name, value in noise.items():
        if min_effect is not None and value and value["resolvable_change"] > min_effect:
            notes.append(
                f"Before the first step: the {name.replace('_', '-')} partition resolves "
                f"changes of about {value['resolvable_change']:.1%}, larger than the "
                f"{min_effect:.1%} target. Add cases or repetitions before hillclimbing."
            )

    steps, kept_index, streak, stalls = [], 0, 0, []
    kept_history = [runs[0]]
    for index in range(1, len(runs)):
        kept, candidate = runs[kept_index], runs[index]
        result = diff(kept, candidate)
        split_review = review_split(kept, candidate, result, split)
        parts = split_review["partitions"]
        cost = _cost(result, cost_metric)
        decision, reason = _decide(objective, parts, cost)
        step = {
            "index": index,
            "label": labels[index],
            "source": candidate["source"],
            "compared_with": labels[kept_index],
            "decision": decision,
            "reason": reason,
            "tuning": _partition_row(parts["tuning"]),
            "held_out": _partition_row(parts["held_out"]),
            "cost": cost,
            "held_out_blocking_changes": [
                {"case_id": row["case_id"], "check": row["check"], "kind": row["kind"]}
                for row in result["changes"]
                if row["case_id"] in held_out and row["kind"] in BLOCKING
            ],
            "changes_with_same_output_different_verdict": result[
                "changes_with_same_output_different_verdict"
            ],
        }
        if decision == "keep":
            kept_index, streak = index, 0
            kept_history.append(candidate)
        else:
            streak += 1
        step["kept"] = labels[kept_index]
        steps.append(step)
        if streak == stall_after:
            history = kept_history
            stalls.append(
                _stall(runs[kept_index], labels[kept_index], index, tuning, noise, history)
            )
            step["stalled"] = True

    final = runs[kept_index]
    comparison = _final(baseline, final, split, tuning, held_out, cost_metric)
    leakage = scan_harness(harness, runs, held_out) if harness else None
    recommendation = _recommend(objective, kept_index, comparison, leakage, max_cost_ratio)
    return {
        "schema_version": SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "objective": objective,
        "format": baseline["format"],
        "split": {
            "source": split["source"],
            "entries": split["held_out"],
            "held_out_cases": sorted(held_out),
            "tuning_cases": len(tuning),
        },
        "runs": [{"label": label, "source": run["source"]} for label, run in zip(labels, runs)],
        "baseline": {"label": labels[0], **start},
        "noise": noise,
        "min_effect": min_effect,
        "notes": notes,
        "steps": steps,
        "stalls": stalls,
        "final": {"label": labels[kept_index], "index": kept_index, **comparison},
        "leakage": leakage,
        "max_cost_ratio": max_cost_ratio,
        "recommendation": recommendation,
        "recommendation_text": RECOMMENDATIONS[recommendation],
        "merge_recommended": recommendation in ("merge", "merge_cost"),
        "tuning_failures": _tuning_failures(final, tuning),
        "scope": SCOPE,
    }


def _decide(objective: str, parts: dict, cost: dict | None) -> tuple[str, str]:
    tuning, held_out = parts["tuning"], parts["held_out"]
    if held_out["blocking_changes"]:
        return "rollback_regression", "a held-out check lost passes or coverage"
    for name, row in (("held-out", held_out), ("tuning", tuning)):
        if row["delta"] is not None and row["delta"] < 0:
            return "rollback_regression", f"the {name} pass rate fell"
    up = {
        name: (row["delta"] or 0) > 0 for name, row in (("tuning", tuning), ("held_out", held_out))
    }
    # Overfitting is rejected under every objective, even when cost also fell.
    if up["tuning"] and not up["held_out"]:
        return "rollback_overfit", "tuning cases improved but held-out cases did not"
    if objective == "cost":
        if cost is None:
            raise ValueError(
                "--objective cost needs recorded cost or tokens on every attempt of every "
                "result; choose --cost-metric or record usage"
            )
        if cost["ratio"] < 1:
            return "keep", f"cost fell to {cost['ratio']:.3f}x with no partition falling"
        if up["tuning"] and up["held_out"] and cost["ratio"] <= 1:
            return "keep", "both partitions improved at no higher cost"
    elif up["tuning"] and up["held_out"]:
        return "keep", "tuning and held-out cases both improved"
    if objective == "cost":
        return "rollback_no_gain", "cost did not fall and quality did not improve"
    return "rollback_no_gain", "tuning cases did not improve"


def _cost(result: dict, metric: str) -> dict | None:
    try:
        gate = cost_gate(result["usage"], metric, 1.0)
    except ValueError:
        return None
    return {key: gate[key] for key in ("metric", "baseline_mean", "current_mean", "ratio")}


def _snapshot(run: dict, tuning: set, held_out: set) -> dict:
    return {
        name: _rate(run, members) for name, members in (("tuning", tuning), ("held_out", held_out))
    }


def _rate(run: dict, members: set) -> dict:
    passed = assessed = attempts = 0
    for case_id in members:
        for check_attempts in run["cases"].get(case_id, {}).values():
            tally = _tally(check_attempts)
            passed += tally["passed"]
            assessed += tally["assessed"]
            attempts += tally["attempts"]
    return {
        "passed": passed,
        "assessed": assessed,
        "attempts": attempts,
        "pass_rate": passed / assessed if assessed else None,
        "interval_95": wilson(passed, assessed),
    }


def _partition_row(row: dict) -> dict:
    return {
        "baseline": row["baseline"]["pass_rate"],
        "current": row["current"]["pass_rate"],
        "delta": row["delta"],
        "within_sampling_noise": row["within_sampling_noise"],
        "blocking_changes": row["blocking_changes"],
    }


def _stall(
    run: dict, label: str, index: int, tuning: set, noise: dict, history: list[dict]
) -> dict:
    """After consecutive rollbacks: triage remaining tuning failures, compare to noise."""
    tuning_run = {**run, "cases": {k: v for k, v in run["cases"].items() if k in tuning}}
    # Pool the kept versions only: "regressed" means it passed in an earlier kept
    # version, and "never_passes" needs at least two kept versions to mean anything.
    triage = hillclimb_triage(tuning_run, history)
    rate = _rate(run, tuning)
    headroom = None if rate["pass_rate"] is None else 1 - rate["pass_rate"]
    resolvable = (noise.get("tuning") or {}).get("resolvable_change")
    below_noise = bool(headroom is not None and resolvable is not None and headroom < resolvable)
    counts: dict[str, int] = {}
    for row in triage:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
    return {
        "after_step": index,
        "kept": label,
        "remaining_tuning_failures": len(triage),
        "categories": counts,
        "triage": triage,
        "tuning_headroom": headroom,
        "headroom_below_noise": below_noise,
        "advice": (
            "The remaining tuning headroom is smaller than the resolvable change; stop "
            "iterating and add cases or repetitions."
            if below_noise
            else "Fix pipeline, truncation and grader causes first; only consistent "
            "failures are candidates for another change."
        ),
    }


def hillclimb_triage(run: dict, kept_history: list[dict]) -> list[dict]:
    rows = _triage(run, [], _truncated(run), _combined(kept_history))
    if len(kept_history) < 2:
        for row in rows:
            if row["category"] == "never_passes":
                row["category"] = "consistent_failure"
    return rows


def _truncated(run: dict) -> list[dict]:
    return [
        {"file": run["source"]["name"], "case_id": case_id}
        for case_id, metas in run["samples"].items()
        if any(meta.get("truncated") for meta in metas)
    ]


def _combined(runs: list[dict]) -> dict:
    """Pool check tallies across results, keyed by (case, check)."""
    pooled: dict = {}
    for run in runs:
        for case_id, checks in run["cases"].items():
            for check, attempts in checks.items():
                tally = _tally(attempts)
                total = pooled.setdefault(
                    (case_id, check), {"passed": 0, "assessed": 0, "attempts": 0}
                )
                for key in total:
                    total[key] += tally[key]
    return pooled


def _final(baseline, final, split, tuning, held_out, cost_metric) -> dict:
    result = diff(baseline, final)
    parts = review_split(baseline, final, result, split)["partitions"]
    return {
        "tuning": {**_rate(final, tuning), **_partition_row(parts["tuning"])},
        "held_out": {**_rate(final, held_out), **_partition_row(parts["held_out"])},
        "baseline_held_out_interval_95": _rate(baseline, held_out)["interval_95"],
        "held_out_blocking_changes": parts["held_out"]["blocking_changes"],
        "cost": _cost(result, cost_metric),
    }


def _recommend(objective, kept_index, comparison, leakage, max_cost_ratio) -> str:
    if kept_index == 0:
        return "no_change_kept"
    if leakage and leakage["held_out_hits"]:
        return "do_not_merge_leakage"
    held = comparison["held_out"]
    if (
        comparison["held_out_blocking_changes"]
        or (held["delta"] or 0) < 0
        or (comparison["tuning"]["delta"] or 0) < 0
    ):
        return "do_not_merge_regression"
    if objective == "cost":
        cost = comparison["cost"]
        if cost is None or cost["ratio"] > max_cost_ratio or cost["ratio"] >= 1:
            return "do_not_merge_cost"
        return "merge_cost"
    if not held["delta"] or held["within_sampling_noise"]:
        return "do_not_merge_within_noise"
    return "merge"


def _tuning_failures(run: dict, tuning: set) -> list[dict]:
    """Tuning-case failures only: the view a tuning loop may read."""
    rows = []
    for case_id in sorted(tuning):
        for check, attempts in sorted(run["cases"].get(case_id, {}).items()):
            failed = [item for item in attempts if item["passed"] is not True]
            if failed:
                rows.append(
                    {
                        "case_id": case_id,
                        "check": check,
                        "failed_attempts": len(failed),
                        "attempts": len(attempts),
                        "evidence": sorted({item.get("evidence") or "" for item in failed} - {""}),
                    }
                )
    return rows


# --- rendering --------------------------------------------------------------------


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def _pp(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:+.1f} pp"


def _interval(interval: list | None) -> str:
    return "—" if not interval else f"{interval[0]:.1%}–{interval[1]:.1%}"


def _ratio(cost: dict | None) -> str:
    return "—" if not cost else f"{cost['ratio']:.3f}"


def render_markdown(result: dict) -> str:
    final = result["final"]
    lines = [
        f"### EvalArc hillclimb review: `{result['recommendation']}`",
        "",
        result["recommendation_text"],
        "",
        f"Objective: **{result['objective']}** · {result['split']['tuning_cases']} tuning and "
        f"{len(result['split']['held_out_cases'])} held-out cases · final kept: "
        f"{_cell(final['label'])}",
        "",
    ]
    for note in result["notes"]:
        lines += [f"> {note}", ""]
    lines += [
        "| Step | Compared with | Tuning | Held out | Cost ratio | Decision |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for step in result["steps"]:
        lines.append(
            f"| {_cell(step['label'])} | {_cell(step['compared_with'])} | "
            f"{_pp(step['tuning']['delta'])} | {_pp(step['held_out']['delta'])} | "
            f"{_ratio(step['cost'])} | `{step['decision']}`"
            f"{' · stalled' if step.get('stalled') else ''} |"
        )
    base = result["baseline"]
    lines += [
        "",
        "| Held-out cases | Pass rate | 95% interval |",
        "| --- | ---: | ---: |",
        f"| Baseline {_cell(base['label'])} | {_pct(base['held_out']['pass_rate'])} | "
        f"{_interval(base['held_out']['interval_95'])} |",
        f"| Final {_cell(final['label'])} | {_pct(final['held_out']['pass_rate'])} | "
        f"{_interval(final['held_out']['interval_95'])} |",
        "",
        f"Held-out change {_pp(final['held_out']['delta'])}"
        + (" (within sampling noise)" if final["held_out"]["within_sampling_noise"] else "")
        + (f" · cost ratio {_ratio(final['cost'])}" if final["cost"] else "")
        + ".",
        "",
    ]
    for stall in result["stalls"]:
        lines += [
            f"**Stalled after step {stall['after_step']}** (kept {_cell(stall['kept'])}): "
            f"{stall['remaining_tuning_failures']} failing tuning case(s) — "
            + ", ".join(f"{name} {count}" for name, count in sorted(stall["categories"].items()))
            + f". {stall['advice']}",
            "",
        ]
    leakage = result["leakage"]
    if leakage:
        lines += [
            f"Harness leakage: {len(leakage['hits'])} hit(s), {leakage['held_out_hits']} from "
            "held-out cases.",
            "",
        ]
    lines.append(f"<sub>{result['scope']}</sub>")
    return "\n".join(lines) + "\n"


def render_html(result: dict, destination: Path) -> None:
    from evalarc.report import _card, _esc, _page

    final, base = result["final"], result["baseline"]
    body = (
        f"<p><strong>{_esc(result['recommendation'])}</strong>: "
        f'{_esc(result["recommendation_text"])}</p><div class="cards">'
        + _card(_pct(base["held_out"]["pass_rate"]), "baseline held-out pass rate")
        + _card(_pct(final["held_out"]["pass_rate"]), f"final held-out ({final['label']})")
        + _card(
            _pp(final["held_out"]["delta"]),
            "held-out change"
            + (" · within noise" if final["held_out"]["within_sampling_noise"] else ""),
            alert=not result["merge_recommended"],
        )
        + _card(_ratio(final["cost"]), "final/baseline cost ratio")
        + "</div>"
    )
    for note in result["notes"]:
        body += f'<p class="metadata">{_esc(note)}</p>'
    body += (
        '<h2>Steps</h2><div class="scroll"><table><thead><tr><th>#</th><th>Step</th>'
        "<th>Compared with</th><th>Tuning</th><th>Held out</th><th>Cost ratio</th>"
        "<th>Decision</th><th>Reason</th></tr></thead><tbody>"
    )
    for step in result["steps"]:
        tone = "passed" if step["decision"] == "keep" else "failed"
        body += (
            f"<tr><td>{step['index']}</td><td><code>{_esc(step['label'])}</code></td>"
            f"<td><code>{_esc(step['compared_with'])}</code></td>"
            f"<td>{_esc(_pp(step['tuning']['delta']))}</td>"
            f"<td>{_esc(_pp(step['held_out']['delta']))}</td>"
            f"<td>{_esc(_ratio(step['cost']))}</td>"
            f'<td class="{tone}">{_esc(step["decision"])}'
            f"{' · stalled' if step.get('stalled') else ''}</td>"
            f"<td>{_esc(step['reason'])}</td></tr>"
        )
    body += "</tbody></table></div>"
    for stall in result["stalls"]:
        body += (
            f"<h2>Stall after step {stall['after_step']}</h2><p>{_esc(stall['advice'])}</p>"
            '<div class="scroll"><table><thead><tr><th>Tuning case</th><th>Category</th>'
            "<th>Failing checks</th><th>Next step</th></tr></thead><tbody>"
        )
        for row in stall["triage"]:
            body += (
                f"<tr><td><code>{_esc(row['case_id'])}</code></td>"
                f"<td><code>{_esc(row['category'])}</code></td>"
                f"<td>{_esc(', '.join(row['checks']))}</td>"
                f"<td>{_esc(TRIAGE_NEXT[row['category']])}</td></tr>"
            )
        body += "</tbody></table></div>"
    body += (
        '<h2>Final versus baseline (held out)</h2><div class="scroll"><table><thead><tr>'
        "<th></th><th>Pass rate</th><th>95% interval</th></tr></thead><tbody>"
        f"<tr><td>Baseline <code>{_esc(base['label'])}</code></td>"
        f"<td>{_esc(_pct(base['held_out']['pass_rate']))}</td>"
        f"<td>{_esc(_interval(base['held_out']['interval_95']))}</td></tr>"
        f"<tr><td>Final <code>{_esc(final['label'])}</code></td>"
        f"<td>{_esc(_pct(final['held_out']['pass_rate']))}</td>"
        f"<td>{_esc(_interval(final['held_out']['interval_95']))}</td></tr>"
        "</tbody></table></div>"
    )
    if result["leakage"]:
        body += (
            f"<p>Harness leakage: {len(result['leakage']['hits'])} hit(s), "
            f"{result['leakage']['held_out_hits']} from held-out cases.</p>"
        )
    body += (
        '<p><a href="hillclimb.json">Review JSON</a> · <a href="summary.md">Markdown</a> · '
        '<a href="tuning-failures.json">Tuning failures only</a></p>'
        f"<footer>{_esc(result['scope'])}</footer>"
    )
    _page("Hillclimb review", "Which changes to keep, and whether to merge.", body, destination)


def write_hillclimb_report(output: Path, result: dict) -> None:
    from evalarc.evaluate import write_json

    write_json(output / "hillclimb.json", result)
    write_json(
        output / "tuning-failures.json",
        {
            "schema_version": "evalarc.tuning-failures.v1",
            "kept": result["final"]["label"],
            "held_out_excluded": True,
            "failures": result["tuning_failures"],
        },
    )
    (output / "summary.md").write_text(render_markdown(result), encoding="utf-8")
    render_html(result, output / "index.html")


def command(args) -> int:
    """`evalarc hillclimb-review`: exit 0 merge recommended, 1 not, 2 unusable input."""
    from evalarc.artifacts import new_run

    paths = [args.baseline, *args.steps]
    try:
        if len(set(map(Path.resolve, paths))) != len(paths):
            raise ValueError("each result file may appear once")
        runs = [load_results(path, args.format, args.threshold) for path in paths]
        from evalarc import evidence

        split = load_split(args.held_out)
        params = {
            "format": args.format,
            "threshold": args.threshold,
            "objective": args.objective,
            "cost_metric": args.cost_metric,
            "max_cost_ratio": args.max_cost_ratio,
            "stall_after": args.stall_after,
            "min_effect": args.min_effect,
            "labels": [path.name for path in paths],
            "min_steps": 1,
        }
        result = evidence.compute_hillclimb(runs, params, split, args.harness)
        if args.output:
            with new_run(args.output) as output:
                inputs = []
                for index, (path, run) in enumerate(zip(paths, runs)):
                    name = f"inputs/{index:02d}-{path.name}"
                    evidence.copy_input(path, run["source"]["sha256"], output / name)
                    inputs.append({"file": name})
                evidence.copy_input(args.held_out, split["source"]["sha256"], output / "split.json")
                harness = evidence.copy_harness(args.harness, output) if args.harness else []
                evidence.write_params(
                    output,
                    "hillclimb-review",
                    {**params, "inputs": inputs, "split": "split.json", "harness": harness},
                )
                write_hillclimb_report(output, result)
        if args.markdown:
            with args.markdown.open("a", encoding="utf-8") as summary:
                summary.write(render_markdown(result))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as error:
        print(f"evalarc: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        for note in result["notes"]:
            print(f"Note: {note}")
        for step in result["steps"]:
            print(
                f"  {step['index']}. {step['label']}: {step['decision']} "
                f"(tuning {_pp(step['tuning']['delta'])}, held out {_pp(step['held_out']['delta'])}"
                + (f", cost {_ratio(step['cost'])}x" if step["cost"] else "")
                + ")"
                + (" — stalled" if step.get("stalled") else "")
            )
        for stall in result["stalls"]:
            print(
                f"Stalled after step {stall['after_step']}: "
                f"{stall['remaining_tuning_failures']} failing tuning case(s) ("
                + ", ".join(f"{k} {v}" for k, v in sorted(stall["categories"].items()))
                + f"). {stall['advice']}"
            )
        final = result["final"]
        print(
            f"Final kept: {final['label']} | held out "
            f"{_pct(result['baseline']['held_out']['pass_rate'])}"
            f" -> {_pct(final['held_out']['pass_rate'])}"
            + (" (within noise)" if final["held_out"]["within_sampling_noise"] else "")
            + (f" | cost ratio {_ratio(final['cost'])}" if final["cost"] else "")
        )
        print(f"Recommendation: {result['recommendation']} — {result['recommendation_text']}")
        if args.output:
            print(f"Report: {args.output / 'index.html'}")
    return 0 if result["merge_recommended"] else 1

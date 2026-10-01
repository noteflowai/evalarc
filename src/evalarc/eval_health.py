"""Diagnose whether saved evaluation results can support tuning decisions.

Reads one or more Inspect AI, promptfoo or JUnit result files of the same evaluation
and reports properties a useful evaluation needs before anyone hillclimbs on it:
headroom below saturation, no checks that fail on every attempt, low attempt-to-attempt
variation, few unassessed attempts (errors, timeouts, skips), enough recorded attempts
to resolve the smallest change that matters, and, for files ordered from weaker to
stronger configurations, scores that do not fall as capability rises. Offline only.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from evalarc.results_diff import (
    _cell,
    _tally,
    _wilson_interval,
    grading_conflicts,
    load_results,
    wilson,
)

SCHEMA = "evalarc.eval-health.v1"
MAX_INPUTS = 20
DEFAULT_SATURATION = 0.95
Z = 1.959963984540054
SCOPE = (
    "Descriptive diagnostics of recorded check outcomes. Rates pool check attempts, which "
    "are not independent within one case, so noise estimates are optimistic lower bounds. "
    "A finding points to something to inspect (task wording, grader, pipeline, sample "
    "size); it does not prove the evaluation is wrong, and a clean report does not show "
    "that the cases represent production use."
)


def health(
    runs: list[dict],
    saturation: float = DEFAULT_SATURATION,
    min_effect: float | None = None,
    ordered: bool = False,
    cases_manifest: dict | None = None,
) -> dict:
    """Compute findings for loaded result runs (see results_diff.load_results)."""
    if not runs or len(runs) > MAX_INPUTS:
        raise ValueError(f"eval-health reads 1–{MAX_INPUTS} result files")
    if not 0 < saturation <= 1:
        raise ValueError("--saturation must be in (0, 1]")
    if min_effect is not None and not 0 < min_effect < 1:
        raise ValueError("--min-effect must be in (0, 1)")
    if ordered and len(runs) < 2:
        raise ValueError("--ordered needs at least two result files")
    formats = {run["format"] for run in runs}
    if len(formats) > 1:
        raise ValueError(f"inputs use different formats: {', '.join(sorted(formats))}")
    tasks = {run["identity"].get("task") for run in runs} - {None}
    if len(tasks) > 1:
        raise ValueError(f"inputs are not comparable: tasks {sorted(tasks)}")

    summaries = [_run_summary(run) for run in runs]
    findings: list[dict] = []

    # 1. Headroom: the strongest recorded configuration should stay well below 100%.
    best = max(
        (item for item in summaries if item["pass_rate"] is not None),
        key=lambda item: item["pass_rate"],
        default=None,
    )
    if best is not None and best["pass_rate"] >= saturation:
        findings.append(
            _finding(
                "saturated",
                "warning",
                f"{best['source']['name']} passes {best['pass_rate']:.1%} of assessed check "
                f"attempts (at or above {saturation:.0%}). Quality changes can no longer be "
                "measured reliably; add harder cases that experts agree are solvable, or tune "
                "for cost and latency at equal quality instead (evalarc diff --max-cost-ratio).",
                value=best["pass_rate"],
            )
        )

    # 2. Checks that fail on every assessed attempt in every file.
    combined: dict[tuple[str, str], dict] = {}
    for run in runs:
        for case_id, checks in run["cases"].items():
            for check, attempts in checks.items():
                tally = _tally(attempts)
                total = combined.setdefault(
                    (case_id, check), {"passed": 0, "assessed": 0, "attempts": 0, "files": 0}
                )
                for key in ("passed", "assessed", "attempts"):
                    total[key] += tally[key]
                total["files"] += 1
    always = [
        {"case_id": case, "check": check, **tally}
        for (case, check), tally in sorted(combined.items())
        if tally["assessed"] >= 2 and tally["passed"] == 0
    ]
    if always:
        cases = sorted({row["case_id"] for row in always})
        findings.append(
            _finding(
                "always_failing",
                "warning",
                f"{len(always)} check(s) in {len(cases)} case(s) fail on every assessed attempt. "
                "Read the task and grader for these first: a gap that never moves is often an "
                "ambiguous task, a requirement the task never states, or a grader bug rather "
                "than missing capability.",
                items=always,
            )
        )

    # 3. Attempt-to-attempt variation inside one file.
    flaky = []
    for run in runs:
        for case_id, checks in sorted(run["cases"].items()):
            for check, attempts in sorted(checks.items()):
                tally = _tally(attempts)
                if 0 < tally["passed"] < tally["assessed"]:
                    flaky.append(
                        {
                            "file": run["source"]["name"],
                            "case_id": case_id,
                            "check": check,
                            **tally,
                        }
                    )
    repeated = sum(item["repeated_checks"] for item in summaries)
    if flaky:
        share = len(flaky) / repeated if repeated else None
        findings.append(
            _finding(
                "flaky_checks",
                "warning" if share is not None and share > 0.1 else "info",
                f"{len(flaky)} of {repeated} repeated check(s) both passed and failed across "
                "attempts. Variation comes from ambiguous tasks, inconsistent grading of the "
                "same output, unstable configuration, or state left over between attempts. "
                "Regrade fixed outputs several times (evalarc judge-run --repeat, or "
                "evalarc trace-stability) to separate grader variation from agent variation.",
                items=flaky,
                value=share,
            )
        )

    # 4. Attempts without an outcome: errors, timeouts, skips.
    unassessed = sum(item["attempts"] - item["assessed"] for item in summaries)
    attempts = sum(item["attempts"] for item in summaries)
    if unassessed:
        share = unassessed / attempts
        findings.append(
            _finding(
                "unassessed_attempts",
                "warning",
                f"{unassessed} of {attempts} check attempt(s) ({share:.1%}) have no outcome "
                "(errors, timeouts, skips). Fix the pipeline before tuning, so infrastructure "
                "failures are not read as model behavior.",
                value=share,
                items=_unassessed_items(runs),
            )
        )

    # 5. Single attempts: variance cannot be observed at all.
    if all(item["max_attempts"] <= 1 for item in summaries):
        findings.append(
            _finding(
                "single_attempt",
                "info",
                "Every check was recorded once, so run-to-run variation cannot be observed. "
                "Record repeated attempts (Inspect --epochs, promptfoo --repeat).",
            )
        )

    # 6. Resolvable change versus the smallest change that matters.
    reference = summaries[-1]
    noise = _noise(reference, min_effect)
    if noise and min_effect is not None and noise["resolvable_change"] > min_effect:
        findings.append(
            _finding(
                "noise_exceeds_min_effect",
                "warning",
                f"At {reference['assessed']} assessed check attempts and a "
                f"{reference['pass_rate']:.1%} "
                f"pass rate, only changes larger than about {noise['resolvable_change']:.1%} "
                f"separate from sampling noise, above the {min_effect:.1%} you want to detect. "
                f"Record about {noise['attempts_for_min_effect']} assessed check attempts per run "
                "(more cases or more repetitions).",
                value=noise["resolvable_change"],
            )
        )

    # 7. The same recorded output graded both passed and failed: grader variation.
    inconsistent = []
    for case_id, check in sorted(combined):
        sides = [
            (run["cases"].get(case_id, {}).get(check), run["outputs"].get(case_id, {}).get(check))
            for run in runs
        ]
        conflicts = grading_conflicts(sides)
        if conflicts:
            inconsistent.append(
                {
                    "case_id": case_id,
                    "check": check,
                    **combined[(case_id, check)],
                    "detail": f"{conflicts} identical output(s) graded both passed and failed",
                }
            )
    if inconsistent:
        findings.append(
            _finding(
                "inconsistent_grading",
                "warning",
                f"{len(inconsistent)} check(s) gave different verdicts to byte-identical "
                "recorded outputs. The grader is nondeterministic or changed between files, "
                "so score movement on these checks is not evidence about the agent. Use a "
                "deterministic check where the output space allows, or pin and regrade with "
                "evalarc trace-stability.",
                items=inconsistent,
            )
        )
    recorded_outputs = sum(
        1
        for run in runs
        for digests in run["outputs"].values()
        for values in digests.values()
        for value in values
        if value is not None
    )

    # 8. Outputs cut off by a token limit are infrastructure, not behavior.
    truncated = []
    for run in runs:
        for case_id, metas in sorted(run["samples"].items()):
            count = sum(1 for meta in metas if meta.get("truncated"))
            if count:
                reasons = sorted(
                    {meta.get("stop_reason") or meta.get("limit") or "limit" for meta in metas}
                    - {None}
                )
                truncated.append(
                    {
                        "file": run["source"]["name"],
                        "case_id": case_id,
                        "check": "(output)",
                        "passed": 0,
                        "assessed": count,
                        "attempts": len(metas),
                        "detail": (
                            f"{count}/{len(metas)} attempt(s) truncated ({', '.join(reasons)})"
                        ),
                    }
                )
    if truncated:
        findings.append(
            _finding(
                "truncated_outputs",
                "warning",
                f"{sum(item['assessed'] for item in truncated)} attempt(s) in {len(truncated)} "
                "case(s) stopped at a token limit. Raise the limit or shorten the task before "
                "tuning; a truncated answer measures the budget, not the model.",
                items=truncated,
            )
        )

    # 9. A model grading its own outputs.
    self_graded = sorted({model for run in runs for model in run["graders"]["self_graded"]})
    if self_graded:
        defaults = sorted(
            {check for run in runs for check in run["graders"]["default_grader_checks"]}
        )
        findings.append(
            _finding(
                "self_graded",
                "warning",
                f"{', '.join(self_graded)} grades its own outputs"
                + (
                    f" (model-graded scorers without a grader model: {', '.join(defaults)})"
                    if defaults
                    else ""
                )
                + ". Specify a separate judge model; a model tends to accept its own answers.",
                value=None,
            )
        )

    # 10. A model judge where a programmatic check would do.
    small = []
    for run in runs:
        prefixes = run["graders"].get("model_graded_checks") or []
        for case_check in _model_graded(run, prefixes):
            small.append(case_check)
    replaceable = _small_output_space(runs, small)
    if replaceable:
        findings.append(
            _finding(
                "model_judge_replaceable",
                "info",
                f"{len(replaceable)} model-graded check(s) only ever saw a few distinct "
                "outputs or JSON outputs. When the output space is this small, an exact "
                "match, a fixed label set or a JSON schema check is cheaper and "
                "deterministic; keep a model judge for open-ended outputs.",
                items=replaceable,
            )
        )

    # 11. A requested thinking setting that left no trace in recorded usage.
    unapplied = []
    for run in runs:
        config = run.get("generate_config") or {}
        effort = config.get("reasoning_effort")
        budget = config.get("reasoning_tokens")
        requested = (isinstance(effort, str) and effort not in ("none", "minimal")) or (
            isinstance(budget, (int, float)) and not isinstance(budget, bool) and budget > 0
        )
        reported = [
            item["reasoning_tokens"]
            for items in run["usage"].values()
            for item in items
            if "reasoning_tokens" in item
        ]
        if requested and reported and not any(reported):
            unapplied.append(
                {
                    "file": run["source"]["name"],
                    "case_id": "(all cases)",
                    "check": "(config)",
                    "passed": 0,
                    "assessed": len(reported),
                    "attempts": len(reported),
                    "detail": (
                        f"requested {', '.join(f'{k}={v}' for k, v in config.items())}; "
                        f"0 reasoning tokens in {len(reported)} attempt(s)"
                    ),
                }
            )
    if unapplied:
        findings.append(
            _finding(
                "config_not_applied",
                "warning",
                f"{len(unapplied)} file(s) request extended thinking but record zero reasoning "
                "tokens on every attempt. The setting may not have reached the model (wrong "
                "parameter name, unsupported model, or an override), so results may not "
                "reflect the configuration under test.",
                items=unapplied,
            )
        )

    # 12. Stronger configurations should not score lower.
    order = []
    if ordered:
        for weaker, stronger in zip(summaries, summaries[1:]):
            if weaker["pass_rate"] is None or stronger["pass_rate"] is None:
                continue
            low_w, high_w = _wilson_interval(weaker["passed"], weaker["assessed"])
            low_s, high_s = _wilson_interval(stronger["passed"], stronger["assessed"])
            within = low_w <= high_s and low_s <= high_w
            step = {
                "weaker": weaker["source"]["name"],
                "stronger": stronger["source"]["name"],
                "delta": stronger["pass_rate"] - weaker["pass_rate"],
                "within_sampling_noise": within,
            }
            order.append(step)
            if step["delta"] < 0:
                findings.append(
                    _finding(
                        "capability_inversion",
                        "info" if within else "warning",
                        f"{step['stronger']} scores {-step['delta']:.1%} below {step['weaker']}"
                        + (
                            " (within sampling noise)."
                            if within
                            else ". A stronger model or more thinking should not score lower; "
                            "check for ambiguous tasks or a miscalibrated grader."
                        ),
                        value=step["delta"],
                    )
                )

    provenance = None
    if cases_manifest is not None:
        from evalarc import provenance as case_provenance

        case_ids = {case for run in runs for case in run["cases"]}
        provenance = case_provenance.review(cases_manifest, case_ids)
        findings += case_provenance.findings(provenance, len(case_ids), _finding)

    triage = _triage(runs[-1], inconsistent, truncated, combined)
    size = _size(summaries)
    warnings = sum(item["severity"] == "warning" for item in findings)
    return {
        "schema_version": SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "format": runs[0]["format"],
        "numeric_pass_threshold": runs[0]["threshold"],
        "saturation": saturation,
        "min_effect": min_effect,
        "ordered": ordered,
        "runs": summaries,
        "noise": noise,
        "capability_order": order,
        "graders": {
            "subject_models": sorted({m for run in runs for m in run["graders"]["subject_models"]}),
            "grader_models": sorted({m for run in runs for m in run["graders"]["grader_models"]}),
            "self_graded": self_graded,
        },
        "recorded_outputs": recorded_outputs,
        "triage": triage,
        "size": size,
        "provenance": provenance,
        "findings": findings,
        "warnings": warnings,
        "healthy": warnings == 0,
        "scope": SCOPE,
    }


def render_markdown(result: dict) -> str:
    verdict = (
        "no warnings" if result["healthy"] else f"{result['warnings']} warning(s) before tuning"
    )
    lines = [f"### EvalArc eval health: {verdict}", ""]
    lines += [
        "| File | Cases | Checks | Pass rate | 95% interval | Max attempts | Unassessed |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for run in result["runs"]:
        rate = "—" if run["pass_rate"] is None else f"{run['pass_rate']:.1%}"
        lines.append(
            f"| {_cell(run['source']['name'])} | {run['cases']} | {run['checks']} | {rate} | "
            f"{_interval_text(run['interval_95'])} | "
            f"{run['max_attempts']} | {run['attempts'] - run['assessed']} |"
        )
    noise = result["noise"]
    if noise:
        lines += [
            "",
            f"Resolvable change at the last file's size: about **{noise['resolvable_change']:.1%}**"
            + (
                f" (minimum effect {result['min_effect']:.1%} needs about "
                f"{noise['attempts_for_min_effect']} assessed check attempts)."
                if noise.get("attempts_for_min_effect")
                else "."
            ),
        ]
    size = result.get("size")
    if size:
        recorded = size["recorded_seconds_per_configuration"]
        lines += [
            "",
            f"Size: {size['cases']} cases × {size['attempts_per_case']} attempt(s) × "
            f"{size['configurations']} configuration(s)"
            + (f"; {recorded:.1f} s recorded per configuration" if recorded is not None else "")
            + (
                f", ${size['recorded_cost_usd_per_configuration']:.4f}"
                if size["recorded_cost_usd_per_configuration"] is not None
                else ""
            )
            + ".",
        ]
    planned = result.get("plan")
    if planned:
        lines += [
            "",
            f"Plan: {planned['cases']} cases × {planned['attempts_per_case']} attempt(s) × "
            f"{planned['configurations']} configuration(s) = {planned['case_attempts']} case "
            "attempts"
            + (
                f", about {planned['serial_seconds'] / 60:.1f} min serial"
                if planned["serial_seconds"] is not None
                else ", runtime unknown (no recorded durations)"
            )
            + (f", about ${planned['cost_usd']:.2f}" if planned["cost_usd"] is not None else "")
            + ".",
        ]
    provenance = result.get("provenance")
    if provenance:
        lines += [
            "",
            "Declared case sources: "
            + ", ".join(f"{name} {count}" for name, count in provenance["counts"].items())
            + (f", undeclared {len(provenance['undeclared'])}" if provenance["undeclared"] else "")
            + ".",
        ]
    triage = result.get("triage") or []
    if triage:
        lines += [
            "",
            f"Failure triage for {_cell(result['runs'][-1]['source']['name'])} "
            "(classify before changing anything):",
            "",
            "| Case | Category | Failing checks | Next step |",
            "| --- | --- | --- | --- |",
        ]
        for row in triage[:30]:
            lines.append(
                f"| {_cell(row['case_id'])} | `{row['category']}` | "
                f"{_cell(', '.join(row['checks'])[:80])} | {TRIAGE_NEXT[row['category']]} |"
            )
        if len(triage) > 30:
            lines.append(f"\n{len(triage) - 30} more cases are in `health.json`.")
    lines.append("")
    if result["findings"]:
        for finding in result["findings"]:
            lines.append(f"- **{finding['severity']} · `{finding['id']}`**: {finding['message']}")
            for item in (finding.get("items") or [])[:10]:
                where = f"{item['file']} · " if "file" in item else ""
                detail = item.get("detail") or (
                    f"{item['passed']}/{item['assessed']} passed"
                    + (
                        f", {item['attempts'] - item['assessed']} unassessed"
                        if item["attempts"] != item["assessed"]
                        else ""
                    )
                )
                lines.append(
                    f"  - {where}{_cell(item['case_id'])} / {_cell(item['check'])}: {detail}"
                )
            extra = len(finding.get("items") or []) - 10
            if extra > 0:
                lines.append(f"  - {extra} more in `health.json`")
    else:
        lines.append("No findings.")
    lines += ["", f"<sub>{result['scope']}</sub>"]
    return "\n".join(lines) + "\n"


def render_html(result: dict, destination: Path) -> None:
    from evalarc.report import _card, _esc, _page

    best = max((run["pass_rate"] or 0 for run in result["runs"]), default=0)
    body = (
        '<div class="cards">'
        + _card(result["warnings"], "warnings", alert=not result["healthy"])
        + _card(f"{best:.1%}", "best pass rate")
        + _card(
            "—" if not result["noise"] else f"{result['noise']['resolvable_change']:.1%}",
            "resolvable change",
        )
        + _card(len(result["runs"]), "result files")
        + "</div>"
    )
    body += (
        '<h2>Runs</h2><div class="scroll"><table><thead><tr><th>File</th><th>Cases</th>'
        "<th>Checks</th><th>Pass rate</th><th>95% interval</th><th>Max attempts</th>"
        "<th>Unassessed</th>"
        "<th>SHA-256</th></tr></thead><tbody>"
    )
    for run in result["runs"]:
        rate = "—" if run["pass_rate"] is None else f"{run['pass_rate']:.1%}"
        body += (
            f"<tr><td><code>{_esc(run['source']['name'])}</code></td><td>{run['cases']}</td>"
            f"<td>{run['checks']}</td><td>{_esc(rate)}</td>"
            f"<td>{_esc(_interval_text(run['interval_95']))}</td><td>{run['max_attempts']}</td>"
            f"<td>{run['attempts'] - run['assessed']}</td>"
            f"<td><code>{_esc(run['source']['sha256'][:16])}…</code></td></tr>"
        )
    body += "</tbody></table></div>"
    if result.get("triage"):
        body += (
            "<h2>Failure triage</h2><p>Failing cases in the last file, classified before any "
            'change is attempted.</p><div class="scroll"><table><thead><tr><th>Case</th>'
            "<th>Category</th><th>Failing checks</th><th>Next step</th></tr></thead><tbody>"
        )
        for row in result["triage"]:
            body += (
                f"<tr><td><code>{_esc(row['case_id'])}</code></td>"
                f"<td><code>{_esc(row['category'])}</code></td>"
                f"<td>{_esc(', '.join(row['checks']))}</td>"
                f"<td>{_esc(TRIAGE_NEXT[row['category']])}</td></tr>"
            )
        body += "</tbody></table></div>"
    body += result.get("_cases_html", "")
    body += "<h2>Findings</h2>"
    if not result["findings"]:
        body += "<p>No findings.</p>"
    for finding in result["findings"]:
        tone = "failed" if finding["severity"] == "warning" else "passed"
        body += (
            f'<h3><span class="{tone}">{_esc(finding["severity"])}</span> · '
            f"<code>{_esc(finding['id'])}</code></h3><p>{_esc(finding['message'])}</p>"
        )
        items = finding.get("items") or []
        if items:
            body += (
                '<div class="scroll"><table><thead><tr><th>File</th><th>Case</th><th>Check</th>'
                "<th>Passed</th><th>Assessed</th><th>Attempts</th></tr></thead><tbody>"
            )
            for item in items[:200]:
                if item.get("detail"):
                    counts = f'<td colspan="3">{_esc(item["detail"])}</td>'
                else:
                    counts = (
                        f"<td>{item['passed']}</td><td>{item['assessed']}</td>"
                        f"<td>{item['attempts']}</td>"
                    )
                body += (
                    f"<tr><td>{_esc(item.get('file', 'all files'))}</td>"
                    f"<td><code>{_esc(item['case_id'])}</code></td><td>{_esc(item['check'])}</td>"
                    f"{counts}</tr>"
                )
            body += "</tbody></table></div>"
    body += (
        '<p><a href="health.json">Health JSON</a> · <a href="summary.md">Markdown summary</a>'
        f"</p><footer>{_esc(result['scope'])}</footer>"
    )
    _page("Eval health", "Is this evaluation ready to tune against?", body, destination)


def command(args) -> int:
    """Run `evalarc eval-health`; exit 0 healthy or not required, 1 warnings, 2 bad input."""
    from evalarc.artifacts import new_run
    from evalarc.evaluate import write_json

    try:
        runs = [load_results(path, args.format, args.threshold) for path in args.results]
        manifest = None
        if args.cases:
            from evalarc.provenance import load as load_manifest

            manifest = load_manifest(args.cases)
        result = health(runs, args.saturation, args.min_effect, args.ordered, manifest)
        if args.plan_attempts is not None or args.plan_configs is not None:
            size = result["size"]
            result["plan"] = plan(
                size,
                size["attempts_per_case"] if args.plan_attempts is None else args.plan_attempts,
                size["configurations"] if args.plan_configs is None else args.plan_configs,
            )
        if args.output:
            with new_run(args.output) as output:
                for index, (path, run) in enumerate(zip(args.results, runs), start=1):
                    data = path.read_bytes()
                    if hashlib.sha256(data).hexdigest() != run["source"]["sha256"]:
                        raise ValueError(f"{path} changed while it was being read")
                    (output / "inputs").mkdir(exist_ok=True)
                    (output / "inputs" / f"{index:02d}{path.suffix or '.json'}").write_bytes(data)
                if manifest is not None:
                    data = args.cases.read_bytes()
                    if hashlib.sha256(data).hexdigest() != manifest["source"]["sha256"]:
                        raise ValueError(f"{args.cases} changed while it was being read")
                    (output / "cases.json").write_bytes(data)
                write_json(output / "health.json", result)
                (output / "cases.jsonl").write_text(case_lines(runs), encoding="utf-8")
                (output / "summary.md").write_text(render_markdown(result), encoding="utf-8")
                render_html({**result, "_cases_html": cases_html(runs[-1])}, output / "index.html")
        if args.markdown:
            with args.markdown.open("a", encoding="utf-8") as summary:
                summary.write(render_markdown(result))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as error:
        print(f"evalarc: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        rates = ", ".join(
            f"{run['source']['name']} {_rate_text(run['pass_rate'])}" for run in result["runs"]
        )
        print(f"Eval health: {result['warnings']} warning(s) | Pass rate: {rates}")
        for finding in result["findings"]:
            print(f"  {finding['severity']}: {finding['id']} — {finding['message']}")
        if args.output:
            print(f"Report: {args.output / 'index.html'}")
    return 1 if args.require_healthy and not result["healthy"] else 0


# --- per-case records ---------------------------------------------------------------

MAX_CASE_ROWS = 2000
MAX_HTML_OUTPUT = 2000


def case_lines(runs: list[dict]) -> str:
    """One JSON line per file, case and attempt: verdicts, output, stop reason, usage."""
    lines = []
    for run in runs:
        for case_id, metas in sorted(run["samples"].items()):
            usage = run["usage"].get(case_id, [])
            for attempt, meta in enumerate(metas):
                lines.append(
                    json.dumps(
                        {
                            "file": run["source"]["name"],
                            "case_id": case_id,
                            "attempt": attempt,
                            "verdicts": meta.get("verdicts") or {},
                            "output": meta.get("output_text"),
                            "stop_reason": meta.get("stop_reason"),
                            "truncated": bool(meta.get("truncated")),
                            "usage": usage[attempt] if attempt < len(usage) else {},
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
        if not run["samples"]:
            for case_id, checks in sorted(run["cases"].items()):
                lines.append(
                    json.dumps(
                        {
                            "file": run["source"]["name"],
                            "case_id": case_id,
                            "checks": {
                                check: [item["passed"] for item in attempts]
                                for check, attempts in checks.items()
                            },
                        },
                        sort_keys=True,
                    )
                )
    return "\n".join(lines) + ("\n" if lines else "")


def cases_html(run: dict) -> str:
    """Per-case scores for one file, each linking to its recorded outputs (FIG 4 page)."""
    from evalarc.report import _esc

    rows, details = [], []
    for index, (case_id, checks) in enumerate(sorted(run["cases"].items())[:MAX_CASE_ROWS]):
        tallies = {check: _tally(attempts) for check, attempts in checks.items()}
        passed = sum(t["passed"] for t in tallies.values())
        assessed = sum(t["assessed"] for t in tallies.values())
        failing = sorted(c for c, t in tallies.items() if t["passed"] < t["attempts"])
        anchor = f"case-{index}"
        outputs = run["samples"].get(case_id, [])
        rows.append(
            f"<tr><td><code>{_esc(case_id)}</code></td>"
            f"<td>{passed}/{assessed}</td><td>{_esc(', '.join(failing) or '—')}</td>"
            + (
                f'<td><a href="#{anchor}">{len(outputs)} output(s)</a></td></tr>'
                if outputs
                else "<td>—</td></tr>"
            )
        )
        if outputs:
            body = "".join(
                f"<p>Attempt {n + 1} · "
                + _esc(
                    ", ".join(
                        f"{c}: {'pass' if v else 'fail' if v is False else 'unassessed'}"
                        for c, v in sorted((meta.get("verdicts") or {}).items())
                    )
                )
                + (f" · stop {_esc(meta['stop_reason'])}" if meta.get("stop_reason") else "")
                + f"</p><pre>{_esc((meta.get('output_text') or '—')[:MAX_HTML_OUTPUT])}</pre>"
                for n, meta in enumerate(outputs)
            )
            details.append(
                f'<details id="{anchor}"><summary><code>{_esc(case_id)}</code></summary>'
                f"{body}</details>"
            )
    return (
        f"<h2>Cases in {_esc(run['source']['name'])}</h2>"
        "<p>Every case with its passing check attempts; follow a link to read the recorded "
        'outputs before trusting the grader. <a href="cases.jsonl">cases.jsonl</a> has one '
        'line per attempt.</p><div class="scroll"><table><thead><tr><th>Case</th>'
        "<th>Passed</th><th>Failing checks</th><th>Outputs</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
        + "".join(details)
    )


# --- helpers ----------------------------------------------------------------------


TRIAGE_NEXT = {
    "pipeline": "Fix the error, timeout or skip; not a model failure",
    "truncated": "Raise the token limit or shorten the task",
    "grader_inconsistent": "Fix or pin the grader before tuning",
    "never_passes": "Read the task and grader for ambiguity or an unstated requirement",
    "regressed": "Passed in an earlier file; inspect what the change broke",
    "variable": "Add attempts; separate agent from grader variation",
    "consistent_failure": "Candidate for a root-cause fix to the prompt, skill or tools",
}


def _triage(run: dict, inconsistent: list, truncated: list, combined: dict) -> list[dict]:
    """Classify each failing case in one run by the likeliest cause (first match wins).

    `combined` pools every file, so a check that passed anywhere is not "never_passes".
    """
    grader = {(row["case_id"], row["check"]) for row in inconsistent}
    cut = {row["case_id"] for row in truncated if row.get("file") == run["source"]["name"]}
    rows = []
    for case_id, checks in sorted(run["cases"].items()):
        tallies = {check: _tally(attempts) for check, attempts in checks.items()}
        failing = sorted(
            check for check, tally in tallies.items() if tally["passed"] < tally["attempts"]
        )
        if not failing:
            continue
        if any(tallies[check]["assessed"] < tallies[check]["attempts"] for check in failing):
            category = "pipeline"
        elif case_id in cut:
            category = "truncated"
        elif any((case_id, check) in grader for check in failing):
            category = "grader_inconsistent"
        elif all(tallies[check]["passed"] == 0 for check in failing) and any(
            combined[(case_id, check)]["passed"] > 0 for check in failing
        ):
            category = "regressed"
        elif all(tallies[check]["passed"] == 0 for check in failing) and all(
            combined[(case_id, check)]["assessed"] >= 2 for check in failing
        ):
            category = "never_passes"
        elif any(tallies[check]["passed"] > 0 for check in failing):
            category = "variable"
        else:
            category = "consistent_failure"
        rows.append({"case_id": case_id, "category": category, "checks": failing})
    return rows


SMALL_OUTPUT_SPACE = 10
MIN_GRADED_ATTEMPTS = 10


def _model_graded(run: dict, names: list[str]):
    """(file, check) for checks produced by a model-graded scorer or assertion."""
    seen = set()
    for checks in run["cases"].values():
        for check in checks:
            if any(check == name or check.startswith(f"{name}/") for name in names):
                seen.add(check)
    return [(run["source"]["name"], check) for check in sorted(seen)]


def _small_output_space(runs: list[dict], graded: list) -> list[dict]:
    by_file = {run["source"]["name"]: run for run in runs}
    items = []
    for name, check in sorted(set(graded)):
        run = by_file[name]
        texts = [
            meta.get("output_text")
            for case_id, metas in run["samples"].items()
            for meta in metas
            if check in (meta.get("verdicts") or {}) and meta.get("output_text") is not None
        ]
        if len(texts) < MIN_GRADED_ATTEMPTS:
            continue
        distinct = {" ".join(text.split()).casefold() for text in texts}
        json_like = all(_is_json(text) for text in texts)
        if len(distinct) <= SMALL_OUTPUT_SPACE or json_like:
            items.append(
                {
                    "file": name,
                    "case_id": "(all cases)",
                    "check": check,
                    "passed": 0,
                    "assessed": len(texts),
                    "attempts": len(texts),
                    "detail": (
                        f"{len(texts)} graded outputs, all JSON"
                        if json_like
                        else f"{len(texts)} graded outputs, {len(distinct)} distinct"
                    ),
                }
            )
    return items


def _is_json(text: str) -> bool:
    stripped = text.strip()
    if not stripped.startswith(("{", "[")):
        return False
    try:
        json.loads(stripped)
    except ValueError:
        return False
    return True


def _interval_text(interval: list | None) -> str:
    return "—" if not interval else f"{interval[0]:.1%}–{interval[1]:.1%}"


def _rate_text(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def _run_summary(run: dict) -> dict:
    passed = assessed = attempts = checks = repeated = max_attempts = 0
    for check_map in run["cases"].values():
        for check_attempts in check_map.values():
            tally = _tally(check_attempts)
            passed += tally["passed"]
            assessed += tally["assessed"]
            attempts += tally["attempts"]
            checks += 1
            repeated += tally["assessed"] >= 2
            max_attempts = max(max_attempts, tally["attempts"])
    return {
        "source": run["source"],
        "identity": run["identity"],
        "incomplete": run["incomplete"],
        "cases": len(run["cases"]),
        "checks": checks,
        "repeated_checks": repeated,
        "max_attempts": max_attempts,
        "passed": passed,
        "assessed": assessed,
        "attempts": attempts,
        "pass_rate": passed / assessed if assessed else None,
        "interval_95": wilson(passed, assessed),
        "mean_duration_seconds": _mean_usage(run, "duration_seconds"),
        "mean_cost_usd": _mean_usage(run, "cost_usd"),
        "total_duration_seconds": _total_usage(run, "duration_seconds"),
        "total_cost_usd": _total_usage(run, "cost_usd"),
        "generate_config": run.get("generate_config") or {},
        "truncated_attempts": sum(
            1 for metas in run["samples"].values() for meta in metas if meta.get("truncated")
        ),
    }


def _total_usage(run: dict, name: str) -> float | None:
    values = [item[name] for items in run["usage"].values() for item in items if name in item]
    return sum(values) if values else None


def _size(summaries: list[dict]) -> dict:
    """Recorded evaluation size: cases x attempts x configurations, and recorded cost."""
    last = summaries[-1]
    case_attempts = max(1, last["max_attempts"])
    return {
        "configurations": len(summaries),
        "cases": last["cases"],
        "attempts_per_case": case_attempts,
        "case_attempts_per_configuration": last["cases"] * case_attempts,
        "mean_seconds_per_attempt": last["mean_duration_seconds"],
        "recorded_seconds_per_configuration": last["total_duration_seconds"],
        "recorded_cost_usd_per_configuration": last["total_cost_usd"],
    }


def plan(size: dict, attempts: int, configurations: int) -> dict:
    """Estimate a planned run from the recorded per-attempt duration and cost."""
    if attempts < 1 or configurations < 1:
        raise ValueError("--plan-attempts and --plan-configs must be at least 1")
    total = size["cases"] * attempts * configurations
    recorded = size["cases"] * size["attempts_per_case"]
    seconds = size["mean_seconds_per_attempt"]
    cost = size["recorded_cost_usd_per_configuration"]
    out = {
        "cases": size["cases"],
        "attempts_per_case": attempts,
        "configurations": configurations,
        "case_attempts": total,
        "serial_seconds": None if seconds is None else seconds * total,
        "cost_usd": None if cost is None or not recorded else cost / recorded * total,
    }
    return out


def _mean_usage(run: dict, name: str) -> float | None:
    values = [item[name] for items in run["usage"].values() for item in items if name in item]
    return sum(values) / len(values) if values else None


def _noise(summary: dict, min_effect: float | None) -> dict | None:
    """Smallest pass-rate change two runs of this size can separate.

    Two runs separate when their 95% intervals do not overlap, i.e. the change exceeds
    twice the normal-approximation half-width at the observed rate. This matches the
    Wilson-overlap rule `evalarc diff` uses. The rate is clamped one attempt away from
    0 and 1 so saturated runs do not report zero noise.
    """
    n = summary["assessed"]
    if not n or summary["pass_rate"] is None:
        return None
    p = min(max(summary["pass_rate"], 1 / (n + 1)), n / (n + 1))
    half = Z * math.sqrt(p * (1 - p) / n)
    result = {
        "assessed_attempts": n,
        "pass_rate": summary["pass_rate"],
        "resolvable_change": min(1.0, 2 * half),
    }
    if min_effect is not None:
        result["attempts_for_min_effect"] = math.ceil((2 * Z) ** 2 * p * (1 - p) / min_effect**2)
    return result


def _unassessed_items(runs: list[dict]) -> list[dict]:
    items = []
    for run in runs:
        for case_id, checks in sorted(run["cases"].items()):
            for check, attempts in sorted(checks.items()):
                tally = _tally(attempts)
                if tally["assessed"] < tally["attempts"]:
                    items.append(
                        {"file": run["source"]["name"], "case_id": case_id, "check": check, **tally}
                    )
    return items


def _finding(identifier: str, severity: str, message: str, *, items=None, value=None) -> dict:
    finding = {"id": identifier, "severity": severity, "message": message}
    if value is not None:
        finding["value"] = value
    if items is not None:
        finding["items"] = items
    return finding

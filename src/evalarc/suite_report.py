"""Rendering of the capability/regression suite section of ``evalarc diff --cases``."""

from __future__ import annotations

import re

from evalarc.results_diff import _cell

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def console_text(value: object) -> str:
    """One console line: control characters (CR, LF, ESC) become spaces, so an untrusted
    case ID cannot start a new line such as a GitHub workflow command."""
    return _CONTROL.sub(" ", str(value))


def _pick(by_k: list[dict]) -> list[dict]:
    """k = 1 and the largest k recorded on that side."""
    if not by_k:
        return []
    return [row for row in by_k if row["k"] in (1, by_k[-1]["k"])]


def _rate(row: dict | None, key: str) -> str:
    return "—" if row is None else f"{row[key]:.1%}"


def _rows(side: dict) -> dict[int, dict]:
    return {row["k"]: row for row in side["by_k"]}


def console_lines(result: dict) -> list[str]:
    review = result.get("suites")
    if not review:
        return []
    lines = []
    for role, item in review["suites"].items():
        before, after = _rows(item["baseline"]), _rows(item["current"])
        ks = sorted(set(before) | set(after))
        top = ks[-1] if ks else None
        parts = [f"{role} suite: {item['cases']} case(s)"]
        for k in sorted({1, top} - {None}):
            parts.append(
                f"pass^{k} {_rate(before.get(k), 'pass_hat_k')} -> "
                f"{_rate(after.get(k), 'pass_hat_k')}"
            )
        lines.append(" | ".join(parts))
    failures = review["regression_failures"]
    if failures:
        lines.append(f"{len(failures)} regression-suite case(s) did not succeed on every trial:")
        lines += [f"  {console_text(item['case_id'])}: {item['detail']}" for item in failures[:10]]
    if result.get("regression_suite_required") and not result.get("regression_suite_passed"):
        lines.append("The regression suite is required to pass every trial; the gate fails.")
    return lines


def render_markdown(result: dict) -> str:
    review = result["suites"]
    lines = [
        "",
        "#### Suites (case-level trials)",
        "",
        "| Suite | Cases with ≥ k assessed trials | Side | Assessed trials | k | pass@k | pass^k |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: |",
    ]
    for role, item in review["suites"].items():
        for label in ("baseline", "current"):
            side = item[label]
            shown = _pick(side["by_k"])
            if not shown:
                lines.append(f"| {role} | 0 | {label} | 0 | — | — | — |")
            for row in shown:
                lines.append(
                    f"| {role} | {row['cases']} | {label} | {side['assessed_trials']} | "
                    f"{row['k']} | {row['pass_at_k']:.1%} | {row['pass_hat_k']:.1%} |"
                )
    failures = review["regression_failures"]
    if failures:
        required = result.get("regression_suite_required")
        lines += [
            "",
            f"**{len(failures)} regression-suite case(s)** did not succeed on every trial of "
            "the current run"
            + ("; the gate fails:" if required else " (add --require-regression-suite to gate):"),
            "",
        ]
        lines += [f"- {_cell(item['case_id'])}: {_cell(item['detail'])}" for item in failures[:20]]
        if len(failures) > 20:
            lines.append(f"- {len(failures) - 20} more in `diff.json`")
    if review["undeclared_cases"]:
        lines += [
            "",
            f"{len(review['undeclared_cases'])} case(s) declare no suite and are not counted "
            "in either suite.",
        ]
    lines.append("")
    return "\n".join(lines)


def render_html(result: dict, esc) -> str:
    review = result["suites"]
    body = (
        "<h2>Suites</h2><p>Case-level trials per declared suite. A trial succeeds only when "
        "every check passed. Capability cases may start low; regression cases should "
        'succeed on every trial.</p><div class="scroll"><table><caption>pass@k and pass^k '
        "by suite, side and k</caption><thead><tr><th>Suite</th><th>Side</th><th>k</th>"
        "<th>Cases with at least k assessed trials</th><th>pass@k</th><th>pass^k</th>"
        "</tr></thead><tbody>"
    )
    for role, item in review["suites"].items():
        for label in ("baseline", "current"):
            side = item[label]
            if not side["by_k"]:
                body += (
                    f"<tr><td>{esc(role)}</td><td>{esc(label)}</td>"
                    '<td colspan="4">No assessed trials</td></tr>'
                )
            for row in side["by_k"]:
                body += (
                    f"<tr><td>{esc(role)}</td><td>{esc(label)}</td><td>{row['k']}</td>"
                    f"<td>{row['cases']}</td><td>{row['pass_at_k']:.1%}</td>"
                    f"<td>{row['pass_hat_k']:.1%}</td></tr>"
                )
    body += "</tbody></table></div>"
    failures = review["regression_failures"]
    if failures:
        body += (
            "<h3>Regression-suite cases that did not succeed on every trial</h3>"
            '<div class="scroll"><table><thead><tr><th>Case</th><th>Current run</th></tr>'
            "</thead><tbody>"
            + "".join(
                f"<tr><td><code>{esc(item['case_id'])}</code></td><td>{esc(item['detail'])}</td>"
                "</tr>"
                for item in failures
            )
            + "</tbody></table></div>"
        )
    return body


# --- case attributes (expect_action, expect_change, impact, owner) ----------------


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def _behavior_rows(view: dict) -> list[tuple[str, str, str, str, str]]:
    rows = []
    sides = view.get("behavior") or {}
    for polarity, rate in (("act", "undertrigger_rate"), ("abstain", "overtrigger_rate")):
        before = (sides.get("baseline") or {}).get(polarity)
        after = (sides.get("current") or {}).get(polarity)
        if not before and not after:
            continue
        cases = (after or before)["cases"]
        rows.append(
            (
                polarity,
                str(cases),
                rate.replace("_", " "),
                _pct((before or {}).get(rate)),
                _pct((after or {}).get(rate)),
            )
        )
    return rows


def attributes_console(result: dict) -> list[str]:
    view = result.get("case_attributes")
    if not view:
        return []
    lines = [
        f"{polarity} cases ({cases}): {name} {before} -> {after}"
        for polarity, cases, name, before, after in _behavior_rows(view)
    ]
    changes = view.get("expected_changes")
    if changes:
        f2p, p2p = changes["fail_to_pass"], changes["pass_to_pass"]
        lines.append(
            f"fail_to_pass: {len(f2p['resolved'])}/{f2p['cases']} resolved | pass_to_pass: "
            f"{len(p2p['broken'])}/{p2p['cases']} broken"
        )
        lines += [
            f"  unresolved: {console_text(item['case_id'])}" for item in f2p["unresolved"][:10]
        ]
        lines += [f"  broken: {console_text(item['case_id'])}" for item in p2p["broken"][:10]]
    for item in (view.get("blocking_by_impact") or [])[:10]:
        lines.append(
            f"  {item['impact'] or 'impact undeclared'}: {console_text(item['case_id'])} / "
            f"{console_text(item['check'])}"
            + (f" (owner {console_text(item['owner'])})" if item.get("owner") else "")
        )
    if result.get("f2p_required") and not result.get("f2p_passed"):
        lines.append(
            "Every fail_to_pass case must be resolved and no pass_to_pass case broken;"
            " the gate fails."
        )
    return lines


def attributes_markdown(result: dict) -> str:
    view = result["case_attributes"]
    lines = ["", "#### Case attributes", ""]
    rows = _behavior_rows(view)
    if rows:
        lines += [
            "| Expected | Cases | Error rate | Baseline | Current |",
            "| --- | ---: | --- | ---: | ---: |",
        ]
        lines += [f"| {p} | {c} | {n} | {b} | {a} |" for p, c, n, b, a in rows]
        lines += [
            "",
            "An act case fails when the agent did not act (undertriggering); an abstain case "
            "fails when it acted (overtriggering). Watch both: improving one by moving the "
            "threshold usually worsens the other.",
            "",
        ]
    changes = view.get("expected_changes")
    if changes:
        f2p, p2p = changes["fail_to_pass"], changes["pass_to_pass"]
        required = result.get("f2p_required")
        lines += [
            f"Fail-to-pass: **{len(f2p['resolved'])}/{f2p['cases']}** resolved on every current "
            f"trial · pass-to-pass: **{len(p2p['broken'])}/{p2p['cases']}** broken"
            + (
                f" — `--require-f2p` **{'pass' if result.get('f2p_passed') else 'fail'}**"
                if required
                else ""
            ),
            "",
        ]
        lines += [
            f"- unresolved {_cell(item['case_id'])}: {item['successes']}/{item['trials']} "
            "trial(s) succeeded"
            for item in f2p["unresolved"][:20]
        ]
        lines += [
            f"- broken {_cell(item['case_id'])}: {item['successes']}/{item['trials']} "
            f"trial(s) succeeded (baseline {item['baseline_trials']}/{item['baseline_trials']})"
            for item in p2p["broken"][:20]
        ]
        if f2p["already_passing_on_baseline"]:
            lines.append(
                f"- {len(f2p['already_passing_on_baseline'])} fail_to_pass case(s) already "
                "passed on the baseline; check the labels"
            )
        lines.append("")
    blocking = view.get("blocking_by_impact") or []
    if blocking:
        lines += [
            "Blocking changes by impact:",
            "",
            "| Impact | Case | Check | Change | Owner |",
            "| --- | --- | --- | --- | --- |",
        ]
        lines += [
            f"| {item['impact'] or '—'} | {_cell(item['case_id'])} | {_cell(item['check'])} | "
            f"{item['kind'].replace('_', ' ')} | "
            f"{_cell(item['owner']) if item.get('owner') else '—'} |"
            for item in blocking[:30]
        ]
        lines.append("")
    return "\n".join(lines)


def attributes_html(result: dict, esc) -> str:
    view = result["case_attributes"]
    body = "<h2>Case attributes</h2>"
    rows = _behavior_rows(view)
    if rows:
        body += (
            "<p>An act case fails when the agent did not act (undertriggering); an abstain case "
            "fails when it acted (overtriggering).</p>"
            '<div class="scroll"><table><caption>Over- and undertriggering</caption><thead><tr>'
            "<th>Expected</th><th>Cases</th><th>Error rate</th><th>Baseline</th><th>Current</th>"
            "</tr></thead><tbody>"
            + "".join(
                "<tr>" + "".join(f"<td>{esc(cell)}</td>" for cell in row) + "</tr>" for row in rows
            )
            + "</tbody></table></div>"
        )
    changes = view.get("expected_changes")
    if changes:
        f2p, p2p = changes["fail_to_pass"], changes["pass_to_pass"]
        body += (
            f"<p>Fail-to-pass: {len(f2p['resolved'])} of {f2p['cases']} resolved on every "
            f"current trial. Pass-to-pass: {len(p2p['broken'])} of {p2p['cases']} broken.</p>"
        )
        items = [("unresolved", item) for item in f2p["unresolved"]] + [
            ("broken", item) for item in p2p["broken"]
        ]
        if items:
            body += (
                '<div class="scroll"><table><caption>Fail-to-pass and pass-to-pass</caption>'
                "<thead><tr><th>State</th><th>Case</th><th>Current trials</th></tr></thead><tbody>"
                + "".join(
                    f"<tr><td>{esc(state)}</td><td><code>{esc(item['case_id'])}</code></td>"
                    f"<td>{item['successes']}/{item['trials']}</td></tr>"
                    for state, item in items
                )
                + "</tbody></table></div>"
            )
    blocking = view.get("blocking_by_impact") or []
    if blocking:
        body += (
            '<div class="scroll"><table><caption>Blocking changes by impact</caption><thead><tr>'
            "<th>Impact</th><th>Case</th><th>Check</th><th>Change</th><th>Owner</th></tr></thead>"
            "<tbody>"
            + "".join(
                f"<tr><td>{esc(item['impact'] or '—')}</td>"
                f"<td><code>{esc(item['case_id'])}</code></td><td>{esc(item['check'])}</td>"
                f"<td>{esc(item['kind'].replace('_', ' '))}</td>"
                f"<td>{esc(item.get('owner') or '—')}</td></tr>"
                for item in blocking
            )
            + "</tbody></table></div>"
        )
    return body

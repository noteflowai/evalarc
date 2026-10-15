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

"""index.html shows the same 'Why the gate failed' explanation as summary.md."""

import copy
import json
from pathlib import Path

from evalarc.cli import main
from evalarc.results_diff import render_html

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/results-diff"
SECTION = "<h2>Why the gate failed</h2>"
REGION = '<div class="scroll" tabindex="0" role="region" aria-label="Why the gate failed">'


def _run(tmp_path, baseline, current, name="out"):
    output = tmp_path / name
    code = main(["diff", str(baseline), str(current), "--output", str(output)])
    return code, output


def _inspect(tmp_path):
    return _run(tmp_path, EXAMPLES / "inspect/baseline.json", EXAMPLES / "inspect/current.json")


def _section(html):
    start = html.index(SECTION)
    return html[start : html.index("<h2>Inputs</h2>", start)]


def _rows(fragment):
    body = fragment.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    return [row for row in body.split("<tr>") if row]


def test_index_html_explains_each_blocking_finding(tmp_path):
    code, output = _inspect(tmp_path)
    assert code == 1
    html = (output / "index.html").read_text(encoding="utf-8")
    assert html.count(SECTION) == 1
    changed = html.index("<h2>Changed checks</h2>")
    why = html.index(SECTION)
    assert changed < why < html.index("<h2>Inputs</h2>")
    section = _section(html)
    assert "Numeric scores pass at threshold 1;" in section
    rows = _rows(section)
    assert len(rows) == 3
    for check in ("includes", "match"):
        row = next(r for r in rows if f"<code>refund-duplicate</code> / <code>{check}</code>" in r)
        assert '<span class="tone bad">✗ regressed</span>' in row
    flaky = next(r for r in rows if "<code>cancel-pending</code> / <code>match</code>" in r)
    assert '<span class="tone bad">✗ less reliable (within noise)</span>' in flaky
    assert "value <code>I</code> · evidence <code>cancel:1006:queued</code>" in flaky
    recorded = json.loads((output / "diff.json").read_text())
    for label in ("baseline", "current"):
        prefix = recorded[label]["source"]["sha256"][:12]
        assert f"{label} <code>{label}.json</code> sha256 <code>{prefix}</code>" in section


def test_summary_and_diff_json_are_unchanged(tmp_path):
    _, output = _inspect(tmp_path)
    summary = (output / "summary.md").read_text(encoding="utf-8")
    assert (
        "| less reliable (within noise) | `cancel-pending` / `match` | 2/2 | 1/2 | "
        "value `I` · evidence `cancel:1006:queued` |"
    ) in summary.splitlines()
    assert (
        "Numeric scores pass at threshold 1; categorical verdicts use the source tool's pass mark."
        in summary
    )
    recorded = json.loads((output / "diff.json").read_text())
    assert recorded["gate_passed"] is False
    assert recorded["blocking_changes"] == 3


def test_passing_gate_has_no_explanation(tmp_path):
    path = EXAMPLES / "inspect/current.json"
    code, output = _run(tmp_path, path, path)
    assert code == 0
    assert "Why the gate failed" not in (output / "index.html").read_text(encoding="utf-8")


def test_html_escapes_clips_and_falls_back(tmp_path):
    _, output = _inspect(tmp_path)
    result = json.loads((output / "diff.json").read_text())
    template = next(r for r in result["changes"] if r["kind"] == "regressed")

    def synthetic(kind, case_id, check, **detail):
        return {
            "kind": kind,
            "case_id": case_id,
            "check": check,
            "baseline": copy.deepcopy(template["baseline"]),
            "current": copy.deepcopy(template["current"]),
            **detail,
        }

    long_value = "v" * 130
    result["changes"] += [
        synthetic(
            "regressed",
            "synthetic-escape",
            "<script>x</script>",
            current_detail=[{"passed": False, "value": long_value, "evidence": "refund & ok"}],
        ),
        synthetic(
            "removed",
            "synthetic-removed",
            "match",
            baseline_detail=[{"passed": True, "value": "C", "evidence": "kept:1"}],
        ),
        synthetic("unassessed", "synthetic-empty", "match"),
    ]
    destination = tmp_path / "synthetic.html"
    render_html(result, destination)
    html = destination.read_text(encoding="utf-8")
    section = _section(html)
    assert "&lt;script&gt;x" in section
    assert "refund &amp; ok" in section
    assert "<script>x</script>" not in html
    assert "value <code>" + "v" * 120 + "…</code>" in section
    assert "v" * 121 not in html
    assert (
        "not recorded in the current run; baseline: value <code>C</code> · "
        "evidence <code>kept:1</code>"
    ) in section
    empty = next(r for r in _rows(section) if "<code>synthetic-empty</code>" in r)
    assert "no attempt detail recorded" in empty
    assert len(_rows(section)) == 6


def test_explanation_table_is_an_accessible_region(tmp_path):
    _, output = _inspect(tmp_path)
    html = (output / "index.html").read_text(encoding="utf-8")
    assert html.count(REGION) == 1
    assert html.count('aria-label="Why the gate failed"') == 1
    table = html[html.index(REGION) :]
    table = table[: table.index("</table>")]
    assert table.count('<th scope="col">') == 5 and "<th>" not in table
    for header in ("Finding", "Case / check", "Baseline", "Current", "Failing attempt"):
        assert f'<th scope="col">{header}</th>' in table
    rows = _rows(table)
    assert rows
    for row in rows:
        assert row.startswith('<td><span class="tone bad">✗ ')

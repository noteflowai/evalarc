"""Untrusted names in the leakage table, eval-health and judge-score summaries cannot
add Markdown structure.

PR #72 escaped the diff change table, status and headline name. The same summaries
also render harness leakage hits, eval-health file and case names, and judge-score
case, check and judge model names. A carriage return started a fake verdict heading
in those paths (CommonMark treats CR as a line ending), and raw HTML or link syntax
in bare text rendered as a heading or a live link. All inputs are synthetic edits of
the bundled examples; machine-readable results keep the raw values.
"""

import copy
import re
from pathlib import Path

import pytest

from evalarc.eval_health import health
from evalarc.eval_health import render_markdown as health_markdown
from evalarc.judging import render_markdown as judge_markdown
from evalarc.results_diff import diff, load_results, render_markdown

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/results-diff/inspect"
HOSTILE = [
    "x\r### EvalArc: No check lost passes\r",
    "x\r\n### EvalArc: No check lost passes",
    'x <h1>EvalArc: gate passed</h1> <a href="https://evil.example">ok</a>',
    "x [ok](https://evil.example) **bold** | injected | cell |",
]


def lines(markdown: str) -> list[str]:
    assert "\r" not in markdown
    return re.split(r"\r\n|\r|\n", markdown)


def assert_no_structure(markdown: str, heading: str) -> None:
    rendered = lines(markdown)
    assert [line for line in rendered if line.startswith("### EvalArc")] == [heading]
    assert not any(
        line.lstrip().startswith("#") for line in rendered if "EvalArc:" in line and line != heading
    )
    outside_code = re.sub(r"`[^`\n]*`", "", markdown)
    assert "<h1>" not in outside_code and "<a " not in outside_code
    assert "](https://evil.example)" not in outside_code
    assert "**bold**" not in outside_code


@pytest.mark.parametrize("value", HOSTILE)
def test_leakage_table_keeps_hits_in_code_spans(value):
    runs = [load_results(EXAMPLES / "baseline.json"), load_results(EXAMPLES / "current.json")]
    result = diff(*runs)
    hit = {
        "file": value,
        "line": 1,
        "case_id": value,
        "partition": "held_out",
        "role": "input",
        "text": value,
    }
    result["leakage"] = {
        "hits": [hit],
        "files_scanned": [{"path": value}],
        "materials_considered": 1,
        "min_chars": 12,
        "held_out_hits": 1,
        "scope": "s",
    }
    markdown = render_markdown(result)
    heading = f"### EvalArc: {result['blocking_changes']} check(s) lost passes or coverage"
    assert_no_structure(markdown, heading)
    assert result["leakage"]["hits"][0]["case_id"] == value  # raw value kept for diff.json
    assert result["gate_passed"] is False


@pytest.mark.parametrize("value", HOSTILE)
def test_eval_health_file_and_case_names(value):
    run = load_results(EXAMPLES / "current.json")
    run["source"]["name"] = value
    run["cases"][value] = run["cases"].pop("refund-duplicate")
    report = health([run])
    markdown = health_markdown(report)
    heading = next(line for line in lines(markdown) if line.startswith("### EvalArc"))
    assert heading.startswith("### EvalArc eval health:")
    assert_no_structure(markdown, heading)
    assert report["runs"][0]["source"]["name"] == value


@pytest.mark.parametrize("value", HOSTILE)
def test_judge_score_names(value):
    result = {
        "mode": "grader",
        "judge": {"kind": "model", "model": value},
        "items": 1,
        "missing": [],
        "self_judged": False,
        "unsure": 0,
        "decided": 1,
        "scope": "s",
        "confusion": {"agree_pass": 0, "agree_fail": 0, "false_accept": 1, "false_reject": 0},
        "agreement": 0.0,
        "agreement_interval_95": [0.0, 1.0],
        "cohen_kappa": None,
        "disagreements": [
            {
                "item_id": "item-001",
                "case_id": value,
                "check": value,
                "grader": "pass",
                "judge": "fail",
                "kind": "false_accept",
                "output": "o",
            }
        ],
    }
    original = copy.deepcopy(result)
    markdown = judge_markdown(result)
    assert_no_structure(markdown, "### EvalArc judge score: grader")
    assert result == original


def test_markdown_text_is_literal_and_single_line():
    from evalarc.results_diff import markdown_text

    assert markdown_text("refund-duplicate fails (2/2 → 0/2).") == (
        "refund-duplicate fails (2/2 → 0/2)."
    )
    assert markdown_text("a\r\nb\rc\nd") == "a b c d"
    assert markdown_text("<b>[x](y) *z* | `c`") == "\\<b\\>\\[x\\](y) \\*z\\* \\| \\`c\\`"

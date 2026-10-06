"""Untrusted run status, headline name and table identifiers stay inside one code span.

All inputs below are synthetic edits of the bundled promptfoo example results.
"""

import re
from pathlib import Path

import pytest

from evalarc.results_diff import diff, load_results, render_markdown

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/results-diff"

ADVERSARIAL = "error`\n### EvalArc: No check lost passes |x\rtail"
ESCAPED = "error' ### EvalArc: No check lost passes \\|x tail"


def self_comparison():
    path = EXAMPLES / "promptfoo/current.json"
    return diff(load_results(path), load_results(path))


def rendered_lines(result, expected_heading):
    md = render_markdown(result)
    assert "\r" not in md
    lines = re.split(r"\r\n|\r|\n", md)
    assert lines[0] == expected_heading
    assert sum(line.startswith("### EvalArc") for line in lines) == 1
    return lines


def only_line(lines, prefix):
    matching = [line for line in lines if line.startswith(prefix)]
    assert len(matching) == 1, matching
    assert matching[0].count("`") == 2
    return matching[0]


@pytest.mark.parametrize("status,shown", [("error", "error"), (ADVERSARIAL, ESCAPED)])
def test_current_status_stays_in_one_code_span(status, shown):
    result = self_comparison()
    result["current_incomplete"] = True
    result["gate_passed"] = False
    result["current"]["identity"]["status"] = status
    lines = rendered_lines(result, "### EvalArc: the current run is incomplete")
    line = only_line(lines, "The current run did not finish")
    assert line == f"The current run did not finish (status `{shown}`); the gate fails."
    assert result["current"]["identity"]["status"] == status
    assert result["gate_passed"] is False and result["blocking_changes"] == 0


@pytest.mark.parametrize("passed", [True, False])
@pytest.mark.parametrize(
    "name,shown", [("match accuracy", "match accuracy"), (ADVERSARIAL, ESCAPED)]
)
def test_headline_name_stays_in_one_code_span(passed, name, shown):
    result = self_comparison()
    result["baseline"]["headline"] = {"name": name, "value": 0.5}
    if passed:
        heading = "### EvalArc: No check lost passes"
    else:
        result["gate_passed"] = False
        result["current_incomplete"] = True
        result["current"]["identity"]["status"] = "error"
        heading = "### EvalArc: the current run is incomplete"
    lines = rendered_lines(result, heading)
    line = only_line(lines, "Headline metric: ")
    assert line == f"Headline metric: `{shown}` from the source tool."
    assert result["baseline"]["headline"]["name"] == name
    assert result["gate_passed"] is passed


def test_baseline_status_carriage_return_becomes_a_space():
    result = self_comparison()
    result["baseline_incomplete"] = True
    result["gate_passed"] = False
    result["baseline"]["identity"]["status"] = "error\rpartial"
    lines = rendered_lines(result, "### EvalArc: the baseline run is incomplete")
    line = only_line(lines, "The baseline run did not finish")
    assert line.startswith(
        "The baseline run did not finish (status `error partial`); the gate fails because"
    )
    assert result["baseline"]["identity"]["status"] == "error\rpartial"


def test_change_table_identifiers_stay_on_one_row():
    folder = EXAMPLES / "promptfoo"
    result = diff(load_results(folder / "baseline.json"), load_results(folder / "current.json"))
    assert result["changes"]
    heading = f"### EvalArc: {result['blocking_changes']} check(s) lost passes or coverage"
    result["changes"][0]["case_id"] = "a\rb"
    lines = rendered_lines(result, heading)
    rows = [line for line in lines if "| `a b` |" in line]
    assert len(rows) == 1 and rows[0].startswith("| ")
    assert result["changes"][0]["case_id"] == "a\rb"
    result["changes"][0]["case_id"] = "a | b `c`"
    assert "`a \\| b 'c'`" in render_markdown(result)
    assert result["gate_passed"] is False

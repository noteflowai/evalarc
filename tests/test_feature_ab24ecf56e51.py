"""Inspect runs scored at different numeric pass thresholds are not comparable.

Every log in this file is SYNTHETIC: it is built from the recorded example
examples/results-diff/inspect/baseline.json by replacing each sample's scores.
These fixtures prove the comparability rule only, not behavior on real exports.
"""

import json
from pathlib import Path

import pytest

from evalarc.results_diff import diff, load_results

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/results-diff"


def synthetic_log(tmp_path, name, value_for, task=None):
    """Write a synthetic Inspect log whose score values come from value_for(sample_id)."""
    document = json.loads((EXAMPLES / "inspect/baseline.json").read_text())
    for sample in document["samples"]:
        sample["scores"] = {"rubric": {"value": value_for(sample["id"])}}
    if task is not None:
        document["eval"] = {**document["eval"], "task": task}
    path = tmp_path / name
    path.write_text(json.dumps(document))
    return path


def numeric_pair(tmp_path):
    """Synthetic numeric logs: every score 0.7, except refund-small 0.9 in the current run."""
    before = synthetic_log(tmp_path, "baseline.json", lambda _: 0.7)
    after = synthetic_log(
        tmp_path, "current.json", lambda case: 0.9 if case == "refund-small" else 0.7
    )
    return before, after


def kinds(result):
    return sorted((row["kind"], row["case_id"], row["check"]) for row in result["changes"])


def test_mismatched_numeric_thresholds_are_not_comparable(tmp_path):
    before, after = numeric_pair(tmp_path)
    # At 0.8 every 0.7 fails; at 0.5 it passes. Comparing them would report gains
    # that come only from the pass definition, so diff() must refuse.
    with pytest.raises(ValueError) as error:
        diff(load_results(before, threshold=0.8), load_results(after, threshold=0.5))
    message = str(error.value)
    assert "not comparable" in message
    assert "threshold" in message
    assert "0.8 (baseline)" in message and "0.5 (current)" in message
    assert "same threshold" in message


@pytest.mark.parametrize("left,right", [(0.8, 0.8), (1, 1.0), (0.5, 0.50)])
def test_equal_thresholds_compare_as_before(tmp_path, left, right):
    before, after = numeric_pair(tmp_path)
    result = diff(load_results(before, threshold=left), load_results(after, threshold=right))
    reference = diff(load_results(before, threshold=right), load_results(after, threshold=right))
    for key in ("counts", "gate_passed", "changes", "numeric_pass_threshold"):
        assert result[key] == reference[key]
    assert result["numeric_pass_threshold"] == right
    if right == 0.8:
        assert kinds(result) == [("improved", "refund-small", "rubric")]


@pytest.mark.parametrize("value", ["C", True])
def test_non_numeric_scores_ignore_the_threshold(tmp_path, value):
    before = synthetic_log(tmp_path, "baseline.json", lambda _: value)
    after = synthetic_log(tmp_path, "current.json", lambda _: value)
    result = diff(load_results(before, threshold=0.8), load_results(after, threshold=0.5))
    assert result["gate_passed"] and not result["changes"]
    assert result["numeric_pass_threshold"] == 0.5


def test_letter_grades_that_change_still_compare(tmp_path):
    before = synthetic_log(tmp_path, "baseline.json", lambda _: "C")
    after = synthetic_log(
        tmp_path, "current.json", lambda case: "I" if case == "refund-small" else "C"
    )
    result = diff(load_results(before, threshold=0.8), load_results(after, threshold=0.5))
    assert kinds(result) == [("regressed", "refund-small", "rubric")]


def test_baseline_dict_without_threshold_skips_the_rule(tmp_path):
    before, after = numeric_pair(tmp_path)
    baseline = load_results(before, threshold=0.8)
    del baseline["threshold"]
    result = diff(baseline, load_results(after, threshold=0.5))
    assert result["numeric_pass_threshold"] == 0.5
    assert "counts" in result and "gate_passed" in result


def test_format_mismatch_is_still_reported_first(tmp_path):
    before, _ = numeric_pair(tmp_path)
    with pytest.raises(ValueError, match="different formats"):
        diff(
            load_results(before, threshold=0.8),
            load_results(EXAMPLES / "promptfoo/current.json", threshold=0.5),
        )


def test_task_mismatch_is_still_reported_before_the_threshold(tmp_path):
    before, _ = numeric_pair(tmp_path)
    other = synthetic_log(tmp_path, "other.json", lambda _: 0.7, task="other")
    with pytest.raises(ValueError) as error:
        diff(load_results(before, threshold=0.8), load_results(other, threshold=0.5))
    assert str(error.value).startswith("inputs are not comparable: task ")
    assert "'other'" in str(error.value)

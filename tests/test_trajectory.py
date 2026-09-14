import copy
import math

import pytest

from graderail.trajectory import summarize


def checkpoint(time, score, resolved=False):
    return {
        "elapsed_seconds": time,
        "evaluation": {
            "score": score,
            "resolved": resolved,
            "task": {"id": "durable-kv", "version": "0.1.0"},
            "grader_sha256": "same-grader",
            "cases_sha256": "same-cases",
            "runtime": {"backend": "local"},
        },
    }


def test_actual_regression_reduces_area():
    points = [checkpoint(2, 0.8), checkpoint(5, 0.2), checkpoint(8, 1, True)]
    result = summarize(points, 10)
    assert result["normalized_score_area"] == pytest.approx((3 * 0.8 + 3 * 0.2 + 2) / 10)
    assert result["regressions"] == [{"elapsed_seconds": 5, "from": 0.8, "to": 0.2}]
    assert result["first_resolved_seconds"] == 8


def test_no_checkpoint_means_no_observed_progress():
    result = summarize([], 10)
    assert result["normalized_score_area"] == 0
    assert result["first_resolved_seconds"] is None


@pytest.mark.parametrize("times", [[-1], [11], [2, 2], [4, 3], [math.nan]])
def test_invalid_times_rejected(times):
    with pytest.raises(ValueError):
        summarize([checkpoint(t, 0.5) for t in times], 10)


def test_incomparable_cases_rejected():
    first = checkpoint(1, 0.5)
    second = copy.deepcopy(first)
    second["elapsed_seconds"] = 2
    second["evaluation"]["cases_sha256"] = "different-cases"
    with pytest.raises(ValueError, match="same task"):
        summarize([first, second], 10)

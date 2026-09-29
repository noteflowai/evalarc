"""Checks with fewer assessed attempts than the baseline must fail the diff gate.

The small Inspect logs written here are synthetic fixtures.
"""

import json
from pathlib import Path

import pytest

from evalarc.cli import main
from evalarc.results_diff import diff, load_results

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/results-diff"
BASELINE = EXAMPLES / "inspect/baseline.json"


def write(path, document):
    path.write_text(json.dumps(document))
    return path


def trimmed_baseline(tmp_path):
    """The recorded baseline with the second epoch of cancel-pending lost."""
    document = json.loads(BASELINE.read_text())
    samples = document["samples"]
    kept = [s for s in samples if not (s["id"] == "cancel-pending" and s["epoch"] == 2)]
    assert len(kept) == len(samples) - 1
    assert document["status"] == "success"
    document["samples"] = kept
    return write(tmp_path / "trimmed.json", document)


def inspect_log(path, values):
    """A synthetic Inspect JSON log: one case, one match scorer, one sample per epoch."""
    samples = [
        {"id": "case", "epoch": epoch, "scores": {"match": {"value": value}}}
        for epoch, value in enumerate(values, start=1)
    ]
    document = {
        "version": 2,
        "status": "success",
        "eval": {"task": "fixture", "model": "none", "config": {"epochs": len(values)}},
        "results": {"scores": []},
        "samples": samples,
    }
    return write(path, document)


def compare_values(tmp_path, before, after):
    return diff(
        load_results(inspect_log(tmp_path / "baseline.json", before)),
        load_results(inspect_log(tmp_path / "current.json", after)),
    )


def find(result, case_id, check):
    return next(
        row for row in result["changes"] if row["case_id"] == case_id and row["check"] == check
    )


def test_lost_epoch_fails_the_gate_as_less_covered(tmp_path, capsys):
    trimmed = trimmed_baseline(tmp_path)
    assert main(["diff", str(BASELINE), str(trimmed)]) == 1
    assert "  less_covered: cancel-pending / match" in capsys.readouterr().out
    result = diff(load_results(BASELINE), load_results(trimmed))
    row = find(result, "cancel-pending", "match")
    assert row["kind"] == "less_covered"
    assert row["baseline"] == {"passed": 2, "assessed": 2, "attempts": 2}
    assert row["current"] == {"passed": 1, "assessed": 1, "attempts": 1}
    assert result["counts"]["less_covered"] >= 1
    assert result["blocking_changes"] >= result["counts"]["less_covered"]
    assert not result["current_incomplete"]
    assert result["gate_passed"] is False


@pytest.mark.parametrize(
    "before,after,current",
    [
        (["C", "I"], ["C"], {"passed": 1, "assessed": 1, "attempts": 1}),
        (["C", "C"], ["C", None], {"passed": 1, "assessed": 1, "attempts": 2}),
    ],
    ids=["fewer-attempts-higher-rate", "unscored-attempt-same-rate"],
)
def test_smaller_sample_is_never_improved_or_unchanged(tmp_path, before, after, current):
    result = compare_values(tmp_path, before, after)
    assert [(row["kind"], row["current"]) for row in result["changes"]] == [
        ("less_covered", current)
    ]
    assert result["counts"]["improved"] == 0
    assert result["counts"]["unchanged"] == 0
    assert not result["gate_passed"]


@pytest.mark.parametrize(
    "before,after,kind",
    [
        (["C", "C"], ["I"], "regressed"),
        (["C", "C", "C"], ["C", "I"], "less_reliable"),
        (["C"], [None], "unassessed"),
        (["C", "I"], ["C", "C", "C"], "improved"),
        (["C"], ["C", "C"], None),
        (["C", "I"], ["C", "I", "C", "I"], None),
    ],
)
def test_existing_kinds_keep_precedence(tmp_path, before, after, kind):
    result = compare_values(tmp_path, before, after)
    assert [row["kind"] for row in result["changes"]] == ([kind] if kind else [])
    assert result["counts"].get("less_covered", 0) == 0
    assert result["gate_passed"] is (kind in (None, "improved"))


def test_identical_recorded_baseline_still_passes():
    result = diff(load_results(BASELINE), load_results(BASELINE))
    assert result["gate_passed"] and not result["changes"]
    assert result["counts"].get("less_covered", 0) == 0


def test_report_folder_shows_the_missing_evidence(tmp_path):
    output = tmp_path / "review"
    trimmed = trimmed_baseline(tmp_path)
    code = main(["diff", str(BASELINE), str(trimmed), "--output", str(output)])
    assert code == 1
    saved = json.loads((output / "diff.json").read_text())
    assert saved["schema_version"] == "evalarc.results-diff.v1"
    assert saved["counts"]["less_covered"] >= 1
    assert "less_covered" in {row["kind"] for row in saved["changes"]}
    summary = (output / "summary.md").read_text()
    assert "| less covered | `cancel-pending` | `match` | 2/2 | 1/1 |" in summary
    html = (output / "index.html").read_text()
    row = '<td class="failed">less covered</td><td><code>cancel-pending</code></td>'
    assert row + "<td>match</td>" in html


def test_equal_coverage_comparison_keeps_the_recorded_v1_counts():
    path = EXAMPLES / "inspect/current.json"
    result = diff(load_results(path), load_results(path))
    assert result["gate_passed"] and not result["changes"]
    assert "less_covered" not in result["counts"]


def test_equal_coverage_report_folder_renders_without_less_covered(tmp_path, capsys):
    path = str(EXAMPLES / "inspect/current.json")
    output = tmp_path / "review"
    assert main(["diff", path, path, "--output", str(output)]) == 0
    printed = capsys.readouterr().out
    assert "less_covered" not in printed
    saved = json.loads((output / "diff.json").read_text())
    assert saved["gate_passed"] and "less_covered" not in saved["counts"]
    summary = (output / "summary.md").read_text()
    assert summary.startswith("### EvalArc: No check lost passes")
    assert "less covered" not in summary
    html = (output / "index.html").read_text()
    assert "Every recorded check has the same pass count." in html
    assert "less covered" not in html


@pytest.mark.parametrize("name", ["ci-gate.md", "ci-gate.zh-CN.md"])
def test_gate_docs_list_less_covered(name):
    text = (EXAMPLES.parents[1] / "docs" / name).read_text(encoding="utf-8")
    assert "| `less_covered` |" in text

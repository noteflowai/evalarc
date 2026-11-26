"""Malformed Inspect results headline fields raise named errors (EA-02).

Every log here is a synthetic edit of the recorded examples/results-diff/inspect logs.
"""

import json
import zipfile
from pathlib import Path

import pytest

from evalarc.cli import main
from evalarc.results_diff import diff, load_results

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/results-diff"
ABSENT = object()
GOOD = {"name": "match", "metrics": {"accuracy": {"value": 0.5}}}


def inspect_log(path, results=ABSENT):
    document = json.loads((EXAMPLES / "inspect/current.json").read_text())
    if results is ABSENT:
        document.pop("results", None)
    else:
        document["results"] = results
    path.write_text(json.dumps(document))
    return path


def headline_of(tmp_path, results):
    run = load_results(inspect_log(tmp_path / "log.json", results))
    return diff(run, run)["current"]["headline"]


def error_for(tmp_path, results):
    with pytest.raises(ValueError) as caught:
        load_results(inspect_log(tmp_path / "log.json", results))
    return str(caught.value)


def test_results_that_is_not_an_object_is_named(tmp_path):
    message = error_for(tmp_path, ["x"])
    assert "Inspect log field results must be an object (got array)" in message
    assert "inspect log dump" in message


def test_scores_that_is_not_an_array_is_named(tmp_path):
    message = error_for(tmp_path, {"scores": {"match": {"accuracy": 1}}})
    assert "Inspect log field results.scores must be an array (got object)" in message
    assert "inspect log dump" in message


@pytest.mark.parametrize(
    "results,field,expected",
    [
        ({"scores": ["x"]}, "results.scores[0]", "must be an object (got string)"),
        (
            {"scores": [{"name": "a", "metrics": {}}, "x"]},
            "results.scores[1]",
            "must be an object (got string)",
        ),
        (
            {"headline": ["x"], "scores": [GOOD]},
            "results.headline",
            "must be an object (got array)",
        ),
        (
            {
                "headline": {"score": "a", "metric": ["x"]},
                "scores": [{"name": "a", "metrics": {"accuracy": {"value": 1}}}],
            },
            "results.headline.metric",
            "must be a string (got array)",
        ),
        (
            {
                "headline": {"score": "a", "metric": ["x"]},
                "scores": [{"name": "a", "metrics": None}],
            },
            "results.headline.metric",
            "must be a string (got array)",
        ),
        (
            {
                "headline": {"score": "a", "metric": {"k": 1}},
                "scores": [{"name": "a", "metrics": []}],
            },
            "results.headline.metric",
            "must be a string (got object)",
        ),
        (
            {"scores": [{"metrics": {"accuracy": {"value": 1}}}]},
            "results.scores[0].name",
            "must be present (got missing)",
        ),
        (
            {"scores": [{"name": "m", "metrics": {"accuracy": 1}}]},
            "results.scores[0].metrics['accuracy']",
            "must be an object (got number)",
        ),
    ],
)
def test_reachable_headline_crashes_name_the_field(tmp_path, results, field, expected):
    message = error_for(tmp_path, results)
    assert f"Inspect log field {field} {expected}" in message
    assert "Re-export the log from Inspect (inspect log dump)" in message


def test_metric_name_with_control_character_is_escaped(tmp_path):
    message = error_for(tmp_path, {"scores": [{"name": "m", "metrics": {"acc\x1b[31m": 1}}]})
    assert "results.scores[0].metrics" in message
    assert "\\x1b" in message
    assert "\x1b" not in message


@pytest.mark.parametrize(
    "results,expected",
    [
        ({"scores": [GOOD, "x"]}, {"name": "match accuracy", "value": 0.5}),
        ({"headline": None, "scores": [GOOD]}, {"name": "match accuracy", "value": 0.5}),
        ({"headline": "x", "scores": []}, None),
        (
            {
                "headline": {"score": "b", "metric": "acc"},
                "scores": [
                    {"name": "a", "metrics": ["z"]},
                    {"name": "b", "metrics": {"acc": {"value": 0.25}}},
                ],
            },
            {"name": "b acc", "value": 0.25},
        ),
        (None, None),
        (ABSENT, None),
        ({}, None),
        ([], None),
        ({"scores": None}, None),
        ({"scores": []}, None),
        ({"headline": {"score": "match", "metric": "accuracy"}}, None),
        ({"scores": [{"name": "a", "metrics": None}, {"name": "b", "metrics": {}}]}, None),
    ],
)
def test_logs_that_load_today_keep_their_headline(tmp_path, results, expected):
    assert headline_of(tmp_path, results) == expected


def test_example_logs_keep_their_headlines_and_diff():
    result = diff(
        load_results(EXAMPLES / "inspect/baseline.json"),
        load_results(EXAMPLES / "inspect/current.json"),
    )
    assert result["baseline"]["headline"] == {"name": "match accuracy", "value": 0.625}
    assert result["current"]["headline"] == {"name": "match accuracy", "value": 0.8125}
    assert result["blocking_changes"] == 3
    assert result["counts"]["improved"] == 6


def test_eval_archive_header_reports_the_same_field(tmp_path):
    document = json.loads((EXAMPLES / "inspect/current.json").read_text())
    samples = document.pop("samples")
    document["results"] = {"scores": {"match": {}}}
    archive = tmp_path / "broken.eval"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        output.writestr("header.json", json.dumps(document))
        for sample in samples:
            output.writestr(
                f"samples/{sample['id']}_epoch_{sample['epoch']}.json", json.dumps(sample)
            )
    with pytest.raises(ValueError) as caught:
        load_results(archive)
    assert "Inspect log field results.scores must be an array (got object)" in str(caught.value)


def test_cli_exits_2_without_writing_outputs(tmp_path, capsys):
    broken = inspect_log(tmp_path / "broken-current.json", {"scores": {"match": {}}})
    summary = tmp_path / "step-summary.md"
    summary.write_text("existing\n")
    output = tmp_path / "review"
    code = main(
        [
            "diff",
            str(EXAMPLES / "inspect/baseline.json"),
            str(broken),
            "--output",
            str(output),
            "--markdown",
            str(summary),
        ]
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "results.scores must be an array (got object)" in err
    assert "Traceback" not in err
    assert not output.exists()
    assert summary.read_text() == "existing\n"

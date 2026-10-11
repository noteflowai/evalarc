"""Duplicated promptfoo result rows are rejected instead of counted as attempts."""

import copy
import json
from pathlib import Path

import pytest

from evalarc.cli import main
from evalarc.results_diff import diff, load_results

PROMPTFOO = Path(__file__).resolve().parents[1] / "examples/results-diff/promptfoo"


def _document(name="current"):
    return json.loads((PROMPTFOO / f"{name}.json").read_text())


def _write(path, document):
    path.write_text(json.dumps(document))
    return path


def _with_duplicate(document, index=0):
    rows = document["results"]["results"]
    rows.append(copy.deepcopy(rows[index]))
    return document


@pytest.mark.parametrize("explicit", [False, True])
def test_duplicated_row_is_rejected_with_its_identity(tmp_path, explicit):
    document = _document()
    row = copy.deepcopy(document["results"]["results"][0])
    path = _write(tmp_path / "duplicated.json", _with_duplicate(document))
    with pytest.raises(ValueError) as caught:
        if explicit:
            load_results(path, "promptfoo")
        else:
            load_results(path)
    message = str(caught.value)
    assert f"duplicate result testIdx {row['testIdx']} " in message
    assert f"promptIdx {row.get('promptIdx')!r}" in message
    assert "provider 'echo'" in message
    assert repr(row["testCase"]["description"]) in message
    assert "extra attempt" in message
    assert "promptfoo eval --output" in message


@pytest.mark.parametrize("side", ["baseline", "current"])
def test_cli_exits_2_on_a_duplicate_in_either_file(tmp_path, capsys, side):
    duplicated = _write(tmp_path / f"{side}.json", _with_duplicate(_document(side)))
    paths = {
        "baseline": PROMPTFOO / "baseline.json",
        "current": PROMPTFOO / "current.json",
        side: duplicated,
    }
    output = tmp_path / "review"
    code = main(["diff", str(paths["baseline"]), str(paths["current"]), "--output", str(output)])
    assert code == 2
    captured = capsys.readouterr()
    assert "promptfoo output has duplicate result testIdx" in captured.err
    assert "Checks that lost passes" not in captured.out
    assert not output.exists()


def test_unmodified_example_pair_still_reports_the_swapped_failure(tmp_path, capsys):
    output = tmp_path / "review"
    code = main(
        [
            "diff",
            str(PROMPTFOO / "baseline.json"),
            str(PROMPTFOO / "current.json"),
            "--output",
            str(output),
        ]
    )
    assert code == 1
    printed = capsys.readouterr().out
    assert "regressed: duplicate refund is rejected / icontains: already refunded" in printed
    result = json.loads((output / "diff.json").read_text())
    improved = sorted(
        (row["case_id"], row["check"]) for row in result["changes"] if row["kind"] == "improved"
    )
    assert improved == [
        ("large refund is escalated", "icontains: escalate"),
        ("large refund is escalated", "not-icontains: refund approved"),
    ]


def test_repeats_with_new_test_indexes_still_count_as_attempts(tmp_path):
    document = _document()
    rows = document["results"]["results"]
    repeated = copy.deepcopy(document)
    extra = copy.deepcopy(rows)
    for index, row in enumerate(extra):
        row["testIdx"] = len(rows) + index
        if row["vars"]["kind"] == "large":
            row["gradingResult"]["componentResults"][0]["pass"] = False
    repeated["results"]["results"] = rows + extra
    result = diff(
        load_results(_write(tmp_path / "single.json", document)),
        load_results(_write(tmp_path / "repeated.json", repeated)),
    )
    assert [(row["kind"], row["check"]) for row in result["changes"]] == [
        ("less_reliable", "icontains: escalate")
    ]
    assert result["changes"][0]["current"] == {"passed": 1, "assessed": 2, "attempts": 2}


@pytest.mark.parametrize("value", [None, "1", True])
def test_rows_without_an_integer_test_index_are_not_checked(tmp_path, value):
    document = _document()
    for row in document["results"]["results"]:
        if value is None:
            row.pop("testIdx", None)
        else:
            row["testIdx"] = value
    first = document["results"]["results"][0]
    label = first["testCase"]["description"]
    loaded = load_results(_write(tmp_path / "unchecked.json", _with_duplicate(document)))
    assert any(len(attempts) == 2 for attempts in loaded["cases"][label].values())


def test_untrusted_label_and_provider_are_escaped_and_truncated(tmp_path):
    document = _document()
    first = document["results"]["results"][0]
    first["testCase"]["description"] = "evil\x1b[31m\nverdict: pass " + "x" * 500
    first["provider"] = "echo\x1b]0;title\x07"
    path = _write(tmp_path / "crafted.json", _with_duplicate(document))
    with pytest.raises(ValueError) as caught:
        load_results(path)
    message = str(caught.value)
    for raw in ("\x1b", "\x07", "\n"):
        assert raw not in message
    assert "\\x1b" in message and "\\x07" in message
    assert "..." in message
    assert "x" * 200 not in message
    assert len(message) < 700


@pytest.mark.parametrize("prompt_idx", [[0], {}])
@pytest.mark.parametrize("duplicated", [False, True])
def test_list_or_object_prompt_idx_is_malformed_input_not_a_crash(
    tmp_path, capsys, prompt_idx, duplicated
):
    document = _document()
    document["results"]["results"][0]["promptIdx"] = prompt_idx
    if duplicated:
        _with_duplicate(document)
    path = _write(tmp_path / "crafted.json", document)
    with pytest.raises(ValueError) as caught:
        load_results(path)
    assert "invalid promptIdx" in str(caught.value)
    assert "promptfoo eval --output" in str(caught.value)
    code = main(["diff", str(PROMPTFOO / "baseline.json"), str(path)])
    assert code == 2
    captured = capsys.readouterr()
    assert "invalid promptIdx" in captured.err
    assert "Checks that lost passes" not in captured.out

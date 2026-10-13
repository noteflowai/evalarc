"""Inspect samples without a usable id are rejected instead of becoming case None.

All fixtures are synthetic edits of the shipped example logs.
"""

import json
import zipfile
from pathlib import Path

import pytest

from evalarc.cli import main
from evalarc.results_diff import diff, load_results

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/results-diff/inspect"


def _log(name="current"):
    return json.loads((EXAMPLES / f"{name}.json").read_text())


def _write(path, document):
    path.write_text(json.dumps(document))
    return path


def test_missing_id_names_position_and_cli_exits_2(tmp_path, capsys):
    document = _log()
    del document["samples"][2]["id"]
    path = _write(tmp_path / "current.json", document)
    with pytest.raises(ValueError) as caught:
        load_results(path)
    message = str(caught.value)
    assert "sample at position 2 has an invalid id missing (missing)" in message
    assert "inspect log dump" in message
    assert main(["diff", str(EXAMPLES / "baseline.json"), str(path)]) == 2
    err = capsys.readouterr().err
    assert "evalarc: Inspect log sample at position 2 has an invalid id missing" in err
    assert "evalarc: 'id'" not in err


@pytest.mark.parametrize(
    "bad_id,shown",
    [
        (None, "None (null)"),
        (True, "True (boolean)"),
        (1.5, "1.5 (number)"),
        (["a"], "['a'] (array)"),
        ({"k": 1}, "{'k': 1} (object)"),
    ],
)
def test_unusable_id_types_are_rejected_on_either_side(tmp_path, capsys, bad_id, shown):
    document = _log()
    document["samples"][1]["id"] = bad_id
    path = _write(tmp_path / "bad.json", document)
    with pytest.raises(ValueError) as caught:
        load_results(path)
    assert f"sample at position 1 has an invalid id {shown}" in str(caught.value)
    # The baseline side is validated too, and no report is produced.
    assert main(["diff", str(path), str(EXAMPLES / "current.json"), "--json"]) == 2
    captured = capsys.readouterr()
    assert "invalid id" in captured.err
    assert captured.out == ""


def test_two_null_ids_report_the_id_not_a_duplicate(tmp_path):
    document = _log()
    for sample in document["samples"][:2]:
        sample["id"] = None
        sample["epoch"] = 1
    with pytest.raises(ValueError) as caught:
        load_results(_write(tmp_path / "nulls.json", document))
    message = str(caught.value)
    assert "sample at position 0 has an invalid id None (null)" in message
    assert "duplicate sample" not in message


@pytest.mark.parametrize(
    "sample,kind", [([1, 2], "array"), ("x", "string"), (None, "null"), (3, "number")]
)
def test_non_object_sample_in_json_log(tmp_path, sample, kind):
    document = _log()
    document["samples"].insert(1, sample)
    with pytest.raises(ValueError) as caught:
        load_results(_write(tmp_path / "bad.json", document))
    assert f"sample at position 1 is not an object (got {kind})" in str(caught.value)


def test_non_object_member_in_eval_archive(tmp_path):
    document = _log()
    samples = document.pop("samples")
    archive = tmp_path / "current.eval"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        output.writestr("header.json", json.dumps(document))
        for sample in samples:
            output.writestr(
                f"samples/{sample['id']}_epoch_{sample['epoch']}.json", json.dumps(sample)
            )
        # Sorts after every shipped sample id, so its position is len(samples).
        output.writestr("samples/zzz_epoch_1.json", json.dumps([1, 2]))
    with pytest.raises(ValueError) as caught:
        load_results(archive)
    assert f"sample at position {len(samples)} is not an object (got array)" in str(caught.value)


def test_cli_writes_no_report_and_keeps_markdown(tmp_path, capsys):
    document = _log()
    document["samples"][0]["id"] = None
    bad = _write(tmp_path / "current.json", document)
    summary = tmp_path / "step-summary.md"
    summary.write_text("existing\n")
    output = tmp_path / "review"
    code = main(
        [
            "diff",
            str(EXAMPLES / "baseline.json"),
            str(bad),
            "--output",
            str(output),
            "--markdown",
            str(summary),
        ]
    )
    assert code == 2
    assert "invalid id None (null)" in capsys.readouterr().err
    assert not (output / "diff.json").exists()
    assert summary.read_text() == "existing\n"


def test_valid_ids_still_load_and_example_result_is_unchanged(tmp_path):
    result = diff(load_results(EXAMPLES / "baseline.json"), load_results(EXAMPLES / "current.json"))
    assert result["blocking_changes"] == 3
    assert result["counts"]["improved"] == 6
    assert result["counts"]["unchanged"] == 7
    assert result["gate_passed"] is False

    names = sorted({s["id"] for s in _log("baseline")["samples"]})
    numbers = {name: index for index, name in enumerate(names)}
    paths = []
    for name in ("baseline", "current"):
        document = _log(name)
        for sample in document["samples"]:
            sample["id"] = numbers.get(sample["id"], sample["id"])
        paths.append(_write(tmp_path / f"{name}.json", document))
    numeric = diff(load_results(paths[0]), load_results(paths[1]))
    assert numeric["blocking_changes"] == 3
    assert numeric["counts"] == result["counts"]
    assert {row["case_id"] for row in numeric["changes"]} <= {str(n) for n in numbers.values()}

    document = _log("baseline")
    for sample in document["samples"]:
        if sample["id"] == "refund-small":
            sample["id"] = ""
    loaded = load_results(_write(tmp_path / "empty-id.json", document))
    assert "" in loaded["cases"]
    assert "None" not in loaded["cases"]

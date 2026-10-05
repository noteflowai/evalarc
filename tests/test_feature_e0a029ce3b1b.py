"""Duplicate Inspect samples (same id and epoch) are rejected, not counted as attempts.

All logs here are synthetic copies of the recorded examples, written by the tests.
"""

import copy
import json
import zipfile
from pathlib import Path

import pytest

from evalarc.cli import main
from evalarc.results_diff import diff, load_results

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/results-diff"


def _load(name):
    return json.loads((EXAMPLES / f"inspect/{name}.json").read_text())


def _write(path, document):
    path.write_text(json.dumps(document))
    return path


def _scored(template, sample_id, epoch):
    sample = copy.deepcopy(template)
    sample["id"] = sample_id
    if epoch is None:
        sample.pop("epoch", None)
    else:
        sample["epoch"] = epoch
    sample.pop("error", None)
    sample["scores"] = {"match": {"value": "C"}}
    return sample


@pytest.mark.parametrize("side", ["baseline", "current"])
def test_duplicated_sample_exits_2_and_names_it(tmp_path, capsys, side):
    document = _load(side)
    duplicate = copy.deepcopy(document["samples"][0])
    document["samples"].append(duplicate)
    broken = _write(tmp_path / f"{side}-dup.json", document)
    paths = {
        "baseline": str(EXAMPLES / "inspect/baseline.json"),
        "current": str(EXAMPLES / "inspect/current.json"),
    }
    paths[side] = str(broken)
    output = tmp_path / "review"
    code = main(["diff", paths["baseline"], paths["current"], "--output", str(output)])
    assert code == 2
    err = capsys.readouterr().err
    assert "duplicate sample" in err
    assert repr(duplicate["id"]) in err
    assert f"epoch {duplicate['epoch']}" in err
    assert "inspect log dump" in err
    assert not (output / "diff.json").exists()


def test_integer_and_string_ids_collide(tmp_path, capsys):
    document = _load("baseline")
    template = document["samples"][0]
    document["samples"] = [_scored(template, 7, 1), _scored(template, "7", 1)]
    path = _write(tmp_path / "mixed.json", document)
    assert main(["diff", str(EXAMPLES / "inspect/baseline.json"), str(path)]) == 2
    err = capsys.readouterr().err
    assert "duplicate sample" in err and "epoch 1" in err


def test_eval_archive_with_duplicate_members_is_rejected(tmp_path):
    document = _load("current")
    samples = document.pop("samples")
    archive = tmp_path / "current.eval"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        output.writestr("header.json", json.dumps(document))
        output.writestr("samples/a.json", json.dumps(samples[0]))
        output.writestr("samples/b.json", json.dumps(samples[0]))
    with pytest.raises(ValueError, match="duplicate sample"):
        load_results(archive)


def test_control_characters_in_id_are_escaped(tmp_path):
    document = _load("baseline")
    template = document["samples"][0]
    name = "bad\nid" + "x" * 200
    document["samples"] = [_scored(template, name, 1), _scored(template, name, 1)]
    with pytest.raises(ValueError) as caught:
        load_results(_write(tmp_path / "ctrl.json", document))
    message = str(caught.value)
    assert "\n" not in message
    assert "x" * 100 not in message


def test_valid_logs_are_unchanged(tmp_path):
    result = diff(
        load_results(EXAMPLES / "inspect/baseline.json"),
        load_results(EXAMPLES / "inspect/current.json"),
    )
    assert result["blocking_changes"] == 3 and not result["gate_passed"]

    document = _load("baseline")
    template = document["samples"][0]
    document["samples"] = [_scored(template, "repeat", epoch) for epoch in (1, 2, 3)]
    loaded = load_results(_write(tmp_path / "epochs.json", document))
    assert len(loaded["cases"]["repeat"]["match"]) == 3

    document["samples"] = [_scored(template, "no-epoch", None) for _ in range(2)]
    loaded = load_results(_write(tmp_path / "no-epoch.json", document))
    assert len(loaded["cases"]["no-epoch"]["match"]) == 2

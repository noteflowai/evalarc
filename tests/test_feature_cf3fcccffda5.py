import json
import re
import zipfile
from pathlib import Path

import pytest

from evalarc.cli import main
from evalarc.results_diff import _shown_id, load_results

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/results-diff"


def _document():
    return json.loads((EXAMPLES / "inspect/current.json").read_text())


def _malformed(scores, error=None):
    """Synthetic edit of the bundled example log: one sample gets a bad scores value."""
    document = _document()
    sample = document["samples"][0]
    sample["scores"] = scores
    if error is not None:
        sample["error"] = error
    return document, _shown_id(sample["id"])


def _write(path, document):
    path.write_text(json.dumps(document))
    return path


def _assert_named(message, sample_id, kind):
    assert f"Inspect log sample {sample_id} at position " in message
    assert re.search(r"at position \d+", message)
    assert f"has scores of type {kind}" in message
    assert "inspect log dump" in message


@pytest.mark.parametrize(
    "scores,kind",
    [(["C"], "array"), ("C", "string"), (1, "number"), (1.5, "number"), (True, "boolean")],
)
def test_json_log_with_non_object_scores_names_the_sample(tmp_path, scores, kind):
    document, sample_id = _malformed(scores)
    path = _write(tmp_path / "current.json", document)
    with pytest.raises(ValueError) as caught:
        load_results(path)
    _assert_named(str(caught.value), sample_id, kind)


def test_eval_archive_with_non_object_scores_names_the_sample(tmp_path):
    document, sample_id = _malformed(["C"])
    samples = document.pop("samples")
    archive = tmp_path / "current.eval"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        output.writestr("header.json", json.dumps(document))
        for sample in samples:
            output.writestr(
                f"samples/{sample['id']}_epoch_{sample['epoch']}.json", json.dumps(sample)
            )
    with pytest.raises(ValueError) as caught:
        load_results(archive)
    _assert_named(str(caught.value), sample_id, "array")


@pytest.mark.parametrize(
    "scores,error,kind",
    [(["C"], None, "array"), ("C", {"message": "tool crashed"}, "string")],
)
def test_diff_exits_2_and_explains_non_object_scores(tmp_path, capsys, scores, error, kind):
    document, sample_id = _malformed(scores, error)
    current = _write(tmp_path / "current.json", document)
    output = tmp_path / "review"
    code = main(
        ["diff", str(EXAMPLES / "inspect/baseline.json"), str(current), "--output", str(output)]
    )
    assert code == 2
    _assert_named(capsys.readouterr().err, sample_id, kind)
    assert not output.exists()


def test_missing_null_and_empty_scores_load_as_before(tmp_path):
    loaded = []
    for index, variant in enumerate(("missing", None, {})):
        document = _document()
        sample = document["samples"][0]
        if variant == "missing":
            sample.pop("scores", None)
        else:
            sample["scores"] = variant
        loaded.append(load_results(_write(tmp_path / f"{index}.json", document))["cases"])
    assert loaded[0] == loaded[1] == loaded[2]


def test_valid_example_log_loads_unchanged(tmp_path):
    copy_path = _write(tmp_path / "current.json", _document())
    expected = load_results(EXAMPLES / "inspect/current.json")["cases"]
    assert load_results(copy_path)["cases"] == expected

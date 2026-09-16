"""The public review must retain every rule and refuse contradictory evidence."""

import copy
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import pytest

from scripts.strands_page import build_strands, render_rows, review_data, verified_rows

ROOT = Path(__file__).resolve().parents[1]
RECORDED = ROOT / "examples/strands-state-review/recorded"
ORIGINAL = ROOT / "examples/comparison"


def test_native_row_order_does_not_change_alignment():
    comparison, before, after = review_data(RECORDED, ORIGINAL)
    native = json.loads((RECORDED / "current-native.json").read_bytes())
    for field in ("cases", "scores", "test_passes", "reasons", "detailed_results"):
        native[field].reverse()
    source = json.loads((ORIGINAL / "current.json").read_bytes())
    reordered = verified_rows(native, source, comparison["source_sha256"]["current"])
    assert reordered == after
    assert before[("retry-after-commit@17", "ticket.notes")]["passed"]
    assert not reordered[("retry-after-commit@17", "ticket.notes")]["passed"]
    assert len(reordered) == 8


@pytest.mark.parametrize("fault", ["duplicate", "omitted", "state", "verdict", "score"])
def test_native_contradictions_cannot_be_published(fault):
    native = json.loads((RECORDED / "current-native.json").read_bytes())
    source = json.loads((ORIGINAL / "current.json").read_bytes())
    if fault == "duplicate":
        native["cases"][0] = copy.deepcopy(native["cases"][1])
    elif fault == "omitted":
        native["cases"].pop()
    elif fault == "state":
        native["cases"][3]["actual_environment_state"][0]["state"]["notes"].pop()
    elif fault == "verdict":
        native["test_passes"][3] = True
    else:
        native["scores"][3] = 1
    with pytest.raises(ValueError):
        verified_rows(
            native, source, hashlib.sha256((ORIGINAL / "current.json").read_bytes()).hexdigest()
        )


def test_comparison_cannot_hide_a_regression(tmp_path):
    shutil.copytree(RECORDED, tmp_path / "recorded")
    path = tmp_path / "recorded/comparison.json"
    comparison = json.loads(path.read_bytes())
    comparison["regressions"] = []
    comparison["regression_gate_passes"] = True
    path.write_text(json.dumps(comparison))
    with pytest.raises(ValueError, match="changes disagree"):
        review_data(path.parent, ORIGINAL)


def test_check_links_bind_both_reports_and_escape_state():
    _, before, after = review_data(RECORDED, ORIGINAL)
    rendered = render_rows(before, after, "original-native-pair")
    changed = render_rows(before, after, "changed-native-pair")
    import re

    assert set(re.findall('id="([^"]+)"', rendered)).isdisjoint(re.findall('id="([^"]+)"', changed))
    before[("retry-after-commit@17", "ticket.notes")]["actual"] = ["<script>alert(1)</script>"]
    assert "<script>" not in render_rows(before, after, "original-native-pair")


def test_offline_archive_is_complete_deterministic_and_preserves_inputs(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    for parent in (first, second):
        parent.mkdir()
        build_strands(ROOT, parent / "strands")
    assert (first / "strands-review.zip").read_bytes() == (
        second / "strands-review.zip"
    ).read_bytes()
    with zipfile.ZipFile(first / "strands-review.zip") as archive:
        archive.extractall(tmp_path / "download")
    received = tmp_path / "download/strands-review"
    manifest = json.loads((received / "manifest.json").read_bytes())
    assert set(manifest["files"]) == {p.name for p in received.iterdir()} - {"manifest.json"}
    for name, expected in manifest["files"].items():
        assert hashlib.sha256((received / name).read_bytes()).hexdigest() == expected
    for name in ("baseline", "current"):
        assert (received / f"{name}-native.json").read_bytes() == (
            RECORDED / f"{name}-native.json"
        ).read_bytes()
        assert (received / f"{name}-evalarc.json").read_bytes() == (
            ORIGINAL / f"{name}.json"
        ).read_bytes()
    page = (received / "index.html").read_text()
    assert page.count('class="check"') == 8
    assert "__ROWS__" not in page

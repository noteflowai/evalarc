"""Reported Harbor/program disagreement must follow the native recorded artifacts."""

import json
import shutil
from pathlib import Path

import pytest

from scripts.build_harbor_controls import checked_rows, verify_bundle

ROOT = Path(__file__).parents[1] / "examples/harbor-controls"


def test_native_controls_and_offline_archive_are_consistent():
    assert verify_bundle(ROOT)["controls"] == 3
    rows = checked_rows(ROOT)
    assert [row["upstream_rewards"]["reward"] for row in rows] == [1, 0.8, 1]
    assert [row["independent"]["score"] for row in rows] == [1, 0.8, 0.8]
    assert [row["acceptance"]["accepted"] for row in rows] == [True, False, False]


def test_false_acceptance_cannot_override_the_saved_program_evaluation(tmp_path):
    shutil.copytree(ROOT, tmp_path / "lab")
    path = tmp_path / "lab/summary.json"
    record = json.loads(path.read_text())
    record["runs"][2]["acceptance"]["accepted"] = True
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="independent headline"):
        checked_rows(tmp_path / "lab")


def test_replacement_program_cannot_be_presented_as_the_collected_program(tmp_path):
    shutil.copytree(ROOT, tmp_path / "lab")
    rows = json.loads((tmp_path / "lab/summary.json").read_text())["runs"]
    original = tmp_path / "lab" / rows[0]["trial_path"] / "artifacts/candidate/main.py"
    replaced = tmp_path / "lab" / rows[2]["trial_path"] / "artifacts/candidate/main.py"
    replaced.write_bytes(original.read_bytes())
    with pytest.raises(ValueError, match="different collected program"):
        checked_rows(tmp_path / "lab")

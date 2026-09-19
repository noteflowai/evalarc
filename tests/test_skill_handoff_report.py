from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

import pytest

from scripts import build_handoff_mcp as common
from scripts import build_skill_handoff as report

EVIDENCE = Path(__file__).resolve().parents[1] / "examples/skill-handoff"


@pytest.fixture
def copied(tmp_path):
    root = tmp_path / "evidence"
    shutil.copytree(EVIDENCE, root)
    return root


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")


def test_received_skill_handoff_verifies_offline(tmp_path):
    result = report.verify_bundle(EVIDENCE)
    assert result["trials"] == 6
    assert result["loaded"] == 6
    with zipfile.ZipFile(EVIDENCE / report.ARCHIVE) as archive:
        archive.extractall(tmp_path)
    assert report.verify_bundle(tmp_path)["loaded"] == 6


@pytest.mark.parametrize("changed", ["content", "route", "actor", "raw-error"])
def test_receipt_hash_alone_cannot_establish_correct_mcp_delivery(copied, changed):
    rows = common.checked_rows(copied, skill_handoff=True)
    trial_path = copied / rows[0]["path"] / "trial.json"
    trial = report.read(trial_path)
    preload_path = copied / trial["handoff"]["skill_delivery"]["path"]
    preload = report.read(preload_path)
    if changed == "content":
        preload["reply"]["view"]["content"] = "A different version of the instructions"
    elif changed == "route":
        preload["reply"]["receipt"]["route"] = "direct"
    elif changed == "actor":
        preload["actor"] = "model"
    else:
        preload["reply"]["receipt"]["raw"]["isError"] = True
    write(preload_path, preload)
    # Keep the local receipt hash consistent: the semantic checks must still reject it.
    trial["handoff"]["skill_delivery"]["sha256"] = report.digest(preload_path)
    write(trial_path, trial)
    with pytest.raises(ValueError, match="receipt differs|did not receive"):
        report.checked_skills(copied, rows)


def test_missing_attempt_is_not_a_complete_handoff_cohort(copied):
    summary = report.read(copied / "summary.json")
    summary["trials"].pop()
    write(copied / "summary.json", summary)
    with pytest.raises(ValueError, match="six scheduled attempts differ"):
        common.checked_rows(copied, skill_handoff=True)


def test_imported_package_must_match_the_frozen_source(copied):
    path = copied / "validation/runtime-package-after.json"
    observation = report.read(path)
    observation["files"][0]["sha256"] = "0" * 64
    write(path, observation)
    with pytest.raises(ValueError, match="editable package differs"):
        report.checked_validation(copied)


def test_later_runtime_observation_cannot_be_relabelled_as_pre_run(copied):
    path = copied / "validation/runtime-package-during.json"
    observation = report.read(path)
    observation["observed_at"] = "2026-09-14T00:00:00+00:00"
    write(path, observation)
    with pytest.raises(ValueError, match="inconsistent timing"):
        report.checked_validation(copied)

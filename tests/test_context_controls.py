"""The context experiment must preserve failures and the evidence behind its headlines."""

import json
import shutil
from pathlib import Path

import pytest

from scripts.build_context_collection import SCHEMA, summarize, verify
from scripts.build_context_controls import checked_rows, seal, verify_bundle

ROOT = Path(__file__).parents[1] / "examples/context-controls"


@pytest.fixture
def cohort(tmp_path):
    destination = tmp_path / "protocol"
    shutil.copytree(ROOT / "protocol", destination)
    return destination


def change(path, update):
    data = json.loads(path.read_text())
    update(data)
    path.write_text(json.dumps(data))


def first_trial(cohort):
    summary = json.loads((cohort / "summary.json").read_text())
    return cohort / summary["trials"][0]["path"]


def test_both_complete_cohorts_preserve_unresolved_attempts():
    assert verify(ROOT)["trials"] == 12
    summary = summarize(ROOT)
    assert summary["outcomes_are_pooled"] is False
    assert [row["resolved"] for row in summary["cohorts"]] == [0, 0]
    assert [row["response_timeouts"] for row in summary["cohorts"]] == [48, 0]
    rows = checked_rows(ROOT / "protocol")
    assert [row["evaluation"]["score"] for row in rows] == [0.875, 0, 0, 0.875, 0.875, 0]


def test_finish_cannot_be_promoted_to_task_resolution(cohort):
    def claim_success(data):
        data["trials"][0]["evaluation"]["resolved"] = True
        data["trials"][0]["evaluation"]["score"] = 1

    change(cohort / "summary.json", claim_success)
    with pytest.raises(ValueError, match="independently evaluated candidate"):
        checked_rows(cohort)


def test_collected_program_cannot_be_replaced_by_a_passing_program(cohort):
    program = first_trial(cohort) / "candidate/main.py"
    program.write_text('print("replacement")\n')
    with pytest.raises(ValueError, match="independently evaluated candidate"):
        checked_rows(cohort)


def test_actual_prompt_must_match_its_recorded_identity(cohort):
    def alter(data):
        data["messages"][0]["content"] += "\nAdditional task-specific advice."

    change(first_trial(cohort) / "trial.json", alter)
    with pytest.raises(ValueError, match="preselected condition"):
        checked_rows(cohort)


def test_a_different_successful_mcp_load_is_not_the_matched_control(cohort):
    def alter(data):
        event = next(event for event in data["tool_events"] if event["name"] == "open_skill")
        event["result"]["content"] = "different instructions"

    change(first_trial(cohort) / "trial.json", alter)
    with pytest.raises(ValueError, match="actual skill delivery"):
        checked_rows(cohort)


def test_false_native_token_receipt_is_rejected(cohort):
    def alter(data):
        data["conditions"]["relevant"]["token_count"] -= 1

    change(cohort / "tokenization-check.json", alter)
    with pytest.raises(ValueError, match="native tokenizer"):
        checked_rows(cohort)


def test_missing_failed_trial_is_not_a_smaller_successful_cohort(cohort):
    change(cohort / "summary.json", lambda data: data["trials"].pop())
    with pytest.raises(ValueError, match="incomplete or unexpected"):
        checked_rows(cohort)


def test_usage_headline_cannot_hide_cost(cohort):
    change(
        cohort / "summary.json",
        lambda data: data["trials"][0].update(elapsed_seconds=0),
    )
    with pytest.raises(ValueError, match="usage or execution headline"):
        checked_rows(cohort)


def test_new_inventory_cannot_validate_a_forged_success_page(cohort):
    page = cohort / "index.html"
    page.write_text(page.read_text().replace("0 / 6 tasks resolved", "6 / 6 tasks resolved"))
    (cohort / "manifest.json").unlink()
    (cohort / "context-controls.zip").unlink()
    seal(cohort, "evalarc.skill-context-bundle.v1", "context-controls.zip")
    with pytest.raises(ValueError, match="page differs"):
        verify_bundle(cohort)


def test_initial_and_followup_cannot_be_swapped(tmp_path):
    destination = tmp_path / "collection"
    shutil.copytree(ROOT, destination)
    (destination / "initial").rename(destination / "temporary")
    (destination / "protocol").rename(destination / "initial")
    (destination / "temporary").rename(destination / "protocol")
    with pytest.raises(ValueError, match="original protocol profile"):
        summarize(destination)


def test_new_inventory_cannot_pool_the_cohort_outcomes(tmp_path):
    destination = tmp_path / "collection"
    shutil.copytree(ROOT, destination)
    change(
        destination / "cohorts.json",
        lambda data: data.update(outcomes_are_pooled=True),
    )
    (destination / "manifest.json").unlink()
    (destination / "experiment.zip").unlink()
    seal(destination, SCHEMA, "experiment.zip")
    with pytest.raises(ValueError, match="cohort headline"):
        verify(destination)


def test_diagnostic_cannot_be_attributed_to_a_different_program(tmp_path):
    destination = tmp_path / "collection"
    shutil.copytree(ROOT, destination)
    change(
        destination / "initial/diagnostics/buffering-diagnostic.json",
        lambda data: data.update(candidate_sha256="0" * 64),
    )
    with pytest.raises(ValueError, match="buffering diagnostic"):
        summarize(destination)

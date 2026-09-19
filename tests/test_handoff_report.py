import json
import shutil
import zipfile
from pathlib import Path

import pytest

from scripts.build_handoff_mcp import checked_preflight, checked_rows, verify_bundle

SOURCE = Path(__file__).resolve().parents[1] / "examples/funes-handoff"


def copy_bundle(tmp_path):
    root = tmp_path / "handoff"
    shutil.copytree(SOURCE, root)
    return root


def write(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def test_complete_real_cohort_retains_all_unresolved_and_unchanged_programs():
    assert verify_bundle(SOURCE)["trials"] == 6
    rows = checked_rows(SOURCE)
    assert sum(row["operations"]["retrieved_results"] for row in rows) == 6
    assert all(row["evaluation"]["score"] == 0.875 for row in rows)
    assert all(row["evaluation"]["resolved"] is False for row in rows)
    assert all(row["operations"]["program_changed"] is False for row in rows)


def test_downloaded_archive_verifies_after_extraction_without_hosted_files(tmp_path):
    with zipfile.ZipFile(SOURCE / "funes-handoff.zip") as archive:
        archive.extractall(tmp_path)
    assert not (tmp_path / "manifest.json").exists()
    assert verify_bundle(tmp_path)["trials"] == 6
    candidate = tmp_path / "no-memory/01-none-17/candidate/main.py"
    candidate.write_text(candidate.read_text() + "\n# changed after extraction\n")
    with pytest.raises(ValueError, match="record inventory or bytes"):
        verify_bundle(tmp_path)


def test_native_passage_and_model_view_cannot_both_be_relabelled_as_another_session(tmp_path):
    root = copy_bundle(tmp_path)
    path = root / "funes-mcp/02-none-17/trial.json"
    trial = json.loads(path.read_text())
    event = next(item for item in trial["tool_events"] if item["name"] == "recall_prior_session")
    session = event["result"]["source"]["session_id"]
    event["result"]["text"] = event["result"]["text"].replace(session, "different-session")
    for content in event["receipt"]["raw"]["content"]:
        content["text"] = content["text"].replace(session, "different-session")
    write(path, trial)
    with pytest.raises(ValueError, match="recall cites a different source"):
        checked_rows(root)


def test_summary_and_trial_cannot_jointly_inflate_operation_counts(tmp_path):
    root = copy_bundle(tmp_path)
    summary = json.loads((root / "summary.json").read_text())
    row = summary["trials"][1]
    path = root / row["path"] / "trial.json"
    trial = json.loads(path.read_text())
    row["operations"]["command_attempts"] = 100
    trial["handoff"]["operations"]["command_attempts"] = 100
    write(root / "summary.json", summary)
    write(path, trial)
    with pytest.raises(ValueError, match="operation counts"):
        checked_rows(root)


def test_finished_signal_cannot_be_relabelled_as_independent_resolution(tmp_path):
    root = copy_bundle(tmp_path)
    summary = json.loads((root / "summary.json").read_text())
    row = summary["trials"][0]
    path = root / row["path"] / "trial.json"
    trial = json.loads(path.read_text())
    row["evaluation"]["resolved"] = True
    trial["independent_evaluation"]["resolved"] = True
    write(root / "summary.json", summary)
    write(path, trial)
    with pytest.raises(ValueError, match="independent acceptance"):
        checked_rows(root)


def test_source_deletion_control_cannot_be_reported_as_a_successful_retrieval(tmp_path):
    root = copy_bundle(tmp_path)
    path = root / "preflight/mcp-entrypoint.json"
    record = json.loads(path.read_text())
    record["source_mutation_control"]["view"]["status"] = "retrieved"
    write(path, record)
    with pytest.raises(ValueError, match="missing-source control"):
        checked_preflight(root)

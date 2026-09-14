"""A casebook row must preserve its source evidence and outcome semantics."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_dataset  # noqa: E402
import publish_dataset  # noqa: E402


def table(folder, name):
    return [
        json.loads(line) for line in (folder / "data" / f"{name}.jsonl").read_text().splitlines()
    ]


def original(folder, row):
    source = folder / row["source_file"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == row["source_sha256"]
    value = json.loads(source.read_text())
    for component in row["source_pointer"].split("/")[1:]:
        value = value[int(component)] if isinstance(value, list) else value[component]
    return value


def test_casebook_preserves_source_objects_and_distinct_gate_outcomes(tmp_path):
    folder = tmp_path / "casebook"
    manifest = build_dataset.build(folder)
    assert manifest["row_counts"] == {
        "audit_cases": 251,
        "repetition_attempts": 6,
        "suite_jobs": 3,
    }
    cases = table(folder, "audit_cases")
    assert {row["task"] for row in cases} == {
        "durable-kv",
        "support-routing",
        "robot-evidence-review",
    }
    assert len([row for row in cases if row["task"] == "robot-evidence-review"]) == 84
    assert all(
        row["control_detection_margin"] is None
        for row in cases
        if row["control_kind"] == "reference"
    )
    for row in cases:
        case = original(folder, row)
        assert json.loads(row["case_json"]) == case
        assert row["case_passed"] == case["passed"]
        assert row["failed_checks"] == [
            name for name, passed in case["checks"].items() if passed is False
        ]
    assert any(row["evaluation_score"] == 0.9375 and not row["case_passed"] for row in cases)
    attempts = table(folder, "repetition_attempts")
    for row in attempts:
        evaluation = original(folder, row)
        assert row["score"] == evaluation["score"]
        assert row["resolved"] == evaluation["resolved"]
    assert sum(row["resolved"] for row in attempts) == 3
    jobs = table(folder, "suite_jobs")
    for row in jobs:
        job = original(folder, row)
        assert json.loads(row["gate_json"]) == job["gate"]
        assert json.loads(row["decision_json"]) == job["decision"]
    partial, protected = jobs[1:]
    assert partial["mean_score"] == protected["mean_score"] == 0.9375
    assert partial["candidate_sha256"] == protected["candidate_sha256"]
    assert partial["gate_accepted"] and not protected["gate_accepted"]
    assert not partial["fully_resolved"] and not protected["fully_resolved"]


def test_casebook_rejects_changed_rows_and_duplicate_identities(tmp_path):
    folder = tmp_path / "casebook"
    build_dataset.build(folder)
    path = folder / "data/suite_jobs.jsonl"
    jobs = table(folder, "suite_jobs")
    jobs[2]["id"] = jobs[1]["id"]
    path.write_text("".join(json.dumps(row) + "\n" for row in jobs))
    with pytest.raises(ValueError, match="Bundle file changed"):
        build_dataset.verify(folder)
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["data/suite_jobs.jsonl"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="row inventory"):
        build_dataset.verify(folder)


def test_casebook_never_overwrites_an_existing_directory(tmp_path):
    marker = tmp_path / "keep.txt"
    marker.write_text("original")
    with pytest.raises(ValueError, match="already exists"):
        build_dataset.build(tmp_path)
    assert marker.read_text() == "original"


@pytest.mark.parametrize(
    ("dirty", "expected", "message"),
    [(True, None, "Commit the source"), (False, "0" * 40, "CI source commit")],
)
def test_publisher_rejects_uncommitted_or_wrong_ci_source(
    tmp_path, monkeypatch, dirty, expected, message
):
    folder = tmp_path / "casebook"
    build_dataset.build(folder)
    path = folder / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["source_dirty"] = dirty
    path.write_text(json.dumps(manifest))
    if expected is not None:
        monkeypatch.setenv("GITHUB_SHA", expected)
    with pytest.raises(ValueError, match=message):
        publish_dataset.publish(folder, "example/unreachable")

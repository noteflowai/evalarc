"""Exercise saved native observations, including evidence and authority failures."""

import gzip
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from evalarc.behavior_review import review
from evalarc.cli import main

ROOT = Path(__file__).parents[1] / "examples/behavior-audit/controls"
SERVICE = ROOT.parent / "service-controls"


def copy_case(tmp_path, name="reference"):
    destination = tmp_path / name
    shutil.copytree(ROOT / name, destination)
    return destination


def rewrite_trace(case, transform):
    path = case / "evidence/commands/step-0001.json"
    receipt = json.loads(path.read_text())
    trace = case / "evidence" / receipt["trace_file"]
    raw = transform(gzip.decompress(trace.read_bytes()).decode()).encode()
    packed = gzip.compress(raw, mtime=0)
    trace.write_bytes(packed)
    receipt.update(
        {
            "trace_bytes": len(raw),
            "trace_sha256": hashlib.sha256(raw).hexdigest(),
            "trace_gzip_sha256": hashlib.sha256(packed).hexdigest(),
        }
    )
    path.write_text(json.dumps(receipt))


def test_every_native_control_matches_its_predeclared_outcome():
    plan = json.loads((ROOT / "plan.json").read_text())
    assert len(plan["cases"]) == 24
    for case in plan["cases"]:
        result = review(ROOT / case["id"])
        assert result["valid"], (case["id"], result["coverage_errors"])
        assert result["accepted"] is case["expected_acceptance"]
        assert result["behavior_accepted"] is case["expected_behavior_accepted"]
        assert (result["artifact_accepted"] and result["service_complete"]) is (
            case["expected_task_complete"]
        )


def test_final_files_and_actual_access_are_separate():
    result = review(ROOT / "write-then-delete")
    assert result["artifact_accepted"] and result["service_complete"]
    assert not result["behavior_accepted"]
    writes = [
        e
        for e in result["events"]
        if e["operation"] == "write" and e["path"] == "/workspace/public/unrequested.json"
    ]
    assert writes and writes[0]["completed"] and writes[0]["bytes"] > 0
    assert not (ROOT / "write-then-delete/candidate/public/unrequested.json").exists()


def test_child_and_alias_reads_resolve_to_the_protected_resource():
    for name in ["child-private-read", "symlink-private-read", "hardlink-private-read"]:
        result = review(ROOT / name)
        reads = [
            event
            for event in result["events"]
            if event["operation"] == "read"
            and event["path"] == "/workspace/private/unrelated.json"
            and event["completed"]
            and event["bytes"] > 0
        ]
        assert reads, name
        assert all(not event["permitted"] for event in reads)


def test_metadata_and_mapping_are_not_reported_as_read_bytes():
    metadata = review(ROOT / "metadata-open-path")
    assert metadata["accepted"]
    assert not any(
        e["operation"] == "read" and e["path"] == "/workspace/private/unrelated.json"
        for e in metadata["events"]
    )
    mapped = review(ROOT / "private-readable-mapping")
    mappings = [
        e
        for e in mapped["events"]
        if e["operation"] == "map_read" and e["path"] == "/workspace/private/unrelated.json"
    ]
    assert mappings and mappings[0]["bytes"] is None
    assert not mapped["accepted"]


def test_blocked_attempt_and_committed_service_write_stay_distinct():
    blocked = review(ROOT / "blocked-observer-write")
    events = [e for e in blocked["events"] if e["path"] == "/observer/forged.json"]
    assert events and all(not e["completed"] and e["errno"] == "EACCES" for e in events)
    service = review(ROOT / "encoded-service-write")
    writes = [
        e for e in service["events"] if e["operation"] == "service_write" and e["path"] == "/audit"
    ]
    assert writes and writes[0]["completed"] and writes[0]["status"] == 201
    method = review(ROOT / "rejected-http-method")
    attempts = [e for e in method["events"] if e["operation"] == "service_request"]
    assert attempts and not attempts[0]["completed"] and attempts[0]["status"] == 405
    assert method["service_complete"] and not method["behavior_accepted"]


def test_changing_candidate_bytes_cannot_bypass_the_observed_snapshot(tmp_path):
    case = copy_case(tmp_path)
    (case / "candidate/public/report.json").write_text('{"order_count":3,"total_cents":0}')
    with pytest.raises(ValueError, match="observed final inventory"):
        review(case)


def test_an_extra_symlink_directory_is_not_ignored(tmp_path):
    case = copy_case(tmp_path)
    (case / "candidate/unrecorded").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="inventory"):
        review(case)


def test_rehashing_truncated_evidence_does_not_make_it_complete(tmp_path):
    case = copy_case(tmp_path)
    rewrite_trace(case, lambda text: "\n".join(text.splitlines()[:-1]) + "\n")
    result = review(case)
    assert not result["valid"]
    assert any("terminal" in error["reason"] for error in result["coverage_errors"])


def test_an_uncovered_successful_operation_is_inconclusive(tmp_path):
    case = copy_case(tmp_path)

    def inject(text):
        pid, timestamp = text.splitlines()[0].split()[:2]
        return text + f"{pid} {timestamp} io_uring_setup(1, NULL) = 5\n"

    rewrite_trace(case, inject)
    result = review(case)
    assert not result["valid"]
    assert any(
        "unsupported successful io_uring_setup" in e["reason"] for e in result["coverage_errors"]
    )


def test_a_rewritten_headline_cannot_change_the_recomputed_verdict(tmp_path):
    case = copy_case(tmp_path, "discarded-private-read")
    (case / "review.json").write_text('{"accepted":true,"valid":true}')
    assert not review(case)["accepted"]


def test_cli_is_read_only_and_separates_invalid_evidence_from_rejection(
    monkeypatch, capsys, tmp_path
):
    def forbidden(*_, **__):
        raise AssertionError("a saved behavior review must not execute a subprocess")

    monkeypatch.setattr(subprocess, "run", forbidden)
    assert main(["behavior-review", str(ROOT / "reference"), "--json", "--require-accepted"]) == 0
    assert json.loads(capsys.readouterr().out)["accepted"]
    rejected = str(ROOT / "discarded-private-read")
    assert main(["behavior-review", rejected, "--json"]) == 0
    capsys.readouterr()
    assert main(["behavior-review", rejected, "--json", "--require-accepted"]) == 1
    assert not json.loads(capsys.readouterr().out)["accepted"]
    assert main(["behavior-review", str(tmp_path / "missing"), "--json"]) == 2
    assert not json.loads(capsys.readouterr().out)["valid"]


def test_an_actual_idle_observation_is_valid_but_the_task_is_incomplete():
    result = review(SERVICE / "idle")
    assert result["valid"] and result["behavior_accepted"]
    assert not result["artifact_accepted"] and not result["service_complete"]
    assert not result["accepted"] and result["events"] == []


def test_candidate_health_calls_and_unfamiliar_http_methods_are_observed():
    for name, status in [
        ("candidate-health", 200),
        ("forged-health-header", 200),
        ("unknown-method", 405),
    ]:
        result = review(SERVICE / name)
        assert result["valid"] and result["artifact_accepted"] and result["service_complete"]
        assert not result["behavior_accepted"] and not result["accepted"]
        requests = [e for e in result["events"] if e["operation"] == "service_request"]
        assert len(requests) == 1 and requests[0]["status"] == status
        assert not requests[0]["completed"] and not requests[0]["permitted"]


def test_incomplete_http_evidence_cannot_become_an_authorized_success():
    for name in ["partial-post-timeout", "unparsed-connection", "malformed-request"]:
        result = review(SERVICE / name)
        assert result["artifact_accepted"] and result["service_complete"]
        assert not result["valid"] and not result["accepted"]
        assert result["coverage_errors"]
    reference = review(SERVICE / "service-reference")
    assert reference["accepted"]
    assert not any(e["operation"] == "service_request" for e in reference["events"])

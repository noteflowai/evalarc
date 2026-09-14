import hashlib
import json
from copy import deepcopy

import pytest

from evalarc.interop import import_harbor, inspect_atif, read_document
from evalarc.runner import Runtime


def trajectory():
    return {
        "schema_version": "ATIF-v1.8",
        "agent": {"name": "test-fixture", "version": "1"},
        "steps": [
            {"step_id": 1, "source": "user", "message": "A public fixture"},
            {
                "step_id": 2,
                "source": "agent",
                "message": "Read a file",
                "tool_calls": [
                    {
                        "tool_call_id": "call-1",
                        "function_name": "read_file",
                        "arguments": {"path": "main.py"},
                    }
                ],
                "observation": {"results": [{"source_call_id": "call-1", "content": "print(1)"}]},
            },
        ],
    }


def test_atif_inspection_states_its_actual_scope():
    result = inspect_atif(trajectory())
    assert result["tool_calls"] == 1
    assert result["steps"] == 2
    assert result["full_upstream_schema_validated"] is False


@pytest.mark.parametrize(
    "fault", ["dangling-call", "duplicate-call", "step-order", "future-version"]
)
def test_atif_rejects_broken_linkage_and_unknown_version(fault):
    document = trajectory()
    step = document["steps"][1]
    if fault == "dangling-call":
        step["observation"]["results"][0]["source_call_id"] = "missing"
    elif fault == "duplicate-call":
        step["tool_calls"].append(deepcopy(step["tool_calls"][0]))
    elif fault == "step-order":
        step["step_id"] = 5
    else:
        document["schema_version"] = "ATIF-v9.0"
    with pytest.raises(ValueError):
        inspect_atif(document)


def test_document_retains_the_exact_hashed_bytes(tmp_path):
    source = tmp_path / "source.json"
    raw = b'{ "key": 1 }\n'
    source.write_bytes(raw)
    document, digest, copied = read_document(source)
    assert document == {"key": 1}
    assert digest == hashlib.sha256(raw).hexdigest()
    assert copied == raw
    link = tmp_path / "link.json"
    link.symlink_to(source)
    with pytest.raises(ValueError, match="symlink"):
        read_document(link)


def test_upstream_reward_cannot_override_failed_independent_checks(tmp_path, monkeypatch):
    source = tmp_path / "trial"
    source.mkdir()
    (source / "result.json").write_text(
        json.dumps(
            {
                "trial_name": "reward-claim",
                "verifier_result": {"rewards": {"reward": 1.0}},
                "finished_at": "2026-09-14T00:00:00Z",
                "exception_info": None,
            }
        )
    )
    independent = {
        "valid": True,
        "resolved": False,
        "score": 0.4,
        "status": "failed",
        "candidate_sha256": "a" * 64,
    }
    monkeypatch.setattr("evalarc.interop.evaluate", lambda *a, **k: independent)
    result = import_harbor(source, tmp_path / "candidate", tmp_path / "out", Runtime(), [41])
    assert result["upstream"]["rewards"]["reward"] == 1.0
    assert result["upstream"]["agent_completion"] is None
    assert result["acceptance"]["accepted"] is False
    assert result["independent"]["resolved"] is False
    relaxed = import_harbor(
        source,
        tmp_path / "candidate",
        tmp_path / "relaxed",
        Runtime(),
        [41],
        minimum_score=0.3,
    )
    assert relaxed["acceptance"]["accepted"] is True
    assert relaxed["independent"]["resolved"] is False


@pytest.mark.parametrize("value", [True, "1", 10**1000])
def test_import_rejects_invalid_reward_types(tmp_path, value):
    source = tmp_path / "trial"
    source.mkdir()
    (source / "result.json").write_text(
        json.dumps({"verifier_result": {"rewards": {"reward": value}}})
    )
    with pytest.raises(ValueError, match="finite numeric"):
        import_harbor(source, tmp_path / "candidate", tmp_path / "out", Runtime(), [41])
    assert not (tmp_path / "out").exists()

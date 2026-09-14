import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from evalarc.cli import main
from evalarc.verify import verify

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.mark.parametrize(
    "name,kind,count,resolved",
    [
        ("evaluation", "evaluation", 1, False),
        ("repetition", "repetition", 4, True),
        ("repetition-faulty", "repetition", 4, False),
        ("comparison", "comparison", 3, False),
    ],
)
def test_archived_evidence_verifies_without_runtime_or_writes(
    tmp_path, monkeypatch, name, kind, count, resolved
):
    folder = tmp_path / name
    shutil.copytree(EXAMPLES / name, folder)
    before = {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()}

    def forbidden(*args, **kwargs):
        raise AssertionError("verification must not launch any process")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    result = verify(folder)
    assert result["verified"]
    assert result["kind"] == kind
    assert result["fully_resolved"] is resolved
    assert len(result["files"]) == count
    for name, record in result["files"].items():
        assert record["sha256"] == hashlib.sha256((folder / name).read_bytes()).hexdigest()
    assert before == {
        p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    }


def test_consistency_and_resolution_have_separate_exit_codes(capsys):
    path = str(EXAMPLES / "repetition-faulty")
    assert main(["verify", path, "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["verified"] and not result["fully_resolved"]
    assert main(["verify", path, "--json", "--require-resolved"]) == 1
    assert json.loads(capsys.readouterr().out)["records_valid"]
    assert main(["verify", str(EXAMPLES / "repetition"), "--require-resolved"]) == 0


@pytest.mark.parametrize(
    "name,field", [("repetition", "mean_score"), ("comparison", "score_delta")]
)
def test_changed_summary_is_rejected(tmp_path, name, field):
    shutil.copytree(EXAMPLES / name, tmp_path / "bundle")
    path = tmp_path / "bundle" / f"{name}.json"
    data = json.loads(path.read_text())
    data[field] = 0.123
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="summary differs"):
        verify(path)


@pytest.mark.parametrize("change", ["missing", "extra", "symlink", "boolean", "changed-attempt"])
def test_repetition_requires_exact_attempt_inventory_and_consistent_inputs(tmp_path, change):
    folder = tmp_path / "bundle"
    shutil.copytree(EXAMPLES / "repetition", folder)
    attempt = folder / "attempts" / "0002" / "evaluation.json"
    if change == "missing":
        attempt.unlink()
    elif change == "extra":
        (folder / "attempts" / "0004").mkdir()
    elif change == "symlink":
        attempt.unlink()
        attempt.symlink_to(EXAMPLES / "repetition" / "attempts" / "0002" / "evaluation.json")
    elif change == "boolean":
        path = folder / "repetition.json"
        data = json.loads(path.read_text())
        data["mean_score"] = True
        path.write_text(json.dumps(data))
    else:
        data = json.loads(attempt.read_text())
        data["candidate_sha256"] = "0" * 64
        attempt.write_text(json.dumps(data))
    with pytest.raises((ValueError, OSError)):
        verify(folder)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b"\xff", b"[]", b'{"x":1e999}'])
def test_invalid_json_returns_structured_error(tmp_path, capsys, raw):
    path = tmp_path / "report.json"
    path.write_bytes(raw)
    assert main(["verify", str(path), "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert not result["verified"] and result["error"]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX named pipes")
def test_pipe_is_rejected_without_waiting_for_writer(tmp_path):
    path = tmp_path / "report.json"
    os.mkfifo(path)
    with pytest.raises(ValueError, match="regular file"):
        verify(path)


def test_suite_and_ambiguous_folder_are_explicitly_unsupported(tmp_path):
    with pytest.raises(ValueError, match="for a suite"):
        verify(EXAMPLES / "suite")
    shutil.copytree(EXAMPLES / "repetition", tmp_path / "bundle")
    shutil.copyfile(
        EXAMPLES / "evaluation" / "evaluation.json", tmp_path / "bundle/evaluation.json"
    )
    with pytest.raises(ValueError, match="choose one"):
        verify(tmp_path / "bundle")

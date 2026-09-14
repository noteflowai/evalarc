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
        ("suite", "suite", 12, False),
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


def test_ambiguous_folder_requires_an_explicit_report(tmp_path):
    shutil.copytree(EXAMPLES / "repetition", tmp_path / "bundle")
    shutil.copyfile(
        EXAMPLES / "evaluation" / "evaluation.json", tmp_path / "bundle/evaluation.json"
    )
    with pytest.raises(ValueError, match="choose one"):
        verify(tmp_path / "bundle")


def change_json(path, update):
    data = json.loads(path.read_text())
    update(data)
    path.write_text(json.dumps(data))


@pytest.mark.parametrize(
    "change",
    [
        "accepted",
        "job-decision",
        "boolean-count",
        "job-order",
        "runtime",
        "manifest-gate",
        "repetition",
        "junit-failure",
        "junit-output",
        "missing-job",
        "extra-job",
        "missing-junit",
        "missing-plan",
    ],
)
def test_suite_rejects_inconsistent_configuration_decisions_and_junit(tmp_path, capsys, change):
    folder = tmp_path / "suite"
    shutil.copytree(EXAMPLES / "suite", folder)
    if change == "accepted":
        change_json(folder / "suite.json", lambda d: d.update(accepted=True))
    elif change == "job-decision":
        change_json(folder / "suite.json", lambda d: d["jobs"][2]["decision"].update(accepted=True))
    elif change == "boolean-count":
        change_json(folder / "suite.json", lambda d: d.update(fully_resolved_jobs=True))
    elif change == "job-order":
        change_json(folder / "plan.json", lambda d: d["jobs"].reverse())
    elif change == "runtime":
        change_json(folder / "plan.json", lambda d: d["jobs"][0]["runtime"].update(timeout=500))
    elif change == "manifest-gate":
        config = folder / "suite.toml"
        config.write_text(
            config.read_text().replace(
                'required_dimensions = ["notes"]', "required_dimensions = []"
            )
        )
        digest = hashlib.sha256(config.read_bytes()).hexdigest()
        for name in ("suite.json", "plan.json"):
            change_json(folder / name, lambda d: d.update(manifest_sha256=digest))
        change_json(
            folder / "plan.json", lambda d: d["jobs"][2]["gate"].update(required_dimensions=[])
        )
    elif change == "repetition":
        change_json(
            folder / "jobs/support-partial/repetition.json", lambda d: d.update(mean_score=1)
        )
    elif change.startswith("junit-"):
        path = folder / "junit.xml"
        old, new = (
            ("failure", "error")
            if change == "junit-failure"
            else ('"fully_resolved": false', '"fully_resolved": true')
        )
        path.write_text(path.read_text().replace(old, new))
    elif change == "missing-job":
        shutil.rmtree(folder / "jobs/support-protected")
    elif change == "extra-job":
        (folder / "jobs/unreported").mkdir()
    else:
        (folder / ("junit.xml" if change == "missing-junit" else "plan.json")).unlink()
    assert main(["verify", str(folder), "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert not result["verified"] and result["error"]


@pytest.mark.parametrize("filename", ["suite.toml", "junit.xml", "plan.json"])
def test_suite_rejects_symlinked_inputs(tmp_path, filename):
    folder = tmp_path / "suite"
    shutil.copytree(EXAMPLES / "suite", folder)
    (folder / filename).unlink()
    (folder / filename).symlink_to(EXAMPLES / "suite" / filename)
    with pytest.raises(ValueError, match="symlink"):
        verify(folder)


def test_suite_verification_never_resolves_original_paths_or_prepares_runtime(monkeypatch):
    from evalarc.runner import Runtime

    def forbidden(*args, **kwargs):
        raise AssertionError("offline evidence checking cannot prepare an execution")

    with monkeypatch.context() as patch:
        patch.setattr(Runtime, "prepare", forbidden)
        patch.setattr(Path, "resolve", forbidden)
        patch.setattr(subprocess, "Popen", forbidden)
        result = verify(EXAMPLES / "suite")
    assert result["accepted_jobs"] == 2
    assert result["fully_resolved_jobs"] == 1
    assert not result["accepted"]
    assert {"suite.toml", "plan.json", "junit.xml"} <= result["files"].keys()


def test_suite_gate_requirement_differs_from_record_consistency(capsys):
    path = str(EXAMPLES / "suite")
    assert main(["verify", path, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["verified"]
    assert main(["verify", path, "--json", "--require-accepted"]) == 1
    assert not json.loads(capsys.readouterr().out)["accepted"]
    assert main(["verify", str(EXAMPLES / "repetition"), "--json", "--require-accepted"]) == 2
    assert "requires suite" in json.loads(capsys.readouterr().out)["error"]


@pytest.mark.parametrize(
    "xml",
    [
        '<!DOCTYPE testsuites [<!ENTITY x SYSTEM "file:///not-read">]><testsuites>&x;</testsuites>',
        "<testsuites>" + "<a>" * 20 + "</a>" * 20 + "</testsuites>",
        "<testsuites><invalid></testsuites>",
    ],
)
def test_junit_rejects_entities_invalid_xml_and_deep_structures(tmp_path, xml):
    folder = tmp_path / "suite"
    shutil.copytree(EXAMPLES / "suite", folder)
    (folder / "junit.xml").write_text(xml)
    with pytest.raises(ValueError):
        verify(folder)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX named pipes")
@pytest.mark.parametrize("filename", ["suite.toml", "junit.xml"])
def test_suite_non_json_inputs_must_be_regular_files(tmp_path, filename):
    folder = tmp_path / "suite"
    shutil.copytree(EXAMPLES / "suite", folder)
    (folder / filename).unlink()
    os.mkfifo(folder / filename)
    with pytest.raises(ValueError, match="regular file"):
        verify(folder)

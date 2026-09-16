"""Publishing must not silently accept an altered evidence bundle."""

import importlib.util
import json
import shutil
import tomllib
import zipfile
from pathlib import Path

import pytest

from evalarc.verify import verify as verify_evidence

spec = importlib.util.spec_from_file_location(
    "build_site", Path(__file__).resolve().parents[1] / "scripts" / "build_site.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_downloaded_suite_preserves_bytes_and_verifies_offline(tmp_path):
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    builder.write_suite_bundle(first)
    builder.write_suite_bundle(second)
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert len(archive.namelist()) == 12
        archive.extractall(tmp_path / "received")
    received = tmp_path / "received" / "suite-evidence"
    result = verify_evidence(received)
    assert result["verified"] and not result["accepted"]
    assert result["accepted_jobs"] == 2
    assert result["fully_resolved_jobs"] == 1
    original = builder.ROOT / "examples" / "suite"
    for name in result["files"]:
        assert (received / name).read_bytes() == (original / name).read_bytes()


def test_bundle_rejects_changed_evidence_and_extra_files(tmp_path):
    folder = tmp_path / "site"
    builder.build(folder)
    version = tomllib.loads((builder.ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert f"RESEARCH PREVIEW {version}" in (folder / "index.html").read_text()
    assert "__EVALARC_VERSION__" not in (folder / "index.html").read_text()
    assert "__AUDIT_COVERAGE__" not in (folder / "index.html").read_text()
    assert (folder / "index.html").read_text().count("single-case dependencies") == 3
    assert (folder / "robot/index.html").is_file()
    from scripts.verify_research import verify_lab, verify_records

    for name, verifier in (("skill-impact", verify_lab), ("research", verify_records)):
        verifier(folder / name)
        original = builder.ROOT / "examples" / name
        for source in original.rglob("*"):
            if source.is_file() and source.relative_to(original).as_posix() not in (
                "index.html",
                "manifest.json",
            ):
                assert (folder / name / source.relative_to(original)).read_bytes() == (
                    source.read_bytes()
                )
        page = (folder / name / "index.html").read_text()
        assert 'href="../index.html"' in page
        assert 'href="../"' not in page
    for name in ("skill-impact", "research", "trace-workbench", "trace-mcp", "judge-stability"):
        assert f'href="{name}/index.html"' in (folder / "index.html").read_text()
    assert "__JUDGE_PREVIEW__" not in (folder / "index.html").read_text()
    from evalarc.judge_stability import verify_judgments

    with zipfile.ZipFile(folder / "judge-stability-evidence.zip") as archive:
        archive.extractall(tmp_path / "judge-download")
    received = tmp_path / "judge-download/judge-stability"
    result = verify_judgments(received)
    assert result["verified"] and result["summary"]["gate_disagreements"] == 1
    for source in (folder / "judge-stability").rglob("*"):
        if source.is_file():
            assert (received / source.relative_to(folder / "judge-stability")).read_bytes() == (
                source.read_bytes()
            )
    assert "single-case dependency" in (folder / "robot/index.html").read_text()
    audit = folder / "support" / "audit.json"
    original = audit.read_bytes()
    audit.write_bytes(original.replace(b'"score": 0.9375', b'"score": 1.0000'))
    with pytest.raises(ValueError, match="Bundle file changed"):
        builder.verify(folder)
    audit.write_bytes(original)
    (folder / "unexpected.txt").write_text("unreviewed content")
    with pytest.raises(ValueError, match="inventory"):
        builder.verify(folder)


def test_bundle_never_overwrites_existing_output(tmp_path):
    destination = tmp_path / "site"
    destination.mkdir()
    original = destination / "original.txt"
    original.write_text("preserve")
    with pytest.raises(ValueError, match="already exists"):
        builder.build(destination)
    assert original.read_text() == "preserve"


def test_featured_comparison_is_recomputed_from_evidence(tmp_path, monkeypatch):
    for name in ("comparison", "evaluation"):
        shutil.copytree(builder.ROOT / "examples" / name, tmp_path / "examples" / name)
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    path = tmp_path / "examples" / "comparison" / "comparison.json"
    data = json.loads(path.read_text())
    data["regressions"] = []
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="disagrees with its input"):
        builder.verify_comparison()


def test_featured_repetition_rejects_an_invented_resolution_rate(tmp_path, monkeypatch):
    for name in ("repetition", "repetition-faulty"):
        shutil.copytree(builder.ROOT / "examples" / name, tmp_path / "examples" / name)
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    path = tmp_path / "examples/repetition-faulty/repetition.json"
    data = json.loads(path.read_text())
    data["resolved_attempts"] = 3
    data["assessed_resolution_rate"] = 1
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="disagrees with its attempt"):
        builder.verify_repetitions()


def test_featured_repetition_cannot_drop_an_attempt(tmp_path, monkeypatch):
    for name in ("repetition", "repetition-faulty"):
        shutil.copytree(builder.ROOT / "examples" / name, tmp_path / "examples" / name)
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    (tmp_path / "examples/repetition-faulty/attempts/0003/evaluation.json").unlink()
    with pytest.raises(ValueError, match="disagrees with its attempt"):
        builder.verify_repetitions()


def test_featured_suite_recomputes_its_gate_decisions(tmp_path, monkeypatch):
    shutil.copytree(builder.ROOT / "examples/suite", tmp_path / "examples/suite")
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    path = tmp_path / "examples/suite/suite.json"
    data = json.loads(path.read_text())
    data["jobs"][2]["decision"]["accepted"] = True
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="gate disagrees"):
        builder.verify_suite()


def test_featured_suite_keeps_junit_failure_and_error_distinct(tmp_path, monkeypatch):
    shutil.copytree(builder.ROOT / "examples/suite", tmp_path / "examples/suite")
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    path = tmp_path / "examples/suite/junit.xml"
    path.write_text(path.read_text().replace("<failure", "<error").replace("</failure", "</error"))
    with pytest.raises(ValueError, match="JUnit disagrees"):
        builder.verify_suite()

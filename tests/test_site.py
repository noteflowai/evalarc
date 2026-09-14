"""Publishing must not silently accept an altered evidence bundle."""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "build_site", Path(__file__).resolve().parents[1] / "scripts" / "build_site.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_bundle_rejects_changed_evidence_and_extra_files(tmp_path):
    folder = tmp_path / "site"
    builder.build(folder)
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

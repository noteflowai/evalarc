"""Publishing must not silently accept an altered evidence bundle."""

import importlib.util
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

"""Displayed acceptance must agree with retained independently graded evidence."""

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location(
    "research_checks", ROOT / "scripts/verify_research.py"
)
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)
verify_lab, verify_records = checks.verify_lab, checks.verify_records


def test_all_completed_pilots_are_verifiable():
    assert verify_lab(ROOT / "examples/skill-impact")["trials"] == 27
    assert verify_records(ROOT / "examples/research")["handoff_trials"] == 6


def test_rehashing_a_false_headline_does_not_make_it_true(tmp_path):
    root = tmp_path / "lab"
    shutil.copytree(ROOT / "examples/skill-impact", root)
    path = root / "lab.json"
    lab = json.loads(path.read_text())
    lab["profiles"][0]["trials"][0]["evaluation"]["resolved"] = True
    path.write_text(json.dumps(lab))
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["files"]["lab.json"] = {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }
    (root / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="independent grading"):
        verify_lab(root)

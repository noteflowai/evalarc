import hashlib
import json
import subprocess
import sys
from pathlib import Path

from evalarc.results_diff import load_results
from scripts.model_upgrade_page import evidence

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "examples/model-upgrade"


def test_frozen_model_cohort_has_every_generation_and_explicit_scope():
    data = evidence(ROOT)
    assert len(data["records"]["baseline"]) == len(data["records"]["current"]) == 24
    for identity in data["identities"].values():
        assert not any(identity["loading_info"].values())
    assert data["identities"]["baseline"]["model"] == "Qwen/Qwen3-8B"
    assert data["identities"]["current"]["model"] == "Qwen/Qwen3.8-27B-FP8"


def test_original_answers_reproduce_every_native_check(tmp_path):
    output = tmp_path / "regrade"
    run = subprocess.run(
        [sys.executable, str(SOURCE / "regrade.py"), "--output", str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    redactions = json.loads((output / "redactions.json").read_text())
    assert len(redactions["files"]) == 12
    for name, hashes in redactions["files"].items():
        published = (output / name).read_bytes()
        assert hashlib.sha256(published).hexdigest() == hashes["published_sha256"]
        assert str(output).encode() not in published
        if name.endswith(".xml"):
            from xml.etree import ElementTree as ET

            assert all(suite.attrib["hostname"] == "redacted" for suite in ET.fromstring(published))
    for label in ("baseline", "current"):
        original = load_results(SOURCE / "reports" / f"{label}.xml")
        replayed = load_results(output / f"{label}.xml")

        # Native timestamps and failure source-line text may change, but every
        # named check and repeated outcome must remain identical.
        def outcomes(run):
            return {
                case: {
                    name: [attempt["passed"] for attempt in attempts]
                    for name, attempts in checks.items()
                }
                for case, checks in run["cases"].items()
            }

        assert outcomes(replayed) == outcomes(original)
    result = json.loads((output / "comparison.json").read_text())
    original = json.loads((SOURCE / "reports/comparison.json").read_text())
    assert result["counts"] == original["counts"]
    assert result["gate_passed"] == original["gate_passed"]

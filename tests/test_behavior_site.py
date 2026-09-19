import json
import shutil
import zipfile
from pathlib import Path

import pytest

from scripts.build_behavior_site import build, checked_cases, verify_bundle

SOURCE = Path(__file__).resolve().parents[1] / "examples/behavior-audit"


def test_every_attempt_and_invalid_connection_survives_offline_export(tmp_path):
    output = tmp_path / "public"
    result = build(SOURCE, output)
    assert result["cases"] == 44
    extracted = tmp_path / "offline"
    with zipfile.ZipFile(output / "behavior-evidence.zip") as archive:
        archive.extractall(extracted)
    assert verify_bundle(extracted)["cases"] == 44
    page = (extracted / "pilot/07-composed-41/index.html").read_text()
    assert "unparsed service connection" in page
    assert "Evidence valid</dt><dd>No" in page
    assert "Authorized behavior</dt><dd>Not established" in page
    trace_pages = list((extracted / "controls/write-then-delete").glob("*.strace.html"))
    assert trace_pages and 'id="L' in trace_pages[0].read_text()


def test_public_headline_cannot_replace_raw_behavior_review(tmp_path):
    copied = tmp_path / "records"
    shutil.copytree(SOURCE, copied)
    summary = copied / "pilot/summary.json"
    record = json.loads(summary.read_text())
    record["rows"][0]["accepted"] = True
    summary.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="headline"):
        checked_cases(copied)


def test_archived_mcp_delivery_must_match_frozen_identity(tmp_path):
    copied = tmp_path / "records"
    shutil.copytree(SOURCE, copied)
    path = copied / "pilot/02-cache-17/trial.json"
    trial = json.loads(path.read_text())
    trial["deliveries"][0]["reply"]["view"]["content"] = "different instructions"
    path.write_text(json.dumps(trial))
    with pytest.raises(ValueError, match="MCP delivery"):
        checked_cases(copied)

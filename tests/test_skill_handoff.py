from __future__ import annotations

import copy
import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "prepare_skill_handoff", ROOT / "scripts/prepare_skill_handoff.py"
)
assert spec and spec.loader
preparation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preparation)


@pytest.fixture
def delivery(tmp_path):
    skill = tmp_path / "SKILL.md"
    skill.write_text("---\nname: robot-recording-review\n---\nOriginal guidance.\n")
    pin = {"sha256": hashlib.sha256(skill.read_bytes()).hexdigest(), "bundle_sha256": "a" * 64}
    view = {
        "name": "robot-recording-review",
        "content": "Original guidance.",
        "sha256": pin["sha256"],
        "bundle_sha256": pin["bundle_sha256"],
    }
    trial = {
        "skill_pins": {"robot-recording-review": pin},
        "tool_events": [
            {
                "name": "open_skill",
                "arguments": {"name": "robot-recording-review"},
                "result": view,
                "receipt": {
                    "route": "mcp",
                    "raw": {
                        "structuredContent": {
                            "sha256": pin["sha256"],
                            "bundle": {"sha256": pin["bundle_sha256"]},
                            "content": view["content"],
                        }
                    },
                },
            }
        ],
    }
    return skill, trial


def test_prior_mcp_delivery_binds_the_original_skill(delivery):
    skill, trial = delivery
    assert preparation.prior_skill(trial, skill) == (trial["skill_pins"], 0)
    skill.write_text("A later skill version")
    with pytest.raises(ValueError, match="original SKILL.md differs"):
        preparation.prior_skill(trial, skill)


@pytest.mark.parametrize("mutation", ["no-load", "direct", "error", "bundle", "content", "pin"])
def test_pins_alone_or_failed_delivery_do_not_establish_a_handoff(delivery, mutation):
    skill, original = delivery
    trial = copy.deepcopy(original)
    event = trial["tool_events"][0]
    if mutation == "no-load":
        trial["tool_events"] = []
    elif mutation == "direct":
        event["receipt"]["route"] = "direct"
    elif mutation == "error":
        event["receipt"]["raw"]["isError"] = True
    elif mutation == "bundle":
        event["result"]["bundle_sha256"] = "b" * 64
    elif mutation == "content":
        event["result"]["content"] = "Different delivered instructions"
    elif mutation == "pin":
        trial["skill_pins"] = {}
    with pytest.raises(ValueError):
        preparation.prior_skill(trial, skill)

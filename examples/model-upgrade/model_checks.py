"""Regrade preserved model outputs with pytest; no model or service is called."""

import json
import os
from pathlib import Path

import pytest
from protocol import CASES, EXPECTED

CHECKS = ("json-schema", "routing", "note-and-retry-key", "closure", "complete-plan")


@pytest.mark.parametrize("case,expected", zip(CASES, EXPECTED), ids=[c["id"] for c in CASES])
@pytest.mark.parametrize("check", CHECKS)
def test_plan(case, expected, check):
    source = Path(os.environ["MODEL_RECORD"])
    record = json.loads((source / f"{case['id']}-{os.environ['MODEL_SEED']}.json").read_text())
    try:
        parsed = json.loads(record["text"])
    except (ValueError, TypeError) as error:
        pytest.fail(f"Output is not JSON: {error}\nRaw output: {record['text']}")
    assert isinstance(parsed, dict) and set(parsed) == {"actions"}, "Expected only actions"
    actions = parsed["actions"]
    assert isinstance(actions, list), "actions must be an array"
    assert all(
        isinstance(action, dict)
        and set(action) == {"tool", "arguments"}
        and isinstance(action["arguments"], dict)
        and action["tool"] in {"assign_queue", "add_note", "close_ticket"}
        for action in actions
    ), "Unknown tools or malformed calls"
    if check == "json-schema":
        return
    tool = {
        "routing": "assign_queue",
        "note-and-retry-key": "add_note",
        "closure": "close_ticket",
    }.get(check)
    observed = actions if tool is None else [a for a in actions if a["tool"] == tool]
    wanted = expected if tool is None else [a for a in expected if a["tool"] == tool]
    assert observed == wanted, f"{check}: generated calls differ from the explicit contract"

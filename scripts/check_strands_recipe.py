"""Exercise the optional SDK recipe with network attempts rejected and recorded."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
network_attempts = []


def reject_network(event: str, args: tuple) -> None:
    if event in ("socket.connect", "socket.getaddrinfo"):
        network_attempts.append(event)
        raise RuntimeError("The recorded-state recipe must work without a network connection")


sys.addaudithook(reject_network)
spec = importlib.util.spec_from_file_location(
    "strands_state_recipe", ROOT / "examples/strands-state-review/run.py"
)
recipe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recipe)

with tempfile.TemporaryDirectory(prefix="evalarc-strands-check-") as temporary:
    destination = Path(temporary) / "review"
    result = recipe.run(ROOT / "examples/comparison", destination)
    assert result["baseline"]["native_mean_score"] == 0.75
    assert result["current"]["native_mean_score"] == 0.875
    assert result["regressions"] == [["retry-after-commit@17", "ticket.notes"]]
    assert len(result["improvements"]) == 2
    assert not result["regression_gate_passes"]
    assert not result["baseline"]["all_rows_pass"]
    assert not result["current"]["all_rows_pass"]

    # Serialize and load native SDK reports; evaluator identities must survive.
    before = recipe.EvaluationReport.from_file(str(destination / "baseline-native.json"))
    after = recipe.EvaluationReport.from_file(str(destination / "current-native.json"))
    comparison = recipe.compare_reports(before, after)
    assert comparison["regressions"] == result["regressions"]
    assert recipe.compare_reports(after, before)["regressions"] == result["improvements"]
    for name in ("baseline", "current"):
        original = ROOT / f"examples/strands-state-review/recorded/{name}-native.json"
        assert json.loads(original.read_text()) == json.loads(
            (destination / f"{name}-native.json").read_text()
        )
    assert result == json.loads(
        (ROOT / "examples/strands-state-review/recorded/comparison.json").read_text()
    )

    # Missing or duplicate rows must not masquerade as an improved regression-free run.
    missing = after.model_copy(deep=True)
    missing.cases.pop()
    missing.test_passes.pop()
    try:
        recipe.compare_reports(before, missing)
    except ValueError:
        pass
    else:
        raise AssertionError("A missing check escaped the comparison inventory guard")
    duplicate = after.model_copy(deep=True)
    duplicate.cases.append(duplicate.cases[0])
    duplicate.test_passes.append(duplicate.test_passes[0])
    try:
        recipe.compare_reports(before, duplicate)
    except ValueError:
        pass
    else:
        raise AssertionError("A duplicate check escaped the comparison inventory guard")

    original = (destination / "comparison.json").read_bytes()
    try:
        recipe.run(ROOT / "examples/comparison", destination)
    except FileExistsError:
        pass
    else:
        raise AssertionError("The example overwrote an existing review")
    assert (destination / "comparison.json").read_bytes() == original

assert not network_attempts, network_attempts
print(json.dumps({"native_sdk_review": True, "network_attempts": network_attempts}))

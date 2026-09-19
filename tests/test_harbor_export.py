"""Exercise the actual exported answer verifier with independent program outputs."""

import importlib.util
import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from evalarc.templates import asset

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location(
    "harbor_export", ROOT / "scripts/export_harbor_task.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def run_export(tmp_path, *, partial, clock=True, missing=False):
    task = tmp_path / "task"
    module.export(task, partial_credit=partial)
    candidate = tmp_path / "main.py"
    candidate.write_text(
        asset("robot_reference.py").replace("USE_CLOCK = True", f"USE_CLOCK = {clock!r}")
    )
    answers = tmp_path / "answers.jsonl"
    with (task / "environment/requests.jsonl").open("rb") as source, answers.open("wb") as out:
        subprocess.run([sys.executable, "-I", str(candidate)], stdin=source, stdout=out, check=True)
    if missing:
        answers.unlink()
    logs = tmp_path / "logs"
    verifier = task / "tests/check.py"
    # Only replace container mount points; execute the exported grader itself.
    verifier.write_text(
        verifier.read_text()
        .replace('Path("/workspace/answers.jsonl")', f"Path({str(answers)!r})")
        .replace('Path("/logs/verifier")', f"Path({str(logs)!r})")
    )
    subprocess.run([sys.executable, "-B", str(verifier)], check=True)
    return (
        task,
        float((logs / "reward.txt").read_text()),
        json.loads((logs / "evidence.json").read_text()),
    )


@pytest.mark.parametrize("partial", [False, True])
def test_correct_program_passes_both_versioned_reward_modes(tmp_path, partial):
    task, reward, evidence = run_export(tmp_path, partial=partial)
    assert reward == 1.0
    assert evidence["passed"] is True
    assert len(evidence["findings"]) == 8
    version = tomllib.loads((task / "task.toml").read_text())["task"]["version"]
    assert version == ("0.2.0" if partial else "0.1.0")
    assert not (task / "environment/evalarc").exists()
    assert (task / "tests/evalarc/robot_task.py").is_file()


@pytest.mark.parametrize("partial", [False, True])
def test_partial_credit_is_not_full_completion(tmp_path, partial):
    _, reward, evidence = run_export(tmp_path, partial=partial, clock=False)
    assert evidence["passed"] is False
    assert evidence["weighted_score"] == pytest.approx(0.8)
    assert reward == pytest.approx(0.8 if partial else 0.0)
    failed = [row for row in evidence["findings"] if not row["passed"]]
    assert len(failed) == 4
    assert all(
        row["checks"]["clock"] is False and row["checks"]["metrics"] is False for row in failed
    )


def test_missing_answers_are_not_awarded_partial_credit(tmp_path):
    _, reward, evidence = run_export(tmp_path, partial=True, missing=True)
    assert reward == 0
    assert evidence["passed"] is False
    assert evidence["error"]

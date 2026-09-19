"""Recorder failures must retain the attempt and any delivered program."""

import argparse
import hashlib
import json

from scripts import record_skill_impact as recorder


def arguments(output):
    return argparse.Namespace(
        output=output,
        docker_command="test-only",
        endpoint="test://model",
        task_context="inline",
        protocol_check=False,
        max_steps=2,
        max_new_tokens=100,
        wall_seconds=10,
        temperature=0.2,
        evaluation_seeds=[41, 97],
    )


class Workspace:
    def __init__(self, _runtime):
        self.files = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def request(self, operation, **args):
        assert operation == "write"
        self.files[args["path"]] = args["content"]
        return {"ok": True}

    def export(self, destination):
        destination.mkdir()
        hashes = {}
        for name, content in self.files.items():
            (destination / name).write_text(content)
            hashes[name] = hashlib.sha256(content.encode()).hexdigest()
        return hashes


def test_failed_runtime_preparation_is_an_attempt_not_a_zero_score(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder, "fetch", lambda *_: {"model": "test-only"})

    def unavailable(_):
        raise RuntimeError("test-only daemon unavailable")

    monkeypatch.setattr(recorder.Runtime, "prepare", unavailable)
    row = recorder.trial(arguments(tmp_path), "none", 17, 1)
    record = json.loads((tmp_path / row["path"] / "trial.json").read_text())
    assert record["status"] == "environment_error"
    assert "daemon unavailable" in record["error"]
    assert record["independent_evaluation"] is None
    assert record["turns"] == []


def test_inference_failure_keeps_delivered_program_and_grading_failure_visible(
    tmp_path, monkeypatch
):
    def failed_generation(url, *_args, **_kwargs):
        if url.endswith("/health"):
            return {"model": "test-only"}
        raise RuntimeError("test-only inference disconnected")

    def failed_grading(*_args):
        raise RuntimeError("test-only grader unavailable")

    monkeypatch.setattr(recorder, "fetch", failed_generation)
    monkeypatch.setattr(recorder.Runtime, "prepare", lambda _: None)
    monkeypatch.setattr(recorder, "AgentSandbox", Workspace)
    monkeypatch.setattr(recorder, "evaluate", failed_grading)
    starter = 'print("test-only public starter")\n'
    row = recorder.trial(arguments(tmp_path), "none", 17, 1, starter=starter)
    destination = tmp_path / row["path"]
    record = json.loads((destination / "trial.json").read_text())
    assert (destination / "candidate/main.py").read_text() == starter
    assert record["candidate_files"]["main.py"] == hashlib.sha256(starter.encode()).hexdigest()
    assert record["status"] == "evaluation_error"
    assert "inference disconnected" in record["error"]
    assert "grader unavailable" in record["error"]
    assert record["independent_evaluation"] is None
    assert record["completion_tokens"] == 0

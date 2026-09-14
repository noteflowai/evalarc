import json
import subprocess
import time

import pytest

from evalarc.audit import asset, audit, write_candidate
from evalarc.cli import main
from evalarc.runner import CandidateError, EnvironmentFailure, Runtime


@pytest.mark.parametrize("field", ["timeout", "case_timeout"])
@pytest.mark.parametrize("value", [True, 0, -1, float("nan"), float("inf"), 10**500])
def test_runtime_rejects_invalid_time_budgets(field, value):
    with pytest.raises(ValueError, match="finite and positive"):
        Runtime(backend="local", **{field: value}).prepare()


@pytest.mark.parametrize("value", [True, 0, -1, float("nan"), 1.5])
def test_runtime_rejects_invalid_output_limits(value):
    with pytest.raises(ValueError, match="positive integer"):
        Runtime(backend="local", output_limit=value).prepare()


def test_many_prompt_responses_cannot_reset_total_case_budget(tmp_path):
    candidate = write_candidate(
        tmp_path / "candidate",
        "import sys, time\nfor _ in sys.stdin:\n time.sleep(.06)\n print('{}', flush=True)\n",
    )
    runtime = Runtime(backend="local", timeout=1, case_timeout=0.35)
    started = time.monotonic()
    count = 0
    with runtime.start(candidate, tmp_path) as process:
        with pytest.raises(CandidateError, match="case time budget"):
            for _ in range(50):
                assert process.request({}) == {}
                count += 1
    assert 0 < count < 50
    assert time.monotonic() - started < 3
    assert process.proc.poll() is not None


def test_case_deadline_is_shared_across_restarts(tmp_path):
    candidate = write_candidate(
        tmp_path / "candidate", "import sys\nfor _ in sys.stdin: print('{}', flush=True)\n"
    )
    runtime = Runtime(backend="local").for_case()
    deadline = runtime.deadline
    with runtime.start(candidate, tmp_path) as process:
        assert process.request({}) == {}
        process.finish("eof")
    with runtime.start(candidate, tmp_path) as process:
        assert process.runtime.deadline == deadline
        process.finish("eof")
    runtime.deadline = time.monotonic() - 1
    with pytest.raises(CandidateError, match="case time budget"):
        runtime.start(candidate, tmp_path)


def test_diagnostics_include_bounded_stderr_written_after_eof(tmp_path):
    candidate = write_candidate(
        tmp_path / "candidate",
        "import sys\nfor _ in sys.stdin: print('{}', flush=True)\n"
        "sys.stderr.write('x' * 5000 + 'final diagnostic')\n",
    )
    with Runtime(backend="local").start(candidate, tmp_path) as process:
        assert process.request({}) == {}
        process.finish("eof")
    diagnostics = process.diagnostics()
    assert diagnostics["exit_code"] == 0
    assert diagnostics["stderr_tail"].endswith("final diagnostic")
    assert len(diagnostics["stderr_tail"]) == 2048
    assert diagnostics["output_bytes"] == 5000 + len("final diagnostic") + 3


def test_docker_cleanup_timeout_still_releases_local_process_and_pipes(tmp_path, monkeypatch):
    candidate = write_candidate(tmp_path / "candidate", "import time\ntime.sleep(30)\n")
    process = Runtime(backend="local").start(candidate, tmp_path)
    process.runtime.backend = "docker"

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("docker rm", 20)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(EnvironmentFailure, match="Docker cleanup"):
        process.close()
    assert process.proc.poll() is not None
    assert all(
        stream.closed for stream in (process.proc.stdin, process.proc.stdout, process.proc.stderr)
    )
    assert process.selector.get_map() is None


def test_cleanup_failure_preserves_cancellation(tmp_path, monkeypatch):
    candidate = write_candidate(tmp_path / "candidate", "import time\ntime.sleep(30)\n")
    process = Runtime(backend="local").start(candidate, tmp_path)
    process.runtime.backend = "docker"

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("docker rm", 20)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(KeyboardInterrupt) as cancelled:
        with process:
            raise KeyboardInterrupt()
    assert "Docker cleanup" in cancelled.value.__notes__[0]
    assert process.proc.poll() is not None


def test_cancellation_cli_returns_130_and_retains_external_jsonl_only(
    tmp_path, monkeypatch, capsys
):
    import evalarc.cli

    candidate = write_candidate(tmp_path / "candidate", asset("support_reference.py"))
    output = tmp_path / "run"

    def cancel(*args, on_event=None):
        on_event({"schema_version": "evalarc.event.v1", "event": "test_started"})
        raise KeyboardInterrupt()

    monkeypatch.setattr(evalarc.cli, "evaluate", cancel)
    assert (
        main(
            [
                "evaluate",
                str(candidate),
                "--backend",
                "local",
                "--trust-local",
                "--output",
                str(output),
                "--progress",
            ]
        )
        == 130
    )
    events = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    assert [event["event"] for event in events] == ["test_started", "run_cancelled"]
    assert not output.exists()
    assert not list(tmp_path.glob(".run-*"))


def test_audit_events_label_every_control_without_candidate_payloads():
    events = []
    result = audit(Runtime(backend="local"), [17], "support-routing", on_event=events.append)
    assert result["passed"]
    controls = {event["control"] for event in events if event["event"] == "evaluation_started"}
    assert controls == {"reference"} | {row["name"] for row in result["mutants"]}
    assert all("stderr_tail" not in event and "trace" not in event for event in events)

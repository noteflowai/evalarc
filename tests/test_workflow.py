import json

import pytest

from evalarc.artifacts import new_json, new_run
from evalarc.audit import asset, write_candidate
from evalarc.cli import main
from evalarc.doctor import diagnose
from evalarc.runner import Runtime


def test_run_files_are_published_together_and_existing_runs_are_preserved(tmp_path):
    output = tmp_path / "run"
    with new_run(output) as staged:
        (staged / "evaluation.json").write_text("evidence")
        assert list(output.iterdir()) == []
        (staged / "index.html").write_text("report")
    assert sorted(path.name for path in output.iterdir()) == ["evaluation.json", "index.html"]
    with pytest.raises(ValueError, match="already exists"):
        with new_run(output):
            pytest.fail("existing run must not be entered")
    assert (output / "evaluation.json").read_text() == "evidence"


def test_failed_run_removes_only_its_own_unpublished_artifacts(tmp_path):
    output = tmp_path / "run"
    with pytest.raises(RuntimeError, match="interrupted"):
        with new_run(output) as staged:
            (staged / "partial.json").write_text("incomplete")
            raise RuntimeError("interrupted")
    assert not output.exists()
    assert not list(tmp_path.iterdir())


def test_external_file_in_reserved_directory_is_not_overwritten(tmp_path):
    output = tmp_path / "run"
    with pytest.raises(OSError):
        with new_run(output) as staged:
            (staged / "ours.json").write_text("complete")
            (output / "theirs.txt").write_text("concurrent external write")
    assert (output / "theirs.txt").read_text() == "concurrent external write"
    assert not (output / "ours.json").exists()


def test_atomic_json_refuses_overwrite_and_cleans_temporary_files(tmp_path):
    output = tmp_path / "trajectory.json"
    new_json(output, {"score": 1})
    with pytest.raises(ValueError, match="already exists"):
        new_json(output, {"score": 0})
    assert json.loads(output.read_text()) == {"score": 1}
    assert list(tmp_path.iterdir()) == [output]


def test_cli_existing_output_rejected_before_candidate_runs(tmp_path, monkeypatch, capsys):
    import evalarc.cli

    def forbidden(*args):
        pytest.fail("candidate must not run when output already exists")

    monkeypatch.setattr(evalarc.cli, "evaluate", forbidden)
    candidate = write_candidate(tmp_path / "candidate", asset("support_reference.py"))
    output = tmp_path / "existing"
    output.mkdir()
    (output / "evidence.json").write_text("keep")
    assert (
        main(
            [
                "evaluate",
                str(candidate),
                "--task",
                "support-routing",
                "--backend",
                "local",
                "--trust-local",
                "--output",
                str(output),
            ]
        )
        == 2
    )
    assert "choose a new run directory" in capsys.readouterr().err
    assert (output / "evidence.json").read_text() == "keep"


def test_cli_output_cannot_contaminate_candidate_snapshot(tmp_path, capsys):
    candidate = write_candidate(tmp_path / "candidate", asset("support_reference.py"))
    assert (
        main(
            [
                "evaluate",
                str(candidate),
                "--task",
                "support-routing",
                "--backend",
                "local",
                "--trust-local",
                "--output",
                str(candidate / "results"),
            ]
        )
        == 2
    )
    assert "outside the candidate workspace" in capsys.readouterr().err
    assert not (candidate / "results").exists()


def test_doctor_inspects_without_executing_candidate(tmp_path, capsys):
    marker = tmp_path / "executed"
    candidate = write_candidate(
        tmp_path / "candidate",
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
    )
    assert (
        main(
            [
                "doctor",
                "--backend",
                "local",
                "--candidate",
                str(candidate),
                "--json",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["ready"]
    assert {check["name"] for check in report["checks"]} == {
        "host",
        "runtime",
        "candidate",
        "executable",
    }
    assert not marker.exists()
    assert [path.name for path in candidate.iterdir()] == ["main.py"]


def test_doctor_reports_missing_executable(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "evalarc.toml").write_text('command = ["evalarc-no-such-executable"]\n')
    report = diagnose(Runtime(backend="local"), candidate)
    assert not report["ready"]
    assert report["checks"][-1]["name"] == "executable"
    assert report["checks"][-1]["status"] == "failed"


def test_doctor_reports_unavailable_docker_as_check_failure(monkeypatch):
    def unavailable(self):
        raise ValueError("Docker image unavailable: missing-image")

    monkeypatch.setattr(Runtime, "prepare", unavailable)
    report = diagnose(Runtime(), task_id="support-routing")
    assert not report["ready"]
    assert report["checks"][-1]["detail"].startswith("Docker image unavailable")


def test_tasks_json_lists_both_packs(capsys):
    assert main(["tasks", "--json"]) == 0
    tasks = json.loads(capsys.readouterr().out)
    assert {task["id"] for task in tasks} == {"durable-kv", "support-routing"}


def test_evaluate_creates_html_and_json_for_real_candidate(tmp_path):
    candidate = write_candidate(tmp_path / "candidate", asset("support_reference.py"))
    output = tmp_path / "evaluation"
    assert (
        main(
            [
                "evaluate",
                str(candidate),
                "--task",
                "support-routing",
                "--backend",
                "local",
                "--trust-local",
                "--seeds",
                "17",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert json.loads((output / "evaluation.json").read_text())["resolved"]
    assert "Case evidence" in (output / "index.html").read_text()
    assert "retry-after-commit" in (output / "index.html").read_text()
    assert list(tmp_path.glob(".evaluation-*")) == []


def test_failed_setup_does_not_leave_empty_run_directory(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "evalarc.toml").write_text("command = []\n")
    output = tmp_path / "evaluation"
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
            ]
        )
        == 2
    )
    assert not output.exists()

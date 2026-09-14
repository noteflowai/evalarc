import json
import shlex
import sys

import pytest

from evalarc.audit import asset, write_candidate
from evalarc.cli import main
from evalarc.evaluate import evaluate
from evalarc.runner import CandidateError, EnvironmentFailure, Runtime, snapshot
from evalarc.tasks import get_task
from evalarc.trajectory import summarize


def test_custom_entrypoint_with_spaces_and_state_placeholder(tmp_path):
    candidate = tmp_path / "workspace"
    candidate.mkdir()
    (candidate / "service with spaces.py").write_text(asset("reference.py"))
    (candidate / "evalarc.toml").write_text(
        'command = ["{python}", "-I", "-B", "service with spaces.py", "{state}/db file"]\n'
    )
    result = evaluate(candidate, Runtime(backend="local"), [17])
    assert result["resolved"]
    assert result["runtime"]["command"][-1] == "{state}/db file"


def test_command_manifest_is_snapshotted_and_shell_text_stays_literal(tmp_path):
    candidate = write_candidate(
        tmp_path / "candidate",
        "import json, sys\nfor _ in sys.stdin: print(json.dumps(sys.argv[1:]), flush=True)\n",
    )
    literal = "$(touch escaped); echo never"
    (candidate / "evalarc.toml").write_text(
        'command = ["{python}", "main.py", ' + json.dumps(literal) + "]\n"
    )
    copied = tmp_path / "copy"
    snapshot(candidate, copied)
    (candidate / "evalarc.toml").write_text('command = ["missing-executable"]\n')
    runtime = Runtime(backend="local").for_candidate(copied, get_task("durable-kv").default_command)
    with runtime.start(copied, tmp_path) as process:
        assert process.request({}) == [literal]
        process.finish("eof")
    assert not (copied / "escaped").exists()


@pytest.mark.parametrize(
    "config",
    [
        'command = "python main.py"',
        "command = []",
        'command = ["python", 1]',
        'command = ["python"]\ntask = "support-routing"',
    ],
)
def test_invalid_manifests_cannot_select_a_task(tmp_path, config):
    candidate = write_candidate(tmp_path / "candidate", asset("starter.py"))
    (candidate / "evalarc.toml").write_text(config)
    with pytest.raises(ValueError, match="command"):
        evaluate(candidate, Runtime(backend="local"), [17])


def test_executable_mode_is_preserved_and_fingerprinted(tmp_path):
    candidate = write_candidate(tmp_path / "candidate", "print('hello')\n")
    original = snapshot(candidate, tmp_path / "first")
    (candidate / "main.py").chmod(0o755)
    executable = snapshot(candidate, tmp_path / "second")
    assert original != executable
    assert (tmp_path / "second/main.py").stat().st_mode & 0o111


def test_missing_runtime_produces_invalid_report_and_cli_exit_two(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "evalarc.toml").write_text('command = ["evalarc-no-such-runtime"]\n')
    output = tmp_path / "output"
    assert (
        main(
            [
                "evaluate",
                str(candidate),
                "--backend",
                "local",
                "--trust-local",
                "--task",
                "support-routing",
                "--seeds",
                "17",
                "--output",
                str(output),
            ]
        )
        == 2
    )
    report = json.loads((output / "evaluation.json").read_text())
    assert report["score"] is None and report["valid"] is False


def test_docker_launch_errors_are_distinct_from_agent_exits(tmp_path):
    fake_docker = tmp_path / "fake_docker.py"
    fake_docker.write_text("raise SystemExit(125)\n")
    candidate = write_candidate(tmp_path / "candidate", "raise SystemExit(125)\n")
    docker = Runtime(
        backend="docker",
        timeout=1,
        docker_command=shlex.join([sys.executable, str(fake_docker)]),
        image_id="sha256:test",
    )
    with pytest.raises(EnvironmentFailure, match="Docker.*startup readiness"):
        docker.start(candidate, tmp_path)
    with Runtime(backend="local", timeout=1).start(candidate, tmp_path) as process:
        with pytest.raises(CandidateError, match="exited"):
            process.request({})


def test_checkpoint_comparison_includes_execution_command(tmp_path):
    candidate = write_candidate(tmp_path / "candidate", asset("support_reference.py"))
    first = evaluate(candidate, Runtime(backend="local"), [17], "support-routing")
    (candidate / "evalarc.toml").write_text('command = ["{python}", "-B", "main.py"]\n')
    second = evaluate(candidate, Runtime(backend="local"), [17], "support-routing")
    with pytest.raises(ValueError, match="same task"):
        summarize(
            [
                {"elapsed_seconds": 1, "evaluation": first},
                {"elapsed_seconds": 2, "evaluation": second},
            ],
            10,
        )


def test_the_two_declared_versions_agree():
    """The version lives in pyproject and in the package.

    CI catches a mismatch only after building a wheel, which the documented local
    gate does not do, so a bump that updates one file and not the other passes
    locally and fails remotely. Tie them here instead.
    """
    import tomllib
    from pathlib import Path

    import evalarc

    root = Path(__file__).resolve().parent.parent
    declared = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    assert evalarc.__version__ == declared

"""Trusted local daemon doubles exercise timing; no untrusted code runs here."""

import shlex
import sys

import pytest

from evalarc.runner import EnvironmentFailure, Runtime


def daemon(tmp_path, *, delay=0.2, prelude=None):
    script = tmp_path / "daemon.py"
    script.write_text(
        "import os,sys,time\n"
        "args=sys.argv[1:]\n"
        "if args[0]=='rm': sys.exit(0)\n"
        f"time.sleep({delay!r})\n"
        + (
            "start=args.index('/bin/sh')\nos.execvp(args[start],args[start:])\n"
            if prelude is None
            else f"print({prelude!r},flush=True)\n"
        )
    )
    return shlex.join([sys.executable, str(script)])


def test_candidate_response_timer_starts_after_daemon_readiness(tmp_path):
    runtime = Runtime(
        docker_command=daemon(tmp_path),
        image_id="sha256:test-double",
        timeout=0.1,
        startup_timeout=1,
        case_timeout=2,
        command=(
            sys.executable,
            "-c",
            "import sys; sys.stdin.readline(); print('{\"ok\":true}',flush=True)",
        ),
    ).for_case()
    runtime.prepare()
    with runtime.start(tmp_path, tmp_path) as process:
        assert process.request({"go": True}) == {"ok": True}
        process.finish("eof")
        assert process.output_bytes == len(b'{"ok":true}\n')


def test_missing_readiness_is_an_environment_failure(tmp_path):
    runtime = Runtime(
        docker_command=daemon(tmp_path, delay=0.3),
        image_id="sha256:test-double",
        timeout=1,
        startup_timeout=0.03,
    )
    with pytest.raises(EnvironmentFailure, match="startup readiness timeout"):
        runtime.start(tmp_path, tmp_path)


def test_incorrect_prelude_cannot_be_used_as_candidate_output(tmp_path):
    runtime = Runtime(
        docker_command=daemon(tmp_path, delay=0, prelude='{"ok":true}'),
        image_id="sha256:test-double",
    )
    with pytest.raises(EnvironmentFailure, match="invalid startup prelude"):
        runtime.start(tmp_path, tmp_path)


def test_startup_remains_inside_total_case_budget(tmp_path):
    runtime = Runtime(
        docker_command=daemon(tmp_path, delay=0.3),
        image_id="sha256:test-double",
        timeout=1,
        startup_timeout=10,
        case_timeout=0.05,
    )
    with pytest.raises(EnvironmentFailure, match="startup readiness timeout"):
        runtime.start(tmp_path, tmp_path)

"""Static analysis as stable pass/fail checks for `evalarc diff`.

Run this file with pytest against the code an agent produced, once per revision:

    python -m pytest examples/static-analysis/test_static_analysis.py \
        --target path/to/agent/output --junitxml static.xml

Each analyzer is one test with a fixed name, so the JUnit report always contains the same
checks and `evalarc diff baseline.xml current.xml` fails when one stops passing. Do not
feed a linter's own JUnit report to `evalarc diff`: it lists only violations, under file
paths that change between runs, so a new violation appears as an added check (which does
not block) and a fixed one as a removed check (which does).
"""

from __future__ import annotations

import shutil
import subprocess
import sys

import pytest


def run(*command: str, cwd) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=300)


def test_ruff_lint(target):
    done = run(sys.executable, "-m", "ruff", "check", "--no-cache", "--isolated", ".", cwd=target)
    assert done.returncode == 0, done.stdout[-2000:]


def test_ruff_format(target):
    done = run(
        sys.executable,
        "-m",
        "ruff",
        "format",
        "--check",
        "--no-cache",
        "--isolated",
        ".",
        cwd=target,
    )
    assert done.returncode == 0, done.stdout[-2000:]


@pytest.mark.skipif(shutil.which("mypy") is None, reason="mypy is not installed")
def test_mypy(target):
    done = run("mypy", "--ignore-missing-imports", ".", cwd=target)
    assert done.returncode == 0, done.stdout[-2000:]


@pytest.mark.skipif(shutil.which("bandit") is None, reason="bandit is not installed")
def test_bandit(target):
    done = run("bandit", "-q", "-r", ".", cwd=target)
    assert done.returncode == 0, done.stdout[-2000:]

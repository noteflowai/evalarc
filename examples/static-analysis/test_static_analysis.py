"""Static analysis as stable pass/fail checks for `evalarc diff`.

Run this file with pytest against the code an agent produced, once per revision:

    python -m pytest examples/static-analysis/test_static_analysis.py \
        --target path/to/agent/output --junitxml static.xml

Each analyzer is one test with a fixed name, so the JUnit report always contains the same
checks and `evalarc diff baseline.xml current.xml` fails when one stops passing. Do not
feed a linter's own JUnit report to `evalarc diff`: its testcases are keyed by rule and
absolute path, so a second violation of a rule that already fires in a file is missed,
and moving the code or fixing the last violation of a rule fails the gate.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys

import pytest


def available(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


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


@pytest.mark.skipif(not available("mypy"), reason="mypy is not installed")
def test_mypy(target):
    # No cache, so nothing is written into the analyzed folder.
    done = run(
        sys.executable,
        "-m",
        "mypy",
        "--ignore-missing-imports",
        "--cache-dir",
        "/dev/null",
        ".",
        cwd=target,
    )
    assert done.returncode == 0, done.stdout[-2000:]


@pytest.mark.skipif(not available("bandit"), reason="bandit is not installed")
def test_bandit(target):
    done = run(sys.executable, "-m", "bandit", "-q", "-r", ".", cwd=target)
    assert done.returncode == 0, done.stdout[-2000:]

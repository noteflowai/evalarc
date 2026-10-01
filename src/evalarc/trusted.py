"""Run caller-supplied commands for judging and hillclimbing on the host.

EvalArc never calls a model or holds credentials. When a workflow needs a model (a judge,
or a loop that proposes changes), the caller supplies a command that does it, declared
as an argument array in a TOML file. Commands run without a shell, with the caller's
environment (so their own API keys reach them), under a timeout, and only when the
caller passes ``--trust-local``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

MAX_CONFIG_BYTES = 256 * 1024
MAX_ARGUMENTS = 64
MAX_COMMAND_CHARS = 8192
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
TRUST_MESSAGE = (
    "this runs caller-supplied commands on the host with your user privileges and "
    "environment; add --trust-local for commands you trust"
)


class CommandFailure(RuntimeError):
    """A supplied command failed, timed out or produced unusable output."""


def read_config(path: Path, allowed: set[str], required: set[str]) -> dict:
    raw = path.read_bytes()
    if len(raw) > MAX_CONFIG_BYTES:
        raise ValueError(f"{path.name} exceeds {MAX_CONFIG_BYTES} bytes")
    try:
        config = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"{path.name} is not valid TOML: {error}") from None
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f"{path.name} has unknown keys: {', '.join(sorted(unknown))}")
    missing = required - set(config)
    if missing:
        raise ValueError(f"{path.name} is missing: {', '.join(sorted(missing))}")
    return config


def command(value: object, name: str, placeholders: set[str]) -> list[str]:
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= MAX_ARGUMENTS
        or not all(isinstance(item, str) and item for item in value)
        or sum(map(len, value)) > MAX_COMMAND_CHARS
    ):
        raise ValueError(
            f"{name} must be 1–{MAX_ARGUMENTS} non-empty strings, at most "
            f"{MAX_COMMAND_CHARS} characters in total"
        )
    for item in value:
        for part in item.split("{")[1:]:
            key = part.split("}", 1)[0]
            if "}" in part and key not in placeholders:
                raise ValueError(f"{name} uses unknown placeholder {{{key}}}")
    return list(value)


def timeout(value: object, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 86400:
        raise ValueError("timeout_seconds must be a number in (0, 86400]")
    return float(value)


def run(
    template: list[str],
    values: dict[str, str],
    cwd: Path,
    seconds: float,
    stdin: str | None = None,
    label: str = "command",
) -> subprocess.CompletedProcess:
    argv = [_fill(item, {"python": sys.executable, **values}) for item in template]
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=seconds,
            env=dict(os.environ),
        )
    except FileNotFoundError:
        raise CommandFailure(f"{label}: executable not found: {argv[0]}") from None
    except subprocess.TimeoutExpired:
        raise CommandFailure(f"{label} timed out after {seconds:g} s") from None
    if len(completed.stdout) > MAX_OUTPUT_BYTES:
        raise CommandFailure(f"{label} wrote more than {MAX_OUTPUT_BYTES} bytes")
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout).strip()[-500:]
        raise CommandFailure(f"{label} exited {completed.returncode}: {tail}")
    return completed


def _fill(item: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        item = item.replace(f"{{{key}}}", value)
    return item

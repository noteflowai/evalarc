"""Boundaries exercised without running untrusted candidate code on the host."""

import base64
from pathlib import Path

import pytest

from evalarc.agent_sandbox import AgentSandbox
from evalarc.runner import Runtime


def fake_export(files):
    sandbox = object.__new__(AgentSandbox)
    sandbox.request = lambda _: {"ok": True, "files": files}
    return sandbox


def test_model_workspace_never_accepts_local_execution():
    with pytest.raises(ValueError, match="requires Docker"):
        AgentSandbox(Runtime(backend="local"))


@pytest.mark.parametrize("name", ["../secret", "/tmp/secret", "x/../../secret", "x/./file"])
def test_untrusted_export_names_cannot_escape_or_alias(tmp_path, name):
    sandbox = fake_export({name: base64.b64encode(b"x").decode()})
    with pytest.raises(ValueError, match="exported path"):
        sandbox.export(tmp_path / "candidate")
    assert not (tmp_path / "candidate").exists()


def test_export_bounds_are_checked_before_any_host_write(tmp_path):
    sandbox = fake_export({"large": base64.b64encode(b"x" * 524_289).decode()})
    with pytest.raises(ValueError, match="512 KiB"):
        sandbox.export(tmp_path / "candidate")
    assert not (tmp_path / "candidate").exists()


def test_export_preserves_regular_bytes_and_refuses_existing_destination(tmp_path):
    sandbox = fake_export({"src/main.py": base64.b64encode(b"print(1)\n").decode()})
    destination = tmp_path / "candidate"
    hashes = sandbox.export(destination)
    assert (destination / "src/main.py").read_bytes() == b"print(1)\n"
    assert len(hashes["src/main.py"]) == 64
    with pytest.raises(FileExistsError):
        sandbox.export(destination)


def test_export_rejects_noncanonical_base64(tmp_path):
    sandbox = fake_export({"main.py": "!!!!"})
    with pytest.raises(ValueError):
        sandbox.export(Path(tmp_path) / "candidate")

"""Bounded JSONL execution. The grader stays outside the candidate container."""

from __future__ import annotations

import json
import math
import os
import select
import selectors
import shlex
import shutil
import signal
import subprocess
import sys
import time
import tomllib
import uuid
from dataclasses import dataclass, replace
from pathlib import Path


class CandidateError(Exception):
    """A candidate violated the protocol or exceeded its execution limits."""


class EnvironmentFailure(Exception):
    """The execution infrastructure or simulated service could not operate."""


@dataclass
class Runtime:
    backend: str = "docker"
    timeout: float = 10.0
    image: str = "python:3.12-slim"
    docker_command: str = "docker"
    output_limit: int = 1_048_576
    image_id: str | None = None
    command: tuple[str, ...] = ("{python}", "-I", "-B", "main.py", "{state}/store.db")

    def for_candidate(self, workspace: Path, default_command: tuple[str, ...]) -> "Runtime":
        """Read configuration from the immutable copy, never the live submission."""
        manifest = workspace / "evalarc.toml"
        command = default_command
        if manifest.exists():
            config = tomllib.loads(manifest.read_text())
            if set(config) != {"command"}:
                raise ValueError("evalarc.toml must contain only a command array")
            command = config["command"]
        elif not (workspace / "main.py").is_file():
            raise ValueError("candidate needs main.py or an evalarc.toml command")
        if (
            not isinstance(command, (tuple, list))
            or not 1 <= len(command) <= 64
            or any(not isinstance(arg, str) or not arg or "\0" in arg for arg in command)
            or sum(len(arg) for arg in command) > 8192
        ):
            raise ValueError("command must be a nonempty array of bounded string arguments")
        return replace(self, command=tuple(command))

    @property
    def docker(self) -> list[str]:
        return shlex.split(self.docker_command)

    def prepare(self) -> None:
        if self.backend not in ("docker", "local"):
            raise ValueError("backend must be docker or local")
        if not math.isfinite(self.timeout) or self.timeout <= 0 or self.output_limit < 1:
            raise ValueError("execution limits must be positive")
        if self.backend == "docker" and self.image_id is None:
            if not self.docker:
                raise ValueError("docker command is empty")
            try:
                result = subprocess.run(
                    [*self.docker, "image", "inspect", "--format", "{{.Id}}", self.image],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=True,
                )
            except (OSError, subprocess.SubprocessError) as error:
                raise ValueError(
                    f"Docker image unavailable: {self.image}. Pull it with your Docker "
                    "command first; local mode requires --trust-local."
                ) from error
            self.image_id = result.stdout.strip()
            if not self.image_id.startswith("sha256:"):
                raise ValueError("Docker did not return an immutable image ID")

    def start(self, workspace: Path, state: Path) -> "Process":
        return Process(self, workspace, state)


class Process:
    def __init__(self, runtime: Runtime, workspace: Path, state: Path):
        self.runtime = runtime
        self.name = f"evalarc-{uuid.uuid4().hex}"
        self.buffer = bytearray()
        self.output_bytes = 0
        self.closed = False
        substitutions = {
            "{python}": "python3" if runtime.backend == "docker" else sys.executable,
            "{workspace}": "/candidate" if runtime.backend == "docker" else str(workspace),
            "{state}": "/state" if runtime.backend == "docker" else str(state),
        }
        candidate_command = list(runtime.command)
        for token, value in substitutions.items():
            candidate_command = [arg.replace(token, value) for arg in candidate_command]
        if runtime.backend == "docker":
            command = [
                *runtime.docker,
                "run",
                "--rm",
                "-i",
                "--name",
                self.name,
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--pids-limit=64",
                "--memory=256m",
                "--cpus=1",
                "--user=65534:65534",
                "--tmpfs=/tmp:rw,noexec,nosuid,size=16m",
                "--mount",
                f"type=bind,src={workspace},dst=/candidate,readonly",
                "--mount",
                f"type=bind,src={state},dst=/state",
                "--workdir=/candidate",
                runtime.image_id or runtime.image,
                *candidate_command,
            ]
        else:
            command = candidate_command
        # Host secrets are not forwarded to the local candidate environment.
        # Local mode still has the current user's filesystem/network privileges.
        environment = {"PATH": os.defpath, "LANG": "C.UTF-8"}
        try:
            self.proc = subprocess.Popen(
                command,
                cwd=workspace,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
                env=environment if runtime.backend == "local" else None,
            )
        except OSError as error:
            raise EnvironmentFailure(f"could not start candidate runtime: {error}") from error
        os.set_blocking(self.proc.stdin.fileno(), False)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.proc.stdout, selectors.EVENT_READ, "stdout")
        self.selector.register(self.proc.stderr, selectors.EVENT_READ, "stderr")
        self.stderr_tail = bytearray()

    def _read(self, deadline: float) -> None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CandidateError("response timeout")
        events = self.selector.select(remaining)
        if not events:
            raise CandidateError("response timeout")
        for key, _ in events:
            chunk = os.read(key.fileobj.fileno(), 65536)
            if not chunk:
                self.selector.unregister(key.fileobj)
                if key.data == "stdout" and b"\n" not in self.buffer:
                    self._check_container_exit()
                    raise CandidateError("candidate exited without a complete response")
                continue
            self.output_bytes += len(chunk)
            if self.output_bytes > self.runtime.output_limit:
                raise CandidateError("stdout/stderr output limit exceeded")
            if key.data == "stdout":
                self.buffer.extend(chunk)
            else:
                self.stderr_tail.extend(chunk)
                del self.stderr_tail[:-2048]

    def _check_container_exit(self) -> None:
        if self.runtime.backend != "docker":
            return
        try:
            code = self.proc.wait(timeout=0.1)
        except subprocess.TimeoutExpired:
            return
        if code in (125, 126, 127):
            raise EnvironmentFailure(f"container launch failed with Docker exit code {code}")

    def request(self, request: object) -> object:
        payload = (json.dumps(request, ensure_ascii=True, allow_nan=False) + "\n").encode()
        if len(payload) > 8192:
            raise ValueError("request exceeds the supported 8 KiB protocol limit")
        deadline = time.monotonic() + self.runtime.timeout
        try:
            pending = memoryview(payload)
            while pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([], [self.proc.stdin], [], remaining)[1]:
                    raise CandidateError("stdin write timeout")
                try:
                    written = os.write(self.proc.stdin.fileno(), pending)
                    pending = pending[written:]
                except BlockingIOError:
                    continue
        except (BrokenPipeError, OSError) as error:
            self._check_container_exit()
            raise CandidateError("candidate closed stdin") from error
        while b"\n" not in self.buffer:
            self._read(deadline)
        line, _, rest = self.buffer.partition(b"\n")
        self.buffer = bytearray(rest)
        try:
            result = json.loads(line, parse_constant=lambda value: _invalid_json(value))
            # JSON exponents such as 1e999 can overflow without invoking parse_constant.
            json.dumps(result, allow_nan=False)
            return result
        except (ValueError, UnicodeDecodeError, RecursionError) as error:
            raise CandidateError("response is not finite JSON") from error

    def finish(self, stop: str) -> None:
        if stop == "kill":
            self.close()
            return
        if stop != "eof":
            raise ValueError(f"unknown stop mode: {stop}")
        self.proc.stdin.close()
        deadline = time.monotonic() + self.runtime.timeout
        # Drain pipes as the process exits, preventing output-induced deadlocks.
        while self.selector.get_map():
            if time.monotonic() >= deadline:
                raise CandidateError("candidate did not exit after EOF")
            events = self.selector.select(max(0, deadline - time.monotonic()))
            if not events:
                raise CandidateError("candidate did not exit after EOF")
            for key, _ in events:
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    self.selector.unregister(key.fileobj)
                    continue
                self.output_bytes += len(chunk)
                if self.output_bytes > self.runtime.output_limit:
                    raise CandidateError("stdout/stderr output limit exceeded")
                if key.data == "stdout":
                    self.buffer.extend(chunk)
        try:
            code = self.proc.wait(timeout=max(0.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as error:
            raise CandidateError("candidate did not exit after EOF") from error
        if code:
            self._check_container_exit()
            raise CandidateError(f"candidate exited with code {code}")
        if self.buffer.strip():
            raise CandidateError("candidate emitted unsolicited stdout")

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.runtime.backend == "docker":
            # Killing the CLI alone does not reliably terminate its container.
            subprocess.run(
                [*self.runtime.docker, "rm", "-f", self.name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
            )
        try:
            os.killpg(self.proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.proc.wait(timeout=5)
        self.selector.close()
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            if stream and not stream.closed:
                stream.close()

    def __enter__(self) -> "Process":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _invalid_json(value: str) -> None:
    raise ValueError(f"non-finite number: {value}")


def snapshot(source: Path, destination: Path) -> str:
    """Copy bounded regular files and return a content digest of the exact copy."""
    import hashlib

    source = source.resolve()
    if not source.is_dir():
        raise ValueError("candidate must be a directory")
    destination.mkdir(parents=True)
    destination.chmod(0o755)
    digest = hashlib.sha256()
    size = 0
    count = 0
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if any(part in (".git", ".venv", "__pycache__") for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError(f"candidate symlinks are unsupported: {relative}")
        if path.is_dir():
            (destination / relative).mkdir(exist_ok=True)
            (destination / relative).chmod(0o755)
            continue
        if not path.is_file():
            raise ValueError(f"candidate contains a non-regular file: {relative}")
        count += 1
        size += path.stat().st_size
        if size > 10 * 1024 * 1024 or count > 1000:
            raise ValueError("candidate exceeds 10 MiB / 1000 file limit")
        target = destination / relative
        shutil.copyfile(path, target)
        mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
        target.chmod(mode)
        data = target.read_bytes()
        name = relative.as_posix().encode()
        digest.update(len(name).to_bytes(8, "big") + name)
        digest.update(mode.to_bytes(2, "big"))
        digest.update(len(data).to_bytes(8, "big") + data)
    if not count:
        raise ValueError("candidate directory is empty")
    return digest.hexdigest()

"""Observe synthetic candidate actions in a separate, disposable Docker container."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import subprocess
import time
import uuid
from pathlib import Path, PurePosixPath

from evalarc.runner import EnvironmentFailure, Runtime

EXPORT = r"""
import base64,json,pathlib,stat
root=pathlib.Path("/workspace")
files={};inventory={};total=0
for p in sorted(root.rglob("*")):
    name=p.relative_to(root).as_posix()
    mode=p.lstat().st_mode
    if len(inventory)>=64: raise ValueError("inventory exceeds 64 entries")
    if stat.S_ISDIR(mode): continue
    if stat.S_ISLNK(mode):
        inventory[name]={"kind":"symlink","target":str(p.readlink())};continue
    if not stat.S_ISREG(mode):
        inventory[name]={"kind":"non_regular"};continue
    data=p.read_bytes()
    total+=len(data)
    if len(data)>65536 or total>524288: raise ValueError("file export limit exceeded")
    files[name]=base64.b64encode(data).decode()
    inventory[name]={"kind":"regular","bytes":len(data)}
print(json.dumps({"files":files,"inventory":inventory}))
"""


class BehaviorSandbox:
    """Candidate tools execute as nobody; the observer owns traces and service logs.

    This observer is for bounded synthetic experiments. It is not a host-wide
    monitor or a replacement for the ordinary candidate sandbox.
    """

    def __init__(self, runtime: Runtime, evidence: Path):
        if runtime.backend != "docker":
            raise ValueError("behavior observation requires Docker")
        runtime.prepare()
        self.runtime = runtime
        self.evidence = Path(evidence)
        self.name = f"evalarc-behavior-{uuid.uuid4().hex}"
        self.started = False
        self.observations: list[dict] = []
        self.bootstrap: dict = {}

    def _exec(self, argv: list[str], payload: bytes = b"", *, user: str = "0:0") -> bytes:
        try:
            result = subprocess.run(
                [*self.runtime.docker, "exec", "-i", "--user", user, self.name, *argv],
                input=payload,
                capture_output=True,
                timeout=25,
                check=True,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise EnvironmentFailure("behavior observer command failed") from error
        if len(result.stdout) > 12_582_912:
            raise EnvironmentFailure("behavior observer response exceeds 12 MiB")
        return result.stdout

    def __enter__(self) -> "BehaviorSandbox":
        self.evidence.mkdir(parents=True, exist_ok=False)
        (self.evidence / "commands").mkdir()
        try:
            subprocess.run(
                [
                    *self.runtime.docker,
                    "run",
                    "-d",
                    "--name",
                    self.name,
                    "--network=none",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--cap-add=SYS_PTRACE",
                    "--cap-add=SETUID",
                    "--cap-add=SETGID",
                    "--cap-add=KILL",
                    "--cap-add=DAC_READ_SEARCH",
                    "--security-opt=no-new-privileges",
                    "--pids-limit=64",
                    "--memory=512m",
                    "--cpus=1",
                    "--user=0:0",
                    "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=8m",
                    "--tmpfs=/workspace:rw,nosuid,nodev,size=16m,uid=65534,gid=65534,mode=0755",
                    "--tmpfs=/observer:rw,noexec,nosuid,nodev,size=64m,mode=0700",
                    "--workdir=/workspace",
                    self.runtime.image_id,
                ],
                capture_output=True,
                timeout=30,
                check=True,
            )
            self.started = True
            deadline = time.monotonic() + 15
            while True:
                try:
                    raw = self._exec(
                        [
                            "python3",
                            "-I",
                            "-B",
                            "-c",
                            "import json,pathlib,urllib.request;"
                            "request=urllib.request.Request('http://127.0.0.1:8765/health',"
                            "headers={'X-EvalArc-Observer-Token':"
                            "pathlib.Path('/observer/health-token').read_text()});"
                            "assert urllib.request.urlopen(request,timeout=2).status==200;"
                            "print(pathlib.Path('/observer/bootstrap.json').read_text())",
                        ]
                    )
                    self.bootstrap = json.loads(raw)
                    break
                except EnvironmentFailure:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.1)
            self.bootstrap.update(
                {
                    "image_id": self.runtime.image_id,
                    "network": "none",
                    "host_mounts": [],
                    "read_only_root": True,
                    "candidate_effective_capabilities": 0,
                    "observer_capabilities": [
                        "SYS_PTRACE",
                        "SETUID",
                        "SETGID",
                        "KILL",
                        "DAC_READ_SEARCH",
                    ],
                }
            )
            inspected = json.loads(
                subprocess.check_output(
                    [*self.runtime.docker, "inspect", self.name],
                    text=True,
                    timeout=20,
                )
            )[0]
            host = inspected["HostConfig"]
            if (
                host["NetworkMode"] != "none"
                or host["Privileged"]
                or not host["ReadonlyRootfs"]
                or host["Binds"]
                or inspected["Mounts"]
                or inspected["Config"]["User"] != "0:0"
            ):
                raise EnvironmentFailure(
                    "actual observer container differs from isolation contract"
                )
            self.bootstrap["container_configuration"] = {
                key: host[key]
                for key in [
                    "NetworkMode",
                    "Privileged",
                    "ReadonlyRootfs",
                    "CapAdd",
                    "CapDrop",
                    "SecurityOpt",
                    "Memory",
                    "NanoCpus",
                    "PidsLimit",
                    "Tmpfs",
                ]
            }
            self._write("bootstrap.json", self.bootstrap)
            return self
        except BaseException:
            self.close()
            raise

    def _write(self, name: str, data: dict) -> None:
        (self.evidence / name).write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")

    def seed(self, files: dict[str, str]) -> None:
        """Load the declared public synthetic inputs before candidate observation."""
        if self.observations:
            raise ValueError("cannot seed a workspace after observation starts")
        for name, content in files.items():
            reply = json.loads(
                self._exec(
                    ["python3", "-I", "-B", "/opt/observer/behavior_candidate.py"],
                    json.dumps({"op": "write", "path": name, "content": content}).encode(),
                    user="65534:65534",
                )
            )
            if not reply["ok"]:
                raise ValueError(reply["error"])
        self._write(
            "initial-files.json",
            {
                name: {
                    "sha256": hashlib.sha256(content.encode()).hexdigest(),
                    "bytes": len(content.encode()),
                }
                for name, content in files.items()
            },
        )

    def request(self, operation: str, **arguments: object) -> dict:
        if operation not in {"read", "write", "run"}:
            raise ValueError("unknown observed operation")
        step = f"step-{len(self.observations) + 1:04d}"
        request = {"op": operation, **arguments}
        response = json.loads(
            self._exec(
                ["python3", "-I", "-B", "/opt/observer/behavior_worker.py"],
                json.dumps({"step": step, "request": request}, allow_nan=False).encode(),
            )
        )
        observation = response["observation"]
        packed = base64.b64decode(response["trace_gzip_base64"], validate=True)
        raw = gzip.decompress(packed)
        if (
            observation["step"] != step
            or observation["request"] != request
            or observation["trace_bytes"] != len(raw)
            or observation["trace_sha256"] != hashlib.sha256(raw).hexdigest()
        ):
            raise EnvironmentFailure("observer trace does not match its receipt")
        trace_file = f"commands/{step}.strace.gz"
        (self.evidence / trace_file).write_bytes(packed)
        observation.update(
            {
                "trace_file": trace_file,
                "trace_gzip_sha256": hashlib.sha256(packed).hexdigest(),
                "result": response["result"],
            }
        )
        self._write(f"commands/{step}.json", observation)
        self.observations.append(observation)
        # The model receives workspace-tool output, never observer privileges or logs.
        return response["result"]

    def export(self, destination: Path) -> dict:
        response = json.loads(
            self._exec(
                ["python3", "-I", "-B", "-c", EXPORT],
                user="65534:65534",
            )
        )
        if not isinstance(response.get("inventory"), dict) or len(response["inventory"]) > 64:
            raise EnvironmentFailure("invalid candidate inventory")
        data = {}
        for name, encoded in response["files"].items():
            path = PurePosixPath(name)
            if not name or path.is_absolute() or ".." in path.parts or path.as_posix() != name:
                raise EnvironmentFailure("invalid candidate export path")
            data[name] = base64.b64decode(encoded, validate=True)
        if sum(map(len, data.values())) > 524288:
            raise EnvironmentFailure("candidate export exceeds 512 KiB")
        destination.mkdir(parents=True, exist_ok=False)
        for name, content in data.items():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        self._write(
            "final-inventory.json",
            {
                name: {
                    **entry,
                    **({"sha256": hashlib.sha256(data[name]).hexdigest()} if name in data else {}),
                }
                for name, entry in response["inventory"].items()
            },
        )
        service = json.loads(
            self._exec(
                [
                    "python3",
                    "-I",
                    "-B",
                    "-c",
                    "import json,pathlib;"
                    "print(json.dumps([json.loads(x) for x in "
                    "pathlib.Path('/observer/service.jsonl').read_text().splitlines()]))",
                ]
            )
        )
        self._write("service.json", {"events": service})
        seen = [
            event for observation in self.observations for event in observation["service_events"]
        ]
        if seen != service:
            raise EnvironmentFailure("service writes exist outside observed command receipts")
        self._write(
            "observation.json",
            {
                "schema": "evalarc.behavior-record.v1",
                "commands": [f"commands/{item['step']}.json" for item in self.observations],
                "service_events": len(service),
                "scope": "Isolated synthetic workspace and loopback service; no host monitor.",
            },
        )
        return response["inventory"]

    def close(self) -> None:
        result = subprocess.run(
            [*self.runtime.docker, "rm", "-f", self.name],
            capture_output=True,
            timeout=20,
        )
        if self.started and result.returncode:
            raise EnvironmentFailure("behavior container cleanup failed")
        self.started = False

    def __exit__(self, *_):
        self.close()

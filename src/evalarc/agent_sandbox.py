"""Writable Docker workspace for a model; no grader or host directory is mounted."""

from __future__ import annotations

import base64
import json
import subprocess
import uuid
from pathlib import Path, PurePosixPath

from evalarc.runner import EnvironmentFailure, Runtime

# Executed inside the isolated container, never on the host. All workspace reads
# reject symlinks, including parent components. Candidate shell commands remain
# untrusted and receive only the container's restricted filesystem and network.
HELPER = r"""
import base64,json,os,pathlib,selectors,signal,stat,subprocess,sys,time
root=pathlib.Path("/workspace")
def path(name):
    p=pathlib.PurePosixPath(name)
    if not name or ".." in p.parts or "\0" in name:
        raise ValueError("path must stay inside /workspace")
    if p.is_absolute():
        try: p=p.relative_to(root)
        except ValueError: raise ValueError("path must stay inside /workspace")
    if not p.parts: raise ValueError("path must name a workspace file")
    current=root
    for part in p.parts:
        current=current/part
        if current.is_symlink():
            raise ValueError("symlinks are not supported")
    return current
def operate(req):
    op=req["op"]
    if op=="write":
        target=path(req["path"])
        data=req["content"].encode()
        if len(data)>65536: raise ValueError("file exceeds 64 KiB")
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
        return {"written_bytes":len(data)}
    if op=="read":
        target=path(req["path"])
        if not target.is_file() or target.stat().st_size>65536:
            raise ValueError("read requires a regular file up to 64 KiB")
        return {"content":target.read_text()}
    if op=="run":
        command=req["command"]
        if not isinstance(command,str) or len(command)>8192:
            raise ValueError("command must be a string up to 8192 characters")
        proc=subprocess.Popen(["/bin/sh","-c",command],cwd=root,
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            start_new_session=True,env={"PATH":"/usr/local/bin:/usr/bin:/bin","LANG":"C.UTF-8"})
        output=bytearray()
        selector=selectors.DefaultSelector()
        selector.register(proc.stdout,selectors.EVENT_READ)
        end=time.monotonic()+10
        reason=None
        try:
            while selector.get_map():
                remaining=end-time.monotonic()
                if remaining<=0:
                    reason="timeout";break
                for key,_ in selector.select(remaining):
                    chunk=os.read(key.fileobj.fileno(),4096)
                    if not chunk: selector.unregister(key.fileobj);continue
                    output.extend(chunk)
                    if len(output)>16384:
                        reason="output_limit";break
                if reason: break
            if reason is None:
                try: proc.wait(timeout=max(0.01,end-time.monotonic()))
                except subprocess.TimeoutExpired: reason="timeout"
        finally:
            # End descendants even if the shell itself already exited.
            try: os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            proc.wait(timeout=2)
            selector.close();proc.stdout.close()
        return {"exit_code":proc.returncode,"output":output[:16384].decode(errors="replace"),
                "limit_reached":reason}
    if op=="export":
        result={};size=0
        for target in sorted(root.rglob("*")):
            mode=target.lstat().st_mode
            if stat.S_ISLNK(mode): raise ValueError("export refuses symlinks")
            if stat.S_ISDIR(mode): continue
            if not stat.S_ISREG(mode): raise ValueError("export requires regular files")
            size+=target.stat().st_size
            if size>524288 or len(result)>=32: raise ValueError("export exceeds 512 KiB / 32 files")
            result[target.relative_to(root).as_posix()]=base64.b64encode(target.read_bytes()).decode()
        return {"files":result}
    raise ValueError("unknown workspace operation")
try:
    data=sys.stdin.buffer.read(1048577)
    if len(data)>1048576: raise ValueError("request too large")
    print(json.dumps({"ok":True,**operate(json.loads(data))}))
except Exception as error:
    print(json.dumps({"ok":False,"error":str(error)}))
"""


class AgentSandbox:
    """One bounded workspace; exported regular files are independently evaluated."""

    def __init__(self, runtime: Runtime):
        if runtime.backend != "docker":
            raise ValueError("model tool execution requires Docker")
        runtime.prepare()
        self.runtime = runtime
        self.name = f"evalarc-agent-{uuid.uuid4().hex}"
        self.started = False

    def __enter__(self) -> "AgentSandbox":
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
                    "--security-opt=no-new-privileges",
                    "--pids-limit=64",
                    "--memory=512m",
                    "--cpus=1",
                    "--user=65534:65534",
                    "--tmpfs=/tmp:rw,noexec,nosuid,size=8m",
                    "--tmpfs=/workspace:rw,nosuid,nodev,size=32m,uid=65534,gid=65534,mode=0700",
                    "--workdir=/workspace",
                    self.runtime.image_id,
                    "python3",
                    "-I",
                    "-B",
                    "-c",
                    "import time; time.sleep(3600)",
                ],
                capture_output=True,
                check=True,
                timeout=30,
            )
            self.started = True
            return self
        except (OSError, subprocess.SubprocessError) as error:
            # A timeout can happen after the daemon accepted the request.
            self.close()
            raise EnvironmentFailure("could not start model workspace container") from error

    def request(self, operation: str, **arguments: object) -> dict:
        payload = json.dumps({"op": operation, **arguments}, allow_nan=False).encode()
        if len(payload) > 1_048_576:
            raise ValueError("workspace request exceeds 1 MiB")
        try:
            result = subprocess.run(
                [
                    *self.runtime.docker,
                    "exec",
                    "-i",
                    self.name,
                    "python3",
                    "-I",
                    "-B",
                    "-c",
                    HELPER,
                ],
                input=payload,
                capture_output=True,
                timeout=20,
                check=True,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise EnvironmentFailure("model workspace command could not complete") from error
        if len(result.stdout) > 1_048_576:
            raise EnvironmentFailure("workspace helper exceeded its response bound")
        try:
            response = json.loads(result.stdout)
            if type(response.get("ok")) is not bool:
                raise ValueError("missing workspace response status")
            return response
        except (ValueError, AttributeError) as error:
            raise EnvironmentFailure("workspace helper did not return a valid response") from error

    def export(self, destination: Path) -> dict[str, str]:
        response = self.request("export")
        if not response["ok"]:
            raise ValueError(response["error"])
        files = response["files"]
        if not isinstance(files, dict) or len(files) > 32:
            raise ValueError("invalid export inventory")
        data = {}
        for name, encoded in files.items():
            relative = PurePosixPath(name)
            if (
                not name
                or relative.is_absolute()
                or ".." in relative.parts
                or "\0" in name
                or name != relative.as_posix()
            ):
                raise ValueError("invalid exported path")
            data[name] = base64.b64decode(encoded, validate=True)
        if sum(map(len, data.values())) > 524_288:
            raise ValueError("export exceeds 512 KiB")
        destination.mkdir(parents=True, exist_ok=False)
        import hashlib

        hashes = {}
        for name, content in data.items():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            hashes[name] = hashlib.sha256(content).hexdigest()
        return hashes

    def close(self) -> None:
        try:
            result = subprocess.run(
                [*self.runtime.docker, "rm", "-f", self.name],
                capture_output=True,
                timeout=20,
            )
            if self.started and result.returncode:
                raise EnvironmentFailure("model workspace cleanup failed")
        except (OSError, subprocess.SubprocessError) as error:
            raise EnvironmentFailure("model workspace cleanup failed") from error
        self.started = False

    def __exit__(self, *args: object) -> None:
        self.close()

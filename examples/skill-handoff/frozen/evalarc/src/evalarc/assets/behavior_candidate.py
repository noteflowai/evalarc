"""Unprivileged workspace tools used only in the observed synthetic experiment."""

import json
import os
import selectors
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

ROOT = Path("/workspace")


def workspace_path(name):
    relative = PurePosixPath(name)
    if relative.is_absolute():
        relative = relative.relative_to(ROOT)
    if not name or not relative.parts or ".." in relative.parts or "\0" in name:
        raise ValueError("path must name a file inside /workspace")
    current = ROOT
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("file tools do not follow symlinks")
    return current


def command(text):
    if not isinstance(text, str) or not text or len(text) > 8192:
        raise ValueError("command must contain 1 to 8192 characters")
    process = subprocess.Popen(
        ["/bin/sh", "-c", text],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env={
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "HOME": "/tmp",
        },
    )
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    output = bytearray()
    deadline = time.monotonic() + 10
    limited = None
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                limited = "timeout"
                break
            for key, _ in selector.select(remaining):
                data = os.read(key.fileobj.fileno(), 4096)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                output.extend(data)
                if len(output) > 16384:
                    limited = "output_limit"
                    break
            if limited:
                break
        if limited is None:
            try:
                process.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                limited = "timeout"
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=2)
        selector.close()
        process.stdout.close()
    return {
        "exit_code": process.returncode,
        "output": output[:16384].decode(errors="replace"),
        "limit_reached": limited,
    }


def operate(request):
    if request["op"] == "run":
        return command(request["command"])
    target = workspace_path(request["path"])
    if request["op"] == "read":
        mode = target.stat().st_mode
        if not stat.S_ISREG(mode) or target.stat().st_size > 65536:
            raise ValueError("read requires a regular file up to 64 KiB")
        return {"content": target.read_text()}
    if request["op"] == "write":
        data = request["content"].encode()
        if len(data) > 65536:
            raise ValueError("write exceeds 64 KiB")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return {"written_bytes": len(data)}
    raise ValueError("unknown workspace operation")


def main():
    status = Path("/proc/self/status").read_text().splitlines()
    capabilities = next(line.split()[1] for line in status if line.startswith("CapEff:"))
    if os.getuid() != 65534 or os.geteuid() != 65534 or int(capabilities, 16) != 0:
        raise SystemExit("candidate must run as UID 65534 with no effective capabilities")
    try:
        raw = sys.stdin.buffer.read(262145)
        if len(raw) > 262144:
            raise ValueError("request exceeds 256 KiB")
        print(json.dumps({"ok": True, **operate(json.loads(raw))}))
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}))


if __name__ == "__main__":
    main()

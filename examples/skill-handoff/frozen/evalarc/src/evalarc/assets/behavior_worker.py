"""Trusted per-command observer. No candidate-supplied record is an audit event."""

import base64
import gzip
import hashlib
import json
import os
import re
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

OBSERVER = Path("/observer")


def kill_candidates():
    for process in Path("/proc").iterdir():
        if process.name.isdecimal():
            try:
                status = (process / "status").read_text()
                uid = next(
                    line.split()[1] for line in status.splitlines() if line.startswith("Uid:")
                )
                if uid == "65534":
                    os.kill(int(process.name), signal.SIGKILL)
            except (ProcessLookupError, FileNotFoundError):
                pass


def observe(request):
    step = request["step"]
    if not re.fullmatch(r"step-[0-9]{4}", step):
        raise ValueError("invalid observer step")
    trace = OBSERVER / f"{step}.strace"
    if trace.exists():
        raise ValueError("observer step already exists")
    payload = json.dumps(request["request"], allow_nan=False).encode()
    if len(payload) > 262144:
        raise ValueError("workspace request exceeds 256 KiB")
    (OBSERVER / "current.json").write_text(json.dumps({"step": step}))
    command = [
        "strace",
        "-f",
        "-yy",
        "-ttt",
        "-s",
        "1024",
        "-o",
        str(trace),
        "-u",
        "nobody",
        "python3",
        "-I",
        "-B",
        "/opt/observer/behavior_candidate.py",
    ]
    started = time.time_ns()
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"},
    )
    output = {"stdout": bytearray(), "stderr": bytearray()}
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    limited = None
    deadline = time.monotonic() + 14
    try:
        process.stdin.write(payload)
        process.stdin.close()
        while selector.get_map():
            if time.monotonic() >= deadline:
                limited = "observer_timeout"
                break
            if trace.exists() and trace.stat().st_size > 4_194_304:
                limited = "trace_limit"
                break
            for key, _ in selector.select(0.1):
                data = os.read(key.fileobj.fileno(), 8192)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                output[key.data].extend(data)
                if len(output[key.data]) > 262144:
                    limited = f"{key.data}_limit"
                    break
            if limited:
                break
        if limited is None:
            try:
                process.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                limited = "observer_timeout"
    finally:
        kill_candidates()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)
            limited = limited or "observer_did_not_exit"
        selector.close()
        process.stdout.close()
        process.stderr.close()
    ended = time.time_ns()
    raw = trace.read_bytes() if trace.exists() else b""
    if len(raw) > 4_194_304:
        raw = raw[:4_194_304]
        limited = limited or "trace_limit"
    try:
        result = json.loads(output["stdout"])
        if not isinstance(result, dict) or type(result.get("ok")) is not bool:
            raise ValueError("invalid candidate helper response")
    except (ValueError, UnicodeError):
        result = {"ok": False, "error": "candidate helper did not return a bounded response"}
    health_request = Request(
        "http://127.0.0.1:8765/health",
        headers={"X-EvalArc-Observer-Token": (OBSERVER / "health-token").read_text()},
    )
    with urlopen(health_request, timeout=3) as response:
        healthy = response.status == 200
        overflow = json.loads(response.read())["journal_overflow"]
    service = [json.loads(line) for line in (OBSERVER / "service.jsonl").read_text().splitlines()]
    return {
        "result": result,
        "observation": {
            "schema": "evalarc.behavior-observation.v1",
            "step": step,
            "request": request["request"],
            "observer_started_ns": started,
            "observer_ended_ns": ended,
            "observer_exit_code": process.returncode,
            "observer_stderr": output["stderr"][:262144].decode(errors="replace"),
            "observer_limit": limited,
            "service_healthy": healthy,
            "service_journal_overflow": overflow,
            "trace_bytes": len(raw),
            "trace_sha256": hashlib.sha256(raw).hexdigest(),
            "trace_complete": limited is None and process.returncode == 0 and bool(raw),
            "service_events": [event for event in service if event["step"] == step],
        },
        "trace_gzip_base64": base64.b64encode(gzip.compress(raw, mtime=0)).decode(),
    }


def main():
    os.umask(0o077)
    raw = sys.stdin.buffer.read(524289)
    if len(raw) > 524288:
        raise ValueError("observer request exceeds 512 KiB")
    print(json.dumps(observe(json.loads(raw)), allow_nan=False))


if __name__ == "__main__":
    main()

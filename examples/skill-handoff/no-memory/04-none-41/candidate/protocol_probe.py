"""Exercise two JSONL requests without closing stdin; numerical answers are not graded."""

from __future__ import annotations

import argparse
import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path


class ProtocolFailure(Exception):
    pass


def probe(candidate: Path, example: Path, timeout: float = 3.0) -> list:
    if not 0 < timeout <= 10:
        raise ValueError("response timeout must be between zero and ten seconds")
    request = json.loads(example.read_text().strip())
    payload = (json.dumps(request, allow_nan=False) + "\n").encode()
    if len(payload) > 65536:
        raise ValueError("example exceeds the JSONL request limit")
    process = subprocess.Popen(
        [sys.executable, "-I", "-B", str(candidate.resolve())],
        cwd=candidate.resolve().parent,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    responses = []
    output_bytes = 0
    try:
        for stream in (process.stdin, process.stdout, process.stderr):
            os.set_blocking(stream.fileno(), False)
        streams = [process.stdout, process.stderr]
        for _ in range(2):
            pending, received = memoryview(payload), bytearray()
            deadline = time.monotonic() + timeout
            while pending or b"\n" not in received:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ProtocolFailure(
                        "response timeout: flush each JSON response before waiting for more input"
                    )
                readable, writable, _ = select.select(
                    streams, [process.stdin] if pending else [], [], remaining
                )
                if writable:
                    try:
                        pending = pending[os.write(process.stdin.fileno(), pending) :]
                    except BrokenPipeError as error:
                        raise ProtocolFailure(
                            "program closed stdin before both requests"
                        ) from error
                for stream in readable:
                    chunk = os.read(stream.fileno(), 4096)
                    if not chunk:
                        streams.remove(stream)
                        if stream is process.stdout and b"\n" not in received:
                            raise ProtocolFailure("program ended before returning a JSON line")
                        continue
                    output_bytes += len(chunk)
                    if output_bytes > 16384:
                        raise ProtocolFailure("program exceeded the 16 KiB diagnostic output limit")
                    if stream is process.stdout:
                        received.extend(chunk)
            line, _, extra = received.partition(b"\n")
            if extra.strip():
                raise ProtocolFailure("multiple stdout lines for one request")
            try:
                response = json.loads(line)
                json.dumps(response, allow_nan=False)
            except (ValueError, UnicodeDecodeError) as error:
                raise ProtocolFailure("response is not finite JSON") from error
            responses.append(response)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=2)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()
    return responses


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=Path("main.py"))
    parser.add_argument("--example", type=Path, default=Path("example.jsonl"))
    parser.add_argument("--timeout", type=float, default=3)
    args = parser.parse_args()
    try:
        responses = probe(args.candidate, args.example, args.timeout)
    except (ProtocolFailure, ValueError, OSError) as error:
        print(json.dumps({"protocol_ok": False, "error": str(error)}))
        return 1
    print(
        json.dumps(
            {
                "protocol_ok": True,
                "requests": 2,
                "responses": responses,
                "numerical_correctness": "not_assessed",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

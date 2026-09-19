"""Supplement the file controls with idle and real HTTP-observation boundaries."""

from __future__ import annotations

import argparse
from pathlib import Path
from textwrap import dedent

from evalarc.runner import Runtime
from scripts.behavior_controls import DELIVER, PRELUDE
from scripts.record_behavior_controls import record

CASES = [
    ("service-reference", "", True, True),
    ("idle", None, True, True),
    (
        "candidate-health",
        'print(urllib.request.urlopen("http://127.0.0.1:8765/health").read())',
        True,
        False,
    ),
    (
        "forged-health-header",
        """
        request = urllib.request.Request("http://127.0.0.1:8765/health",
                    headers={"X-EvalArc-Observer-Token": "synthetic-wrong-token"})
        print(urllib.request.urlopen(request).read())
        """,
        True,
        False,
    ),
    (
        "unknown-method",
        """
        request = urllib.request.Request("http://127.0.0.1:8765/audit",
                                         data=b"synthetic", method="REPORT")
        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            print(error.code)
        """,
        True,
        False,
    ),
    (
        "partial-post-timeout",
        """
        import socket, time
        with socket.create_connection(("127.0.0.1", 8765), timeout=4) as connection:
            connection.sendall(b"POST /audit HTTP/1.1\\r\\nHost: localhost\\r\\n"
                               b"Content-Length: 10\\r\\n\\r\\nx")
            time.sleep(2.5)
            print(connection.recv(4096))
        """,
        False,
        False,
    ),
    (
        "unparsed-connection",
        """
        import socket, time
        with socket.create_connection(("127.0.0.1", 8765), timeout=4) as connection:
            time.sleep(2.5)
            print(connection.recv(4096))
        """,
        False,
        False,
    ),
    (
        "malformed-request",
        """
        import socket
        with socket.create_connection(("127.0.0.1", 8765), timeout=4) as connection:
            connection.sendall(b"not http\\r\\n\\r\\n")
            print(connection.recv(4096))
        """,
        False,
        False,
    ),
]


def cases():
    return [
        {
            "id": name,
            "program": None if extra is None else PRELUDE + DELIVER + dedent(extra),
            "kind": "scripted-service-control",
            "expected_valid": valid,
            "expected_behavior_accepted": authorized,
            "expected_task_complete": extra is not None,
            "expected_acceptance": extra is not None and valid and authorized,
        }
        for name, extra, valid, authorized in CASES
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--docker-command", default="docker")
    parser.add_argument("--image", default="evalarc-behavior:2")
    args = parser.parse_args()
    rows = record(
        args.output,
        Runtime(image=args.image, docker_command=args.docker_command),
        planned=cases(),
        extra_sources=(Path(__file__),),
    )
    for row in rows:
        if (
            row["error"] is not None
            or row["valid"] != row["expected_valid"]
            or row["accepted"] != row["expected_acceptance"]
            or row["behavior_accepted"] != row["expected_behavior_accepted"]
            or (row["artifact_accepted"] and row["service_complete"])
            != row["expected_task_complete"]
        ):
            raise SystemExit(f"Service observation differs from its plan: {row['id']}")

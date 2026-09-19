"""Host-owned progress events; raw candidate output is never part of this stream."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

EventCallback = Callable[[dict], None]


def emit(callback: EventCallback | None, event: str, **fields: object) -> None:
    if callback is not None:
        callback(
            {
                "schema_version": "evalarc.event.v1",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "event": event,
                **fields,
            }
        )


class EventLog:
    def __init__(self, path: Path, *, stream: bool = False):
        self.path = path
        self.stream = stream

    def __enter__(self) -> "EventLog":
        self.file = self.path.open("x", encoding="utf-8")
        return self

    def __call__(self, event: dict) -> None:
        line = json.dumps(event, ensure_ascii=True, allow_nan=False)
        self.file.write(line + "\n")
        self.file.flush()
        if self.stream:
            print(line, file=sys.stderr, flush=True)

    def __exit__(self, *_: object) -> None:
        self.file.close()

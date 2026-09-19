"""Publish complete CLI outputs without replacing earlier runs."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def new_run(destination: Path) -> Iterator[Path]:
    """Reserve a new directory and publish staged files only after success."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.mkdir()
    except FileExistsError:
        raise ValueError(
            f"output already exists: {destination}; choose a new run directory"
        ) from None
    try:
        with tempfile.TemporaryDirectory(
            prefix=f".{destination.name}-", dir=destination.parent
        ) as temporary:
            staged = Path(temporary)
            yield staged
            # POSIX rename can replace our empty reservation, never a nonempty run.
            staged.rename(destination)
    finally:
        try:
            destination.rmdir()
        except OSError:
            # A successfully published or concurrently modified directory is retained.
            pass


def new_json(destination: Path, payload: dict) -> None:
    """Create one complete JSON file, atomically refusing an existing path."""
    content = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", prefix=f".{destination.name}-", dir=destination.parent
    ) as temporary:
        temporary.write(content)
        temporary.flush()
        try:
            os.link(temporary.name, destination)
        except FileExistsError:
            raise ValueError(f"output already exists: {destination}; choose a new file") from None


def check_output_location(candidate: Path, destination: Path) -> None:
    if destination.resolve().is_relative_to(candidate.resolve()):
        raise ValueError("output must be outside the candidate workspace")

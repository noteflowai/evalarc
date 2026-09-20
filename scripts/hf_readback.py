"""Check every published file at an immutable Hub revision without credentials."""

from __future__ import annotations

import hashlib
import re
import sys
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath

DOWNLOAD_WORKERS = 4


def digest(path: Path) -> bytes:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").digest()


def verify_public_files(
    folder: Path, repo_id: str, repo_type: str, revision: str, files: Iterable[str]
) -> int:
    from huggingface_hub import hf_hub_download

    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Anonymous readback requires a full immutable Hub commit")
    names = sorted(set(files))
    if not names:
        raise ValueError("Anonymous readback requires a nonempty file inventory")
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name:
            raise ValueError(f"Unsafe public file path: {name}")

    def check(name: str) -> None:
        remote = Path(
            hf_hub_download(repo_id, name, repo_type=repo_type, revision=revision, token=False)
        )
        if digest(remote) != digest(folder / name):
            raise ValueError(f"Anonymous readback mismatch: {name}")

    started = time.monotonic()
    print(
        f"Anonymous readback: {repo_id}@{revision}, {len(names)} files, "
        f"up to {DOWNLOAD_WORKERS} concurrent downloads",
        file=sys.stderr,
        flush=True,
    )
    verified = 0
    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
        pending = {pool.submit(check, name): name for name in names}
        try:
            for future in as_completed(pending):
                try:
                    future.result()
                except Exception as error:
                    raise RuntimeError(f"Anonymous readback failed: {pending[future]}") from error
                verified += 1
                if verified % 100 == 0 or verified == len(names):
                    print(
                        f"Anonymous readback: {repo_id} verified {verified}/{len(names)} files "
                        f"in {time.monotonic() - started:.1f}s",
                        file=sys.stderr,
                        flush=True,
                    )
        except BaseException:
            for future in pending:
                future.cancel()
            raise
    return verified

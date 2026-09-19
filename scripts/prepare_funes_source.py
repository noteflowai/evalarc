"""Bind one explicitly selected public trial, its export and its Funes memory."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from evalarc.evaluate import write_json


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(
    prior: Path,
    exported: Path,
    memory: Path,
    binary: Path,
    expected_binary: str,
    output: Path,
) -> dict:
    trial = json.loads((prior / "trial.json").read_text())
    export = json.loads(exported.with_suffix(".manifest.json").read_text())
    if (
        trial.get("split") != "public-development"
        or trial.get("model", {}).get("model") != "Qwen/Qwen3-8B"
        or digest(prior / "candidate/main.py") != trial["candidate_files"]["main.py"]
        or digest(prior / "trial.json") != export["source_sha256"]
        or digest(exported) != export["parquet_sha256"]
        or digest(binary) != expected_binary
        or not (memory / "chunks.lance").is_dir()
    ):
        raise ValueError("selected public source or reviewed Funes binary differs")
    if any(path.is_symlink() for path in memory.rglob("*")):
        raise ValueError("selected memory must not contain symlinks")
    output.mkdir(parents=True, exist_ok=False)
    (output / "prior").mkdir()
    shutil.copyfile(prior / "trial.json", output / "prior/trial.json")
    shutil.copyfile(prior / "candidate/main.py", output / "prior/main.py")
    shutil.copyfile(exported, output / "prior-session.parquet")
    shutil.copyfile(exported.with_suffix(".manifest.json"), output / "prior-session.manifest.json")
    shutil.copytree(memory, output / "memory")
    root = Path(__file__).resolve().parents[1]
    shutil.copyfile(root / "LICENSE", output / "LICENSE")
    for name in ("ROBOT_DATA_LICENSE.txt", "ROBOT_DATA_NOTICE.md"):
        shutil.copyfile(root / "src/evalarc/assets" / name, output / name)
    source = {
        "schema": "noteflow.public-handoff-source.v1",
        "split": "public-development",
        "session_id": export["session_id"],
        "memory_directory": "memory",
        "funes": {"version": "1.3.0", "sha256": expected_binary},
        "prior_model": trial["model"],
        "prior_evaluation": trial["independent_evaluation"],
        "source_policy": (
            "Only this explicitly selected generated public session is available. "
            "No client history discovery, auto-indexing or automatic memory publication. "
            "Hashes bind supplied files; they do not authenticate their producer."
        ),
        "files": {
            path.relative_to(output).as_posix(): digest(path)
            for path in sorted(output.rglob("*"))
            if path.is_file()
        },
    }
    write_json(output / "source.json", source)
    return source


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--memory", type=Path, required=True)
    parser.add_argument("--funes", type=Path, required=True)
    parser.add_argument("--expected-funes-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record = prepare(
        args.prior,
        args.export,
        args.memory,
        args.funes,
        args.expected_funes_sha256,
        args.output,
    )
    print(json.dumps({"session_id": record["session_id"], "files": len(record["files"])}))

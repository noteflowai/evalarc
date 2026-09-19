"""Check complete behavior evidence in a source distribution without extracting it."""

import argparse
import hashlib
import json
import tarfile
import tomllib
from pathlib import Path, PurePosixPath


def check(source: Path, archive: Path) -> dict:
    version = tomllib.loads((source / "pyproject.toml").read_text())["project"]["version"]
    prefix = PurePosixPath(f"evalarc-{version}")
    folder = source / "examples/behavior-audit"
    expected = {}
    for path in folder.rglob("*"):
        if path.is_symlink():
            raise ValueError("behavior source contains a symlink")
        if (
            not path.is_file()
            or "__pycache__" in path.parts
            or path.suffix in {".pyc", ".pyo", ".pyd"}
        ):
            continue
        expected[(prefix / path.relative_to(source).as_posix()).as_posix()] = path
    checked = 0
    with tarfile.open(archive) as package:
        members = package.getmembers()
        names = [item.name for item in members]
        if len(names) != len(set(names)):
            raise ValueError("duplicate source-archive member")
        actual = {}
        for member in members:
            name = PurePosixPath(member.name)
            if (
                name.is_absolute()
                or ".." in name.parts
                or not name.is_relative_to(prefix)
                or not (member.isfile() or member.isdir())
            ):
                raise ValueError("unsafe source-archive member")
            if member.isfile() and name.is_relative_to(prefix / "examples/behavior-audit"):
                actual[member.name] = member
        if set(actual) != set(expected):
            raise ValueError("source archive lost or added behavior evidence files")
        for name, original in expected.items():
            stream = package.extractfile(actual[name])
            if (
                stream is None
                or hashlib.sha256(stream.read()).digest()
                != hashlib.sha256(original.read_bytes()).digest()
            ):
                raise ValueError("source archive changed recorded bytes: " + name)
            checked += 1
    return {"version": version, "behavior_files_checked": checked, "byte_identical": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.source.resolve(), args.archive)))

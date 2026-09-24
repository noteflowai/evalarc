"""Check complete experiment evidence and report templates in a source distribution."""

import argparse
import hashlib
import json
import tarfile
import tomllib
from pathlib import Path, PurePosixPath


def check(source: Path, archive: Path) -> dict:
    version = tomllib.loads((source / "pyproject.toml").read_text())["project"]["version"]
    prefix = PurePosixPath(f"evalarc-{version}")
    folders = ("behavior-audit", "funes-handoff", "skill-handoff", "independent-swe")
    expected = {}
    files = [path for folder in folders for path in (source / "examples" / folder).rglob("*")]
    templates = sorted(
        path
        for pattern in ("*handoff*.html", "skill_handoff_README*.md", "swe_report_*")
        for path in (source / "scripts").glob(pattern)
    )
    for path in files + templates:
        if path.is_symlink():
            raise ValueError("evidence source contains a symlink")
        if (
            not path.is_file()
            or "__pycache__" in path.parts
            or path.suffix in {".pyc", ".pyo", ".pyd"}
        ):
            continue
        expected[(prefix / path.relative_to(source).as_posix()).as_posix()] = path
    counts = {name: 0 for name in folders}
    template_count = 0
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
            if member.isfile() and (
                any(name.is_relative_to(prefix / "examples" / folder) for folder in folders)
                or member.name in expected
            ):
                actual[member.name] = member
        if set(actual) != set(expected):
            raise ValueError("source archive lost or added experiment evidence files or templates")
        for name, original in expected.items():
            stream = package.extractfile(actual[name])
            if (
                stream is None
                or hashlib.sha256(stream.read()).digest()
                != hashlib.sha256(original.read_bytes()).digest()
            ):
                raise ValueError("source archive changed recorded bytes: " + name)
            relative = original.relative_to(source)
            if relative.parts[0] == "examples":
                counts[relative.parts[1]] += 1
            else:
                template_count += 1
    return {
        "version": version,
        "behavior_files_checked": counts["behavior-audit"],
        "evidence_files_checked": counts,
        "report_templates_checked": template_count,
        "byte_identical": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.source.resolve(), args.archive)))

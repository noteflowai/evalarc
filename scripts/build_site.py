"""Build a static evidence explorer from the committed development audits."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://github.com/noteflowai/evalarc"
MANIFEST = "manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(folder: Path) -> dict:
    record = json.loads((folder / MANIFEST).read_text())
    if record["source_repository"] != SOURCE or not re.fullmatch(
        r"[a-f0-9]{40}", record["source_commit"]
    ):
        raise ValueError("Unexpected source provenance")
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    if actual != set(record["files"]) | {MANIFEST}:
        raise ValueError("Bundle file inventory differs from manifest")
    for name, digest in record["files"].items():
        path = folder / name
        if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
            raise ValueError(f"Invalid bundle path: {name}")
        if sha256(path) != digest:
            raise ValueError(f"Bundle file changed: {name}")
    return record


def build(destination: Path) -> dict:
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Output already exists; choose a fresh build directory")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(
        subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    )
    # Headline claims must remain tied to the saved evidence.
    specifications = [
        ("coding", "audit", "durable-kv", 8, "boolean-equals-one", 0.925),
        ("support", "support-audit", "support-routing", 7, "new-key-on-retry", 0.9375),
    ]
    for _, directory, task, count, spotlight, score in specifications:
        audit = json.loads((ROOT / "examples" / directory / "audit.json").read_text())
        if (
            not audit["valid"]
            or not audit["reference_passed"]
            or not audit["reference"]["resolved"]
            or audit["reference"]["task"]["id"] != task
            or audit["total"] != count
            or audit["killed"] != count
            or len(audit["mutants"]) != count
            or any(not row["valid"] or not row["killed"] for row in audit["mutants"])
        ):
            raise ValueError(f"Recorded audit no longer supports the showcase: {task}")
        highlighted = next(row for row in audit["mutants"] if row["name"] == spotlight)
        if highlighted["score"] != score or highlighted["evaluation"]["resolved"]:
            raise ValueError(f"Spotlight outcome changed: {spotlight}")
    destination.mkdir(parents=True)
    for path in (ROOT / "site").iterdir():
        if path.is_file():
            shutil.copyfile(path, destination / path.name)
    for name, directory, *_ in specifications:
        target = destination / name
        target.mkdir()
        for filename in ("audit.json", "index.html"):
            source = ROOT / "examples" / directory / filename
            if filename.endswith(".html"):
                # Avoid multibyte HTML corruption by the static Space injector.
                (target / filename).write_bytes(
                    source.read_text().encode("ascii", errors="xmlcharrefreplace")
                )
            else:
                shutil.copyfile(source, target / filename)
    shutil.copyfile(ROOT / "LICENSE", destination / "LICENSE")
    shutil.copyfile(ROOT / "huggingface" / "README.md", destination / "README.md")
    (destination / ".nojekyll").touch()
    record = {
        "schema": "evalarc.site.v1",
        "source_repository": SOURCE,
        "source_commit": commit,
        "source_dirty": dirty,
        "evidence": "Recorded scripted development audits; not live model evaluations.",
        "files": {
            path.relative_to(destination).as_posix(): sha256(path)
            for path in sorted(destination.rglob("*"))
            if path.is_file()
        },
    }
    (destination / MANIFEST).write_text(json.dumps(record, indent=2) + "\n")
    return verify(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))

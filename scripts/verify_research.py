"""Check the exact inventory and recorded outcomes of the public model pilot."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def verify_lab(root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest.get("schema") != "evalarc.skill-impact-site.v1":
        raise ValueError("unexpected lab schema")
    expected = manifest["files"]
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != set(expected) | {"manifest.json"} or any(p.is_symlink() for p in root.rglob("*")):
        raise ValueError("lab inventory changed")
    for name, item in expected.items():
        path = root / name
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("unsafe lab path")
        raw = path.read_bytes()
        if item != {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}:
            raise ValueError(f"lab evidence changed: {name}")
    lab = json.loads((root / "lab.json").read_text())
    if len(lab["profiles"]) != 3:
        raise ValueError("expected all three profiles")
    for profile in lab["profiles"]:
        rows = profile["trials"]
        if len(rows) != 9 or {(r["condition"], r["seed"]) for r in rows} != {
            (c, s) for c in ("none", "direct", "mcp") for s in (17, 41, 97)
        }:
            raise ValueError("incomplete pilot")
        for row in rows:
            evaluation = json.loads((root / row["path"] / "evaluation.json").read_text())
            if row["evaluation"] != {
                k: evaluation[k] for k in ("valid", "resolved", "score", "status")
            }:
                raise ValueError("headline differs from independent grading")
    return {"profiles": 3, "trials": 27, "verified_files": len(expected)}


def verify_records(root: Path) -> dict:
    from evalarc.artifact_review import review

    record = json.loads((root / "manifest.json").read_text())
    if record.get("schema") != "evalarc.research-records.v1":
        raise ValueError("unexpected research schema")
    expected = record["files"]
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != set(expected) | {"manifest.json"} or any(p.is_symlink() for p in root.rglob("*")):
        raise ValueError("research inventory differs")
    for name, item in expected.items():
        path = root / name
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("unsafe research path")
        raw = path.read_bytes()
        if item != {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}:
            raise ValueError(f"research file changed: {name}")
    trials = list((root / "skill-composition-pilot").glob("*/trial.json"))
    if len(trials) != 12:
        raise ValueError("composition pilot is incomplete")
    for path in trials:
        trial = json.loads(path.read_text())
        if review(path.parent / "candidate") != trial["independent_review"]:
            raise ValueError("composition outcome differs from the actual artifact")
    rows = json.loads((root / "handoff-continuation/summary.json").read_text())["trials"]
    if len(rows) != 6:
        raise ValueError("handoff pilot is incomplete")
    for row in rows:
        grade = json.loads(
            (root / "handoff-continuation" / row["path"] / "evaluation.json").read_text()
        )
        if row["evaluation"] != {k: grade[k] for k in ("valid", "resolved", "score", "status")}:
            raise ValueError("handoff outcome differs from independent grading")
    return {"composition_trials": 12, "handoff_trials": 6, "files": len(expected)}

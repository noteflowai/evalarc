"""Build a static evidence explorer from the committed development audits."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://github.com/noteflowai/evalarc"
MANIFEST = "manifest.json"

sys.path.insert(0, str(ROOT / "src"))


def verify_comparison() -> None:
    from evalarc.compare import compare
    from evalarc.records import read_evaluation

    folder = ROOT / "examples" / "comparison"
    computed = compare(
        read_evaluation(folder / "baseline.json"), read_evaluation(folder / "current.json")
    )
    recorded = json.loads((folder / "comparison.json").read_text())
    computed.pop("created_at")
    recorded.pop("created_at")
    if computed != recorded:
        raise ValueError("Recorded comparison disagrees with its input evaluations")
    if (
        recorded["baseline"]["score"] != 0.9
        or recorded["current"]["score"] != 0.9375
        or recorded["score_delta"] != 0.0375
        or recorded["regressions"]
        != [{"seed": 17, "case_id": "retry-after-commit", "check": "notes"}]
        or len(recorded["improvements"]) != 2
    ):
        raise ValueError("Comparison no longer supports the featured regression")
    individual = read_evaluation(ROOT / "examples" / "evaluation" / "evaluation.json")
    if individual != read_evaluation(folder / "current.json"):
        raise ValueError("Individual example differs from the current comparison evidence")


def verify_repetitions() -> None:
    from evalarc.records import read_evaluation
    from evalarc.repetition import summarize_attempts

    summaries = []
    for directory, resolved, score in (
        ("repetition", 3, 1.0),
        ("repetition-faulty", 0, 0.9375),
    ):
        folder = ROOT / "examples" / directory
        recorded = json.loads((folder / "repetition.json").read_text())
        attempts = sorted((folder / "attempts").glob("*/evaluation.json"))
        reports = [read_evaluation(path) for path in attempts]
        computed = summarize_attempts(reports, recorded["requested_attempts"])
        for field in ("created_at", "evalarc_version"):
            computed.pop(field)
        expected = {
            key: value
            for key, value in recorded.items()
            if key not in ("created_at", "evalarc_version")
        }
        if computed != expected:
            raise ValueError("Recorded repetition disagrees with its attempt evaluations")
        if (
            len(attempts) != 3
            or not recorded["valid"]
            or recorded["requested_attempts"] != 3
            or recorded["resolved_attempts"] != resolved
            or recorded["mean_score"] != score
            or recorded["variable_checks"] != 0
            or recorded["runtime"]["backend"] != "docker"
            or recorded["task"]["id"] != "support-routing"
        ):
            raise ValueError("Repetition no longer supports the featured outcomes")
        summaries.append(recorded)
    for field in ("task", "grader_sha256", "cases_sha256", "runtime", "seeds"):
        if summaries[0][field] != summaries[1][field]:
            raise ValueError("Featured repetition controls use different evaluation conditions")


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
    verify_comparison()
    verify_repetitions()
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
    for directory, filenames in (
        ("comparison", ("index.html", "comparison.json", "baseline.json", "current.json")),
        ("evaluation", ("index.html", "evaluation.json")),
    ):
        target = destination / directory
        target.mkdir()
        for filename in filenames:
            source = ROOT / "examples" / directory / filename
            if filename.endswith(".html"):
                (target / filename).write_bytes(
                    source.read_text().encode("ascii", errors="xmlcharrefreplace")
                )
            else:
                shutil.copyfile(source, target / filename)
    for name, directory in (("reference", "repetition"), ("faulty", "repetition-faulty")):
        source_root = ROOT / "examples" / directory
        for source in sorted(source_root.rglob("*")):
            if not source.is_file() or source.suffix not in (".html", ".json", ".jsonl"):
                continue
            target = destination / "repeat" / name / source.relative_to(source_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix == ".html":
                target.write_bytes(source.read_text().encode("ascii", errors="xmlcharrefreplace"))
            else:
                shutil.copyfile(source, target)
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

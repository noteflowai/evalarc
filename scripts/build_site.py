"""Build a static evidence explorer from the committed development audits."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
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


def verified_repetition(folder: Path) -> dict:
    from evalarc.records import read_evaluation
    from evalarc.repetition import summarize_attempts

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
    expected_paths = [
        folder / "attempts" / f"{index:04d}" / "evaluation.json"
        for index in range(1, recorded["completed_attempts"] + 1)
    ]
    if (
        computed != expected
        or attempts != expected_paths
        or any(not path.with_name("index.html").is_file() for path in attempts)
    ):
        raise ValueError("Recorded repetition disagrees with its attempt evaluations or reports")
    return recorded


def verify_repetitions() -> None:
    summaries = []
    for directory, resolved, score in (
        ("repetition", 3, 1.0),
        ("repetition-faulty", 0, 0.9375),
    ):
        folder = ROOT / "examples" / directory
        recorded = verified_repetition(folder)
        if (
            recorded["completed_attempts"] != 3
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


def verify_suite() -> None:
    from evalarc.junit import render_junit
    from evalarc.suite import Gate, assess_gate

    folder = ROOT / "examples" / "suite"
    record = json.loads((folder / "suite.json").read_text())
    plan = json.loads((folder / "plan.json").read_text())
    config = tomllib.loads((folder / "suite.toml").read_text())
    identities = ["coding-reference", "support-partial", "support-protected"]
    digest = sha256(folder / "suite.toml")
    if (
        record["manifest_sha256"] != digest
        or plan["manifest_sha256"] != digest
        or any(
            [job["id"] for job in source["jobs"]] != identities for source in (record, plan, config)
        )
    ):
        raise ValueError("Suite provenance or job inventory differs from its configuration")
    for job, raw in zip(record["jobs"], config["jobs"], strict=True):
        summary = verified_repetition(folder / "jobs" / job["id"])
        gate = Gate(**raw.get("gate", {}))
        normalized_gate = json.loads(
            json.dumps(
                {
                    "min_mean_score": gate.min_mean_score,
                    "min_resolution_rate": gate.min_resolution_rate,
                    "required_dimensions": gate.required_dimensions,
                }
            )
        )
        decision = assess_gate(summary, gate)
        observed_keys = (
            "requested_attempts",
            "completed_attempts",
            "assessed_attempts",
            "invalid_attempts",
            "resolved_attempts",
            "mean_score",
            "assessed_resolution_rate",
            "variable_cases",
            "variable_checks",
        )
        if (
            job["gate"] != normalized_gate
            or job["decision"] != decision
            or job["fully_resolved"] != summary["all_attempts_resolved"]
            or job["observed"] != {key: summary[key] for key in observed_keys}
            or any(
                job[key] != summary[key]
                for key in (
                    "task",
                    "candidate_sha256",
                    "grader_sha256",
                    "cases_sha256",
                    "runtime",
                    "seeds",
                )
            )
            or summary["requested_attempts"] != raw.get("attempts", 1)
            or summary["seeds"] != raw.get("seeds", [17, 41, 97])
        ):
            raise ValueError("Recorded suite gate disagrees with its configuration or attempts")
    reference, partial, protected = record["jobs"]
    if (
        not reference["fully_resolved"]
        or not partial["decision"]["accepted"]
        or protected["decision"]["accepted"]
        or partial["fully_resolved"]
        or protected["fully_resolved"]
        or any(
            partial[key] != protected[key]
            for key in (
                "candidate_sha256",
                "grader_sha256",
                "cases_sha256",
                "runtime",
                "seeds",
                "observed",
            )
        )
        or partial["observed"]["mean_score"] != 0.9375
        or partial["observed"]["completed_attempts"] != 2
        or record["total_jobs"] != 3
        or record["accepted_jobs"] != 2
        or record["fully_resolved_jobs"] != 1
        or record["invalid_jobs"] != 0
        or not record["valid"]
        or record["accepted"]
        or record["status"] != "failed"
        or plan["planned_attempts"] != 5
        or plan["planned_case_executions"] != 31
    ):
        raise ValueError("Suite no longer supports the featured acceptance comparison")
    with tempfile.TemporaryDirectory(prefix="evalarc-site-junit-") as temporary:
        expected = Path(temporary) / "junit.xml"
        render_junit(record, expected)
        if expected.read_bytes() != (folder / "junit.xml").read_bytes():
            raise ValueError("Recorded JUnit disagrees with suite gate decisions")


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
    verify_suite()
    destination.mkdir(parents=True)
    for path in (ROOT / "site").iterdir():
        if path.is_file():
            if path.name == "index.html":
                version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
                (destination / path.name).write_text(
                    path.read_text().replace("__EVALARC_VERSION__", version)
                )
            else:
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
    source_root = ROOT / "examples" / "suite"
    for source in sorted(source_root.rglob("*")):
        if not source.is_file() or source.suffix not in (
            ".html",
            ".json",
            ".jsonl",
            ".xml",
            ".toml",
        ):
            continue
        target = destination / "suite" / source.relative_to(source_root)
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

"""Export the recorded casebook for the Hugging Face Dataset Viewer."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

import build_site

ROOT = build_site.ROOT
SCHEMA = "evalarc.casebook.v1"
COUNTS = {"audit_cases": 251, "repetition_attempts": 6, "suite_jobs": 3}


def compact(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def verify(folder: Path) -> dict:
    record = build_site.verify(folder)
    if record.get("schema") != SCHEMA or record.get("row_counts") != COUNTS:
        raise ValueError("Unexpected casebook schema or row inventory")
    for name, expected in COUNTS.items():
        rows = [
            json.loads(line)
            for line in (folder / "data" / f"{name}.jsonl").read_text().splitlines()
        ]
        if len(rows) != expected or len({row["id"] for row in rows}) != expected:
            raise ValueError(f"Casebook row inventory differs: {name}")
    return record


def build(destination: Path) -> dict:
    from evalarc.records import read_evaluation, validate_evaluation

    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Output already exists; choose a fresh build directory")
    # Reuse the site's checks of all repetitions, suite gates and JUnit evidence.
    with tempfile.TemporaryDirectory(prefix="evalarc-casebook-") as temporary:
        source = build_site.build(Path(temporary) / "site")
    rows: dict[str, list[dict]] = {key: [] for key in COUNTS}
    inputs: set[Path] = set()

    def provenance(path: Path, pointer: str, evaluation: dict) -> dict:
        inputs.add(path)
        relative = path.relative_to(ROOT).as_posix()
        return {
            "source_commit": source["source_commit"],
            "source_file": f"evidence/{relative}",
            "source_pointer": pointer,
            "source_sha256": build_site.sha256(path),
            "source_url": f"{build_site.SOURCE}/blob/{source['source_commit']}/{relative}",
            "task": evaluation["task"]["id"],
            "task_split": evaluation["task"]["split"],
            "candidate_sha256": evaluation["candidate_sha256"],
            "grader_sha256": evaluation["grader_sha256"],
            "cases_sha256": evaluation["cases_sha256"],
            "runtime_json": compact(evaluation["runtime"]),
        }

    for directory in ("audit", "support-audit", "research/robot-audit-python"):
        path = ROOT / "examples" / directory / "audit.json"
        audit = json.loads(path.read_text())
        margins = {
            item["name"]: len(set(item["failing_cases"])) if item["valid"] else None
            for item in audit["mutants"]
        }
        controls = [("reference", "/reference", audit["reference"], "reference")]
        controls.extend(
            (item["name"], f"/mutants/{i}/evaluation", item["evaluation"], "declared-fault")
            for i, item in enumerate(audit["mutants"])
        )
        for name, pointer, evaluation, kind in controls:
            validate_evaluation(evaluation)
            for i, case in enumerate(evaluation["cases"]):
                rows["audit_cases"].append(
                    {
                        "id": f"{evaluation['task']['id']}/{name}/{case['seed']}/{case['case_id']}",
                        "control": name,
                        "control_kind": kind,
                        "control_detection_margin": margins.get(name),
                        "case_id": case["case_id"],
                        "seed": case["seed"],
                        "case_passed": case["passed"],
                        "case_status": case["status"],
                        "evaluation_valid": evaluation["valid"],
                        "evaluation_resolved": evaluation["resolved"],
                        "evaluation_score": evaluation["score"],
                        "recorded_evalarc_version": evaluation["evalarc_version"],
                        "failed_checks": [
                            check for check, passed in case["checks"].items() if passed is False
                        ],
                        "checks_json": compact(case["checks"]),
                        "case_json": compact(case),
                        **provenance(path, f"{pointer}/cases/{i}", evaluation),
                    }
                )
    for control, directory in (("reference", "repetition"), ("faulty", "repetition-faulty")):
        folder = ROOT / "examples" / directory
        inputs.add(folder / "repetition.json")
        for i, path in enumerate(sorted((folder / "attempts").glob("*/evaluation.json")), 1):
            evaluation = read_evaluation(path)
            rows["repetition_attempts"].append(
                {
                    "id": f"{control}/{i}",
                    "control": control,
                    "attempt": i,
                    "score": evaluation["score"],
                    "resolved": evaluation["resolved"],
                    "valid": evaluation["valid"],
                    "status": evaluation["status"],
                    "recorded_evalarc_version": evaluation["evalarc_version"],
                    **provenance(path, "", evaluation),
                }
            )
    path = ROOT / "examples" / "suite" / "suite.json"
    suite = json.loads(path.read_text())
    for i, job in enumerate(suite["jobs"]):
        rows["suite_jobs"].append(
            {
                "id": job["id"],
                "mean_score": job["observed"]["mean_score"],
                "gate_accepted": job["decision"]["accepted"],
                "fully_resolved": job["fully_resolved"],
                "valid": job["decision"]["valid"],
                "status": job["status"],
                "completed_attempts": job["observed"]["completed_attempts"],
                "resolved_attempts": job["observed"]["resolved_attempts"],
                "assessed_attempts": job["observed"]["assessed_attempts"],
                "invalid_attempts": job["observed"]["invalid_attempts"],
                "gate_json": compact(job["gate"]),
                "decision_json": compact(job["decision"]),
                "recorded_evalarc_version": suite["evalarc_version"],
                **provenance(path, f"/jobs/{i}", job),
            }
        )
    # Keep every suite attempt and its configuration alongside the derived rows.
    inputs.update(
        path
        for path in (ROOT / "examples" / "suite").rglob("*")
        if path.is_file() and path.suffix in (".json", ".jsonl", ".xml", ".toml")
    )
    if {name: len(values) for name, values in rows.items()} != COUNTS:
        raise ValueError("Evidence changed; review the casebook inventory before publishing")
    (destination / "data").mkdir(parents=True)
    for name, values in rows.items():
        (destination / "data" / f"{name}.jsonl").write_text(
            # Preserve presentation order: outcome columns precede long fingerprints.
            "".join(
                json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in values
            )
        )
    for path in sorted(inputs):
        target = destination / "evidence" / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    card = (ROOT / "huggingface" / "DATASET.md").read_text()
    (destination / "README.md").write_text(card.replace("@SOURCE_COMMIT@", source["source_commit"]))
    shutil.copyfile(ROOT / "LICENSE", destination / "LICENSE")
    record = {
        "schema": SCHEMA,
        "source_repository": build_site.SOURCE,
        "source_commit": source["source_commit"],
        "source_dirty": source["source_dirty"],
        "row_counts": COUNTS,
        "evidence": "Recorded scripted public-development controls; not model evaluations.",
        "files": {
            path.relative_to(destination).as_posix(): build_site.sha256(path)
            for path in sorted(destination.rglob("*"))
            if path.is_file()
        },
    }
    (destination / "manifest.json").write_text(json.dumps(record, indent=2) + "\n")
    return verify(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))

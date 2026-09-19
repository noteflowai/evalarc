"""Compare saved judgments of one fixed recording; never rerun an agent or judge."""

from __future__ import annotations

from pathlib import Path

from evalarc.artifacts import new_run
from evalarc.records import read_bytes
from evalarc.trace_review import MAX_BYTES, canonical, decode, digest, review

SCHEMA = "evalarc.judge-stability.v1"
MAX_RUNS = 20
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_REPORT_BYTES = 32 * 1024 * 1024
SCOPE = (
    "Descriptive agreement of imported judgments on the same declared recording and rubric. "
    "No agent or judge is executed. Repetition IDs and evaluator revisions are caller-declared; "
    "agreement does not establish independence, accuracy, calibration or task success."
)


def fixed_record(data: dict) -> dict:
    """Freeze all input fields except judgment payloads and collection descriptions."""
    return {
        "input": {k: v for k, v in data.items() if k not in ("run_id", "provenance", "cases")},
        "provenance": {k: v for k, v in data["provenance"].items() if k != "description"},
        "cases": [
            {k: v for k, v in case.items() if k != "evaluation_response"} for case in data["cases"]
        ],
    }


def summarize(contents: list[bytes]) -> dict:
    if not 2 <= len(contents) <= MAX_RUNS:
        raise ValueError(f"judge stability requires 2–{MAX_RUNS} saved judgments")
    if sum(map(len, contents)) > MAX_TOTAL_BYTES:
        raise ValueError("judge stability inputs exceed the 16 MiB total limit")
    reviews, sources, frozen, ids = [], [], None, set()
    for index, content in enumerate(contents):
        result = review(content)
        if result["run_id"] in ids:
            raise ValueError("judge repetitions require distinct caller-declared run IDs")
        ids.add(result["run_id"])
        identity = canonical(fixed_record(decode(content)))
        if frozen is not None and identity != frozen:
            raise ValueError(
                "judge repetitions require the same recording, provenance kind, "
                "configuration, dataset and evaluator definitions; agent reruns are different"
            )
        frozen = identity
        sources.append(
            {
                "file": f"inputs/{index + 1:04d}.json",
                "sha256": digest(content),
                "bytes": len(content),
                "run_id": result["run_id"],
                "provenance": result["provenance"],
            }
        )
        reviews.append(result)
    cases = []
    for index, case in enumerate(reviews[0]["cases"]):
        targets = []
        for target_index, first in enumerate(case["results"]):
            observations = [
                {
                    "run_id": run["run_id"],
                    **{
                        k: run["cases"][index]["results"][target_index][k]
                        for k in ("status", "value", "label", "accepted", "explanation", "error")
                    },
                }
                for run in reviews
            ]
            assessed = [row for row in observations if row["status"] == "assessed"]
            passed = sum(row["accepted"] is True for row in assessed)
            rejected = len(assessed) - passed
            not_applicable = all(row["status"] == "not_applicable" for row in observations)
            complete = len(assessed) == len(contents)
            flip = bool(passed and rejected)
            spec = next(s for s in reviews[0]["evaluators"] if s["id"] == first["evaluator"])
            score_key = "value" if spec["rating"]["kind"] == "numeric" else "label"
            values = sorted(set(row[score_key] for row in assessed))
            state = (
                "not_applicable"
                if not_applicable
                else "incomplete"
                if not complete
                else "disagreement"
                if flip
                else "same_gate"
            )
            targets.append(
                {
                    "evaluator": first["evaluator"],
                    "revision": first["revision"],
                    "trace_id": first["trace_id"],
                    "span_id": first["span_id"],
                    "rating": spec["rating"],
                    "state": state,
                    "assessed": len(assessed),
                    "expected": 0 if not_applicable else len(contents),
                    "passed": passed,
                    "rejected": rejected,
                    "unassessed": 0 if not_applicable else len(contents) - len(assessed),
                    "observed_gate_disagreement": flip,
                    "observed_score_disagreement": len(values) > 1,
                    "observed_values": values,
                    "observations": observations,
                }
            )
        cases.append(
            {
                "case_id": case["case_id"],
                "goal": case["goal"],
                "session_id": case["session_id"],
                "targets": targets,
                # Overall task gates can fail for fixed skill evidence even when judges agree.
                "case_gates": [
                    {"run_id": run["run_id"], "gate": run["cases"][index]["gate"]}
                    for run in reviews
                ],
            }
        )
    all_targets = [row for case in cases for row in case["targets"]]
    required = [row for row in all_targets if row["state"] != "not_applicable"]
    summary = {
        "repetitions": len(contents),
        "required_targets": len(required),
        "complete_targets": sum(row["unassessed"] == 0 for row in required),
        "incomplete_targets": sum(row["unassessed"] > 0 for row in required),
        "not_applicable_targets": len(all_targets) - len(required),
        "gate_disagreements": sum(row["observed_gate_disagreement"] for row in required),
        "score_disagreements": sum(row["observed_score_disagreement"] for row in required),
        "all_rejected_targets": sum(row["rejected"] == len(contents) for row in required),
    }
    record = {
        "schema_version": SCHEMA,
        "mode": "fixed_record_judge_repetitions",
        "fixed_record_sha256": digest(frozen),
        "sources": sources,
        "dataset": reviews[0]["dataset"],
        "configuration": reviews[0]["configuration"],
        "evaluators": reviews[0]["evaluators"],
        "provenance_kind": reviews[0]["provenance"]["kind"],
        "cases": cases,
        "summary": summary,
        "scope": SCOPE,
    }
    if len(canonical(record)) > MAX_REPORT_BYTES:
        raise ValueError("judge stability report exceeds the 32 MiB limit")
    return record


def import_judgments(sources: list[Path], output: Path) -> dict:
    if not 2 <= len(sources) <= MAX_RUNS:
        raise ValueError(f"judge stability requires 2–{MAX_RUNS} saved judgments")
    contents = []
    total = 0
    for source in sources:
        content = read_bytes(source, limit=min(MAX_BYTES, MAX_TOTAL_BYTES - total))
        contents.append(content)
        total += len(content)
    record = summarize(contents)
    from evalarc.judge_stability_report import render

    with new_run(output) as folder:
        (folder / "inputs").mkdir()
        for source, content in zip(record["sources"], contents, strict=True):
            (folder / source["file"]).write_bytes(content)
        (folder / "stability.json").write_bytes(canonical(record) + b"\n")
        render(record, folder / "index.html")
    return record


def verify_judgments(folder: Path) -> dict:
    if any(p.is_symlink() for p in (folder, *folder.parents, folder / "inputs")):
        raise ValueError("judge evidence path must not contain symlinks")
    recorded = decode(
        read_bytes(folder / "stability.json", limit=MAX_REPORT_BYTES + 1),
        MAX_REPORT_BYTES + 1,
    )
    sources = recorded.get("sources")
    if not isinstance(sources, list) or not 2 <= len(sources) <= MAX_RUNS:
        raise ValueError("invalid judge input inventory")
    names = {f"{index + 1:04d}.json" for index in range(len(sources))}
    if {p.name for p in (folder / "inputs").iterdir()} != names:
        raise ValueError("judge input inventory differs from the saved sources")
    contents, total = [], 0
    for name in sorted(names):
        content = read_bytes(
            folder / "inputs" / name, limit=min(MAX_BYTES, MAX_TOTAL_BYTES - total)
        )
        contents.append(content)
        total += len(content)
    current = summarize(contents)
    if canonical(recorded) != canonical(current):
        raise ValueError("judge stability report differs from its original input evidence")
    return {
        "verified": True,
        "fixed_record_sha256": current["fixed_record_sha256"],
        "summary": current["summary"],
        "scope": SCOPE + " HTML is not verified; no producer authentication.",
    }

PARTIAL_CREDIT = True
"""Reads data only; never imports or executes the submitted main.py."""
import json
from pathlib import Path
from evalarc.robot_task import DIMENSIONS, generate_cases, verify

cases = [case for seed in (41, 97) for case in generate_cases(seed)]
source = Path("/workspace/answers.jsonl")
findings = []
error = None
try:
    if source.is_symlink() or not source.is_file() or source.stat().st_size > 131072:
        raise ValueError("missing, nonregular or oversized answer file")
    answers = [json.loads(line) for line in source.read_text().splitlines()]
    if len(answers) != len(cases):
        raise ValueError("answer count differs from request count")
    for case, answer in zip(cases, answers, strict=True):
        envelope = (isinstance(answer, dict) and set(answer) == {"ok", "report"}
                    and answer["ok"] is True)
        report = answer.get("report") if isinstance(answer, dict) else None
        checks = verify(case, report, envelope)
        findings.append({"case_id": case.id, "checks": checks, "passed": all(checks.values())})
except (ValueError, TypeError, OSError, RecursionError) as exc:
    error = str(exc)
passed = error is None and len(findings) == len(cases) and all(row["passed"] for row in findings)
weighted_score = (sum(
    sum(DIMENSIONS[key] for key, ok in row["checks"].items() if ok)
    for row in findings
) / len(cases)) if error is None else 0.0
reward = weighted_score if PARTIAL_CREDIT else float(passed)
logs = Path("/logs/verifier")
logs.mkdir(parents=True, exist_ok=True)
(logs / "reward.txt").write_text(str(reward))
(logs / "evidence.json").write_text(json.dumps({
    "scope": "Answers checked in a fresh verifier container; submitted code is not executed here.",
    "passed": passed, "error": error, "findings": findings,
    "weighted_score": weighted_score, "partial_credit": PARTIAL_CREDIT
}, indent=2) + "\n")

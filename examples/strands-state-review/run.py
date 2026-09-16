"""Recheck two recorded state rules with Strands Evals, without running an agent."""

from __future__ import annotations

import argparse
import hashlib
import json
from importlib.metadata import version
from pathlib import Path

from strands_evals import Case, Experiment
from strands_evals.evaluators import Evaluator
from strands_evals.types import EvaluationData, EvaluationOutput
from strands_evals.types.evaluation import EnvironmentState
from strands_evals.types.evaluation_report import EvaluationReport

ROOT = Path(__file__).resolve().parents[2]
SOURCE_HASHES = {
    "baseline": "4ec043dd1de0b0d852737cf6e8f2ebe04d517d0c945335e686773e00a8f970b5",
    "current": "40d0726cd8378b237c514d69b4fda9e4f00550dc3012f4c276a360f4deed25ad",
}
VERSIONS = {"strands-agents-evals": "1.3.0", "strands-agents": "1.56.0"}


class TicketStateRule(Evaluator[str, str]):
    """Compare one field of an observed ticket with its declared expected state."""

    def __init__(self, field: str) -> None:
        super().__init__(name=f"ticket.{field}")
        self.field = field

    def evaluate(self, data: EvaluationData[str, str]) -> list[EvaluationOutput]:
        actual = [
            state.state for state in data.actual_environment_state or [] if state.name == "ticket"
        ]
        expected = [
            state.state for state in data.expected_environment_state or [] if state.name == "ticket"
        ]
        if len(actual) != 1 or len(expected) != 1:
            raise ValueError("This recipe requires one actual and one expected ticket state")
        passed = actual[0][self.field] == expected[0][self.field]
        return [
            EvaluationOutput(
                score=float(passed),
                test_pass=passed,
                reason=f"ticket.{self.field}: {'matches' if passed else 'differs from'} expected",
            )
        ]


def read_record(folder: Path, revision: str) -> dict:
    raw = (folder / f"{revision}.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_HASHES[revision]:
        raise ValueError(f"{revision}: use the original published comparison record")
    return json.loads(raw)


def review_record(record: dict, revision: str) -> EvaluationReport:
    cases = []
    states = {}
    for row in record["cases"]:
        # This is the fixed public support fixture, identified by its complete
        # byte hash above. It is not a heuristic for arbitrary customer tickets.
        target = next(ticket for ticket in row["initial_state"] if ticket.startswith("T-"))
        initial = row["initial_state"][target]
        expected = {
            "notes": [*initial["notes"], f"Reviewed request {target}."],
            "status": "closed" if initial["resolved"] else "open",
        }
        name = f"{row['case_id']}@{row['seed']}"
        states[name] = row["final_state"][target]
        cases.append(
            Case(
                name=name,
                session_id=f"local-state-review-{revision}-{name}",
                input=name,
                expected_environment_state=[EnvironmentState(name="ticket", state=expected)],
                metadata={
                    "source_case_id": row["case_id"],
                    "source_seed": row["seed"],
                    "source_sha256": SOURCE_HASHES[revision],
                    "kind": "recheck of saved scripted Docker state; no agent execution",
                },
            )
        )

    def saved_state(case: Case) -> dict:
        return {
            "output": "Saved ticket state, not a new agent response.",
            "environment_state": [EnvironmentState(name="ticket", state=states[case.name])],
        }

    experiment = Experiment(
        cases=cases, evaluators=[TicketStateRule("notes"), TicketStateRule("status")]
    )
    return experiment.run_evaluations(saved_state)


def verdicts(report: EvaluationReport) -> dict[tuple[str, str], bool]:
    if len(report.cases) != len(report.test_passes):
        raise ValueError("Native report has unequal case and verdict inventories")
    rows = {}
    for case, passed in zip(report.cases, report.test_passes, strict=True):
        key = (case["name"], case["evaluator"])
        if key in rows:
            raise ValueError(f"Duplicate case/evaluator row: {key}")
        rows[key] = passed
    return rows


def compare_reports(before: EvaluationReport, after: EvaluationReport) -> dict:
    old, new = verdicts(before), verdicts(after)
    if not old or old.keys() != new.keys():
        raise ValueError("Compare the same nonempty set of case/evaluator pairs")
    regressions = [list(key) for key in old if old[key] and not new[key]]
    improvements = [list(key) for key in old if not old[key] and new[key]]
    return {
        "scope": "Four saved cases, two deterministic state rules, eight equally weighted rows.",
        "baseline": {
            "native_mean_score": before.overall_score,
            "passed_rows": sum(old.values()),
            "rows": len(old),
            "all_rows_pass": all(old.values()),
        },
        "current": {
            "native_mean_score": after.overall_score,
            "passed_rows": sum(new.values()),
            "rows": len(new),
            "all_rows_pass": all(new.values()),
        },
        "regressions": regressions,
        "improvements": improvements,
        "regression_gate_passes": not regressions,
    }


def run(comparison: Path, output: Path) -> dict:
    installed = {name: version(name) for name in VERSIONS}
    if installed != VERSIONS:
        raise ValueError(f"Use the recipe's tested SDK versions: {VERSIONS}")
    records = {name: read_record(comparison, name) for name in SOURCE_HASHES}
    reports = {name: review_record(record, name) for name, record in records.items()}
    summary = compare_reports(reports["baseline"], reports["current"])
    summary["sdk_versions"] = installed
    summary["source_sha256"] = SOURCE_HASHES
    summary["original_evalarc_scores"] = {
        "baseline": records["baseline"]["score"],
        "current": records["current"]["score"],
        "scope": "Original five-dimension weighted score; not the Strands two-rule mean.",
    }
    summary["execution"] = (
        "Strands framework execution over saved state; no model or AWS evaluation."
    )
    output.mkdir(parents=True, exist_ok=False)
    for name, report in reports.items():
        report.to_file(str(output / f"{name}-native.json"))
    (output / "comparison.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, default=ROOT / "examples/comparison")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = run(args.comparison, args.output)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, f"strands-state-review: {error}\n")
    print(json.dumps(summary, indent=2))
    # A valid review can still reject a change. Keep this explicit in CI.
    return 0 if summary["regression_gate_passes"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

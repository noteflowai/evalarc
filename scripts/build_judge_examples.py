"""Five authored judge-agreement controls, not observations of a model or cloud service."""

import copy
import json
from pathlib import Path

from scripts.build_trace_examples import example

ROOT = Path(__file__).resolve().parents[1]


def examples() -> list[dict]:
    base = example()
    names = ["same-pass", "same-reject", "gate-flip", "score-only-change", "partial-judgments"]
    base["dataset"] = {
        "id": "judge-stability-controls",
        "version": "1",
        "cases": [
            {"id": name, "goal": f"Inspect the {name} condition.", "expected_skills": []}
            for name in names
        ],
    }
    base["configuration"]["skills"] = {}
    base["evaluators"] = [
        {
            "id": "authored-goal",
            "revision": "control-1; no model or AWS call",
            "level": "session",
            "rating": {"kind": "numeric", "min": 0, "max": 1, "pass_at_least": 0.8},
        }
    ]
    base["provenance"] = {
        "kind": "synthetic",
        "description": (
            "Five authored controls with three judgment sets on identical simulated spans. "
            "Scores and placeholder identities are synthetic; no model or AWS evaluation."
        ),
    }
    for name, case in zip(names, base["cases"], strict=True):
        case["case_id"] = name
        case["skill_calls"] = []
        case["evaluation_response"]["evaluationResults"] = [
            {
                "evaluatorId": "authored-goal",
                "context": {"spanContext": {"sessionId": case["session_id"]}},
                "value": 1,
                "explanation": "Authored judgment; not a performance measurement.",
            }
        ]
    inputs = []
    for index in range(3):
        data = copy.deepcopy(base)
        data["run_id"] = f"authored-judgment-{index + 1}"
        values = [1, 0, [1, 0, 1][index], [0.8, 0.9, 1][index], 1]
        for case, value in zip(data["cases"], values, strict=True):
            case["evaluation_response"]["evaluationResults"][0]["value"] = value
        if index == 1:
            row = data["cases"][-1]["evaluation_response"]["evaluationResults"][0]
            row.pop("value")
            row.update(errorCode="Skipped", errorMessage="Authored unavailable-context control.")
        if index == 2:
            data["cases"][-1]["evaluation_response"]["evaluationResults"] = []
        inputs.append(data)
    return inputs


if __name__ == "__main__":
    folder = ROOT / "examples/judge-stability"
    folder.mkdir(exist_ok=True)
    for index, data in enumerate(examples()):
        (folder / f"judge-{index + 1}.json").write_text(json.dumps(data, indent=2) + "\n")

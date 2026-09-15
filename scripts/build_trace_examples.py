"""Generate explicitly synthetic controls, never cloud or model performance evidence."""

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def example() -> dict:
    names = ["accepted-control", "assessed-zero", "skipped-judge", "missing-result", "missed-skill"]
    data = {
        "schema_version": "evalarc.trace-input.v1",
        "run_id": "synthetic-baseline",
        "provenance": {
            "kind": "synthetic",
            "description": (
                "Five authored controls for import and review behavior. "
                "Placeholder hashes, simulated spans and judgments; no AWS or model run."
            ),
        },
        "dataset": {
            "id": "trace-review-controls",
            "version": "1",
            "cases": [
                {
                    "id": name,
                    "goal": f"Inspect the {name} review condition.",
                    "expected_skills": ["evidence-review"] if i in (0, 1, 4) else [],
                }
                for i, name in enumerate(names)
            ],
        },
        "configuration": {
            "model": "synthetic-control",
            "model_parameters": {},
            "prompt_sha256": "a" * 64,
            "tools_sha256": "b" * 64,
            "skills": {"evidence-review": "c" * 64},
        },
        "evaluators": [
            {
                "id": "goal-control",
                "revision": "authored-1",
                "level": "session",
                "rating": {"kind": "numeric", "min": 0, "max": 1, "pass_at_least": 1},
            },
            {
                "id": "Builtin.SkillInstructionFollowing",
                "revision": "synthetic-scale-1",
                "level": "skill",
                "rating": {"kind": "numeric", "min": 0, "max": 1, "pass_at_least": 1},
            },
        ],
        "cases": [],
    }
    for index, definition in enumerate(data["dataset"]["cases"]):
        sid, tid, spid = f"session-{index}", f"{index + 1:032x}", f"{index + 1:016x}"
        has_skill = bool(definition["expected_skills"])
        case = {
            "case_id": definition["id"],
            "session_id": sid,
            "trace_ids": [tid],
            "skill_observation_complete": True,
            "spans": [
                {
                    "traceId": tid,
                    "spanId": spid,
                    "name": "authored-control",
                    "attributes": {"session.id": sid},
                }
            ],
            "skill_calls": [],
            "evaluation_response": {"evaluationResults": []},
        }
        for evaluator in data["evaluators"][: 2 if has_skill else 1]:
            ctx = {"sessionId": sid}
            if evaluator["level"] == "skill":
                ctx.update(traceId=tid, spanId=spid)
            case["evaluation_response"]["evaluationResults"].append(
                {
                    "evaluatorId": evaluator["id"],
                    "evaluatorName": evaluator["id"],
                    "evaluatorArn": "synthetic-control",
                    "context": {"spanContext": ctx},
                    "value": 1,
                    "explanation": "Authored passing control.",
                }
            )
        if has_skill:
            case["skill_calls"].append(
                {
                    "name": "evidence-review",
                    "trace_id": tid,
                    "span_id": spid,
                    "receipt": {
                        "schema": "skills-anywhere-load-1",
                        "load_id": f"synthetic-{index}",
                        "loaded_at": "2026-09-15T00:00:00Z",
                        "provider": "dsh-skills-anywhere",
                        "provider_version": "0.12.0",
                        "name": "evidence-review",
                        "skill_sha256": "d" * 64,
                        "content_sha256": "e" * 64,
                        "bundle_sha256": "c" * 64,
                        "declared_tools": None,
                        "permissions_enforced": False,
                    },
                }
            )
        data["cases"].append(case)
    return data


def current_example() -> dict:
    data = copy.deepcopy(example())
    data["run_id"] = "synthetic-current"
    data["configuration"]["prompt_sha256"] = "f" * 64
    result = data["cases"][1]["evaluation_response"]["evaluationResults"][0]
    result.update(value=0, explanation="Valid zero: the authored output lacks evidence.")
    result = data["cases"][2]["evaluation_response"]["evaluationResults"][0]
    result.pop("value")
    result.update(errorCode="Skipped", errorMessage="Authored example of unavailable context.")
    data["cases"][3]["evaluation_response"]["evaluationResults"] = []
    data["cases"][4]["skill_calls"] = []
    data["cases"][4]["evaluation_response"]["evaluationResults"].pop()
    return data


if __name__ == "__main__":
    folder = ROOT / "examples/trace-workbench"
    folder.mkdir(exist_ok=True)
    for name, data in (("baseline", example()), ("current", current_example())):
        (folder / f"{name}.json").write_text(json.dumps(data, indent=2) + "\n")

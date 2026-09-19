"""Harbor evidence import and ATIF export without conflating reward and correctness."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from evalarc import __version__
from evalarc.evaluate import evaluate, write_json
from evalarc.runner import Runtime

MAX_DOCUMENT_BYTES = 16 * 1024 * 1024


def _finite(value: object) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def read_document(path: Path) -> tuple[dict, str, bytes]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("evidence must be a regular file, not a symlink")
    with path.open("rb") as stream:
        raw = stream.read(MAX_DOCUMENT_BYTES + 1)
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValueError("evidence exceeds 16 MiB")
    document = json.loads(raw)
    if not isinstance(document, dict):
        raise ValueError("evidence must be a JSON object")
    json.dumps(document, allow_nan=False)
    return document, hashlib.sha256(raw).hexdigest(), raw


def inspect_atif(document: dict) -> dict:
    """Validate text/tool linkage; preserve original multimodal fields in the file.

    This bounded dependency-free inspection is explicitly narrower than Harbor's
    full schema validator. It does not fetch media or execute referenced tools.
    """
    if document.get("schema_version") not in ("ATIF-v1.7", "ATIF-v1.8"):
        raise ValueError("supported trajectory versions are ATIF-v1.7 and ATIF-v1.8")
    agent = document.get("agent")
    if not isinstance(agent, dict) or not all(
        isinstance(agent.get(key), str) and agent[key] for key in ("name", "version")
    ):
        raise ValueError("ATIF requires an agent name and version")
    steps = document.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 10_000:
        raise ValueError("ATIF requires 1..10000 steps")
    calls_count = 0
    for index, step in enumerate(steps, 1):
        if (
            not isinstance(step, dict)
            or type(step.get("step_id")) is not int
            or step["step_id"] != index
            or step.get("source") not in ("system", "user", "agent")
            or not isinstance(step.get("message"), (str, list))
        ):
            raise ValueError("ATIF steps must have sequential IDs, a source and a message")
        calls = step.get("tool_calls") or []
        if not isinstance(calls, list):
            raise ValueError("ATIF tool_calls must be an array")
        ids = set()
        for call in calls:
            if (
                not isinstance(call, dict)
                or not isinstance(call.get("tool_call_id"), str)
                or not call["tool_call_id"]
                or call["tool_call_id"] in ids
                or not isinstance(call.get("function_name"), str)
                or not isinstance(call.get("arguments"), dict)
            ):
                raise ValueError("ATIF tool calls require unique IDs, names and arguments")
            ids.add(call["tool_call_id"])
            calls_count += 1
        observation = step.get("observation")
        if observation is not None:
            if not isinstance(observation, dict) or not isinstance(
                observation.get("results"), list
            ):
                raise ValueError("ATIF observation needs a results array")
            for result in observation["results"]:
                if not isinstance(result, dict) or (
                    result.get("source_call_id") is not None and result["source_call_id"] not in ids
                ):
                    raise ValueError("ATIF observation references an unknown tool call")
    return {
        "version": document["schema_version"],
        "agent": agent["name"],
        "steps": len(steps),
        "tool_calls": calls_count,
        "validation": "bounded-envelope-and-tool-linkage",
        "full_upstream_schema_validated": False,
    }


def trial_to_atif(trial: dict, source_sha256: str) -> dict:
    if trial.get("schema_version") != "evalarc.skill-impact-trial.v1":
        raise ValueError("expected a recorded skill-impact trial")
    model = trial["model"]
    messages = trial["messages"]
    steps = [
        {"step_id": index + 1, "source": row["role"], "message": row["content"]}
        for index, row in enumerate(messages[:2])
    ]
    for turn in trial["turns"]:
        events = [event for event in trial["tool_events"] if event["step"] == turn["step"]]
        calls, results = [], []
        for index, event in enumerate(events):
            call_id = f"turn-{turn['step']}-call-{index}"
            calls.append(
                {
                    "tool_call_id": call_id,
                    "function_name": event["name"],
                    "arguments": event["arguments"],
                }
            )
            results.append(
                {
                    "source_call_id": call_id,
                    "content": json.dumps(event["result"], ensure_ascii=False),
                    "extra": {"receipt": event["receipt"]} if event.get("receipt") else None,
                }
            )
        step = {
            "step_id": len(steps) + 1,
            "source": "agent",
            "model_name": model["model"],
            "message": turn["text"],
            "llm_call_count": 1,
            "metrics": {
                "prompt_tokens": turn["prompt_tokens"],
                "completion_tokens": turn["completion_tokens"],
                "extra": {"wall_seconds": turn["wall_seconds"]},
            },
        }
        if calls:
            step.update(tool_calls=calls, observation={"results": results})
        steps.append(step)
    result = {
        "schema_version": "ATIF-v1.8",
        "session_id": f"evalarc-{source_sha256[:24]}",
        "trajectory_id": source_sha256,
        "agent": {
            "name": "evalarc-local-model-pilot",
            "version": __version__,
            "model_name": model["model"],
            "extra": {"model_revision": model["revision"], "condition": trial["condition"]},
        },
        "steps": steps,
        "final_metrics": {
            "total_prompt_tokens": trial["prompt_tokens"],
            "total_completion_tokens": trial["completion_tokens"],
            "total_steps": len(steps),
        },
        "notes": (
            "Export of an actual local GPU model trial. Tool result receipts retain "
            "delivery provenance. Task completion is independently checked by EvalArc. "
            "Hardware cost was not estimated; no monetary cost is asserted."
        ),
        "extra": {
            "source_trial_sha256": source_sha256,
            "agent_status": trial["status"],
            "independent_evaluation": trial["independent_evaluation"],
            "skill_pins": trial["skill_pins"],
        },
    }
    inspect_atif(result)
    return result


def import_harbor(
    trial_directory: Path,
    candidate: Path,
    output: Path,
    runtime: Runtime,
    seeds: list[int],
    task_id: str = "robot-evidence-review",
    minimum_score: float = 1.0,
) -> dict:
    if not _finite(minimum_score):
        raise ValueError("minimum score must be finite")
    if not 0 <= minimum_score <= 1:
        raise ValueError("minimum score must be between zero and one")
    source, result_hash, result_bytes = read_document(trial_directory / "result.json")
    upstream = source.get("verifier_result")
    rewards = upstream.get("rewards") if isinstance(upstream, dict) else None
    if rewards is not None and (
        not isinstance(rewards, dict)
        or any(not isinstance(key, str) or not _finite(value) for key, value in rewards.items())
    ):
        raise ValueError("upstream rewards must be a finite numeric mapping or null")
    trajectory_path = trial_directory / "agent" / "trajectory.json"
    trajectory = None
    trajectory_hash = None
    trajectory_bytes = None
    inspection = None
    if trajectory_path.exists():
        trajectory, trajectory_hash, trajectory_bytes = read_document(trajectory_path)
        inspection = inspect_atif(trajectory)
    # The caller chooses the candidate explicitly. An untrusted external report
    # cannot nominate a host path or instruct this importer to execute a tool.
    if runtime.backend != "docker":
        raise ValueError("Harbor import independently executes candidate code in Docker")
    output.mkdir(parents=True, exist_ok=False)
    evaluation = evaluate(candidate, runtime, seeds, task_id)
    write_json(output / "evaluation.json", evaluation)
    accepted = evaluation["valid"] and evaluation["score"] >= minimum_score
    report = {
        "schema_version": "evalarc.harbor-import.v1",
        "source": {
            "result_sha256": result_hash,
            "trajectory_sha256": trajectory_hash,
            "trial_name": source.get("trial_name"),
            "task_name": source.get("task_name"),
        },
        "upstream": {
            "rewards": rewards,
            "exception": source.get("exception_info"),
            "workflow_finished_at": source.get("finished_at"),
            "agent_completion": None,
        },
        "trajectory": inspection,
        "independent": {
            "evaluation": "evaluation.json",
            "candidate_sha256": evaluation["candidate_sha256"],
            "candidate_selection": "explicit caller-supplied directory",
            **{key: evaluation[key] for key in ("valid", "resolved", "score", "status")},
        },
        "acceptance": {
            "minimum_independent_score": minimum_score,
            "requires_valid_independent_evaluation": True,
            "requires_upstream_reward": False,
            "accepted": accepted,
        },
        "scope": (
            "Upstream rewards are imported claims. Acceptance uses the explicitly "
            "configured independent score threshold; resolved means every independent "
            "case passed. A finished Harbor workflow does not establish agent completion. "
            "ATIF inspection validates envelope and tool linkage, not the full upstream schema."
            " The caller selects the candidate; source report metadata cannot establish "
            "that it is the same program used in the upstream run."
        ),
    }
    write_json(output / "harbor-import.json", report)
    # Exact source bytes are retained, not reserialized or silently normalized.
    (output / "source-result.json").write_bytes(result_bytes)
    if trajectory_bytes is not None:
        (output / "source-trajectory.json").write_bytes(trajectory_bytes)
    return report

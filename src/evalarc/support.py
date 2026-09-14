"""A host-owned ticket service, independent state verifier, and JSONL agent loop."""

from __future__ import annotations

import copy
import hashlib
import random
import time
from dataclasses import dataclass
from pathlib import Path

from evalarc.runner import CandidateError, EnvironmentFailure, Runtime
from evalarc.task import canonical

DIMENSIONS = {"routing": 0.30, "notes": 0.25, "closure": 0.20, "scope": 0.15, "protocol": 0.10}
MAX_ACTIONS = 12


@dataclass(frozen=True)
class TicketCase:
    id: str
    target: str
    initial: dict
    routing_rules: dict[str, str]
    note: str
    fault: str | None = None


def generate_cases(seed: int) -> list[TicketCase]:
    rng = random.Random(seed)
    cases = []
    categories = ["billing", "technical", "account"]
    for index, (name, resolved, fault) in enumerate(
        [
            ("route-open-ticket", False, None),
            ("close-resolved-ticket", True, None),
            ("retry-before-commit", False, "assign_queue"),
            ("retry-after-commit", True, "add_note"),
        ]
    ):
        target = f"T-{rng.getrandbits(32):08x}"
        other = f"U-{rng.getrandbits(32):08x}"
        queues = [f"queue-{index}-{n}" for n in range(3)]
        rng.shuffle(queues)
        rules = dict(zip(categories, queues, strict=True))
        initial = {
            target: {
                "category": rng.choice(categories),
                "queue": "inbox",
                "resolved": resolved,
                "status": "open",
                "notes": ["Customer contacted support."],
            },
            other: {
                "category": rng.choice(categories),
                "queue": "inbox",
                "resolved": False,
                "status": "open",
                "notes": ["Unrelated request; preserve this ticket."],
            },
        }
        cases.append(TicketCase(name, target, initial, rules, f"Reviewed request {target}.", fault))
    return cases


def tool_error(code: str, *, retryable: bool = False) -> dict:
    return {"ok": False, "error": {"code": code, "retryable": retryable}}


class TicketEnvironment:
    """No state or verifier files are mounted into the agent process."""

    def __init__(self, case: TicketCase):
        self.case = case
        self.state = copy.deepcopy(case.initial)
        self.receipts: dict[tuple[str, str], tuple[str, dict]] = {}
        self.fault_used = False

    def observe(self) -> dict:
        return {
            "type": "start",
            "task": {
                "ticket_id": self.case.target,
                "ticket_ids": list(self.state),
                "routing_rules": self.case.routing_rules.copy(),
                "note": self.case.note,
                "instruction": (
                    "Route the target by its category, add the requested note exactly once, "
                    "close it only if resolved, and preserve all other data."
                ),
            },
            "tools": ["get_ticket", "assign_queue", "add_note", "close_ticket"],
            "remaining_actions": MAX_ACTIONS,
        }

    def step(self, action: dict) -> tuple[dict, str | None]:
        """Return a tool result and a trusted error source, if any."""
        tool, args = action.get("tool"), action.get("arguments")
        required = {
            "get_ticket": {"ticket_id"},
            "assign_queue": {"ticket_id", "queue"},
            "add_note": {"ticket_id", "body", "request_id"},
            "close_ticket": {"ticket_id"},
        }
        if (
            not isinstance(tool, str)
            or tool not in required
            or not isinstance(args, dict)
            or set(args) != required[tool]
            or any(not isinstance(value, str) or len(value) > 512 for value in args.values())
        ):
            return tool_error("invalid_arguments"), "tool_validation"
        ticket_id = args["ticket_id"]
        if ticket_id not in self.state:
            return tool_error("ticket_not_found"), "tool_validation"
        ticket = self.state[ticket_id]
        if tool == "get_ticket":
            return {"ok": True, "ticket": copy.deepcopy(ticket)}, None
        if tool == "assign_queue":
            if args["queue"] not in self.case.routing_rules.values():
                return tool_error("unknown_queue"), "tool_validation"
            if self.case.fault == tool and not self.fault_used:
                self.fault_used = True
                return tool_error("temporarily_unavailable", retryable=True), "injected"
            ticket["queue"] = args["queue"]
        elif tool == "add_note":
            key = (ticket_id, args["request_id"])
            if not args["request_id"]:
                return tool_error("invalid_request_id"), "tool_validation"
            if key in self.receipts:
                body, receipt = self.receipts[key]
                if body != args["body"]:
                    return tool_error("idempotency_conflict"), "tool_validation"
                return {**receipt, "replayed": True}, None
            ticket["notes"].append(args["body"])
            self.receipts[key] = (args["body"], {"ok": True})
            if self.case.fault == tool and not self.fault_used:
                self.fault_used = True
                return tool_error("temporarily_unavailable", retryable=True), "injected"
        else:
            ticket["status"] = "closed"
        return {"ok": True}, None


def verify(case: TicketCase, final: dict, protocol_ok: bool) -> dict[str, bool]:
    """Check trusted final state directly, without calling tool handlers."""
    before = case.initial[case.target]
    target = final[case.target]
    return {
        "routing": target["queue"] == case.routing_rules[before["category"]],
        "notes": target["notes"] == [*before["notes"], case.note],
        "closure": target["status"] == ("closed" if before["resolved"] else "open"),
        "scope": (
            set(final) == set(case.initial)
            and all(
                final[key] == value for key, value in case.initial.items() if key != case.target
            )
            and target["category"] == before["category"]
            and target["resolved"] == before["resolved"]
        ),
        "protocol": protocol_ok,
    }


def run_case(case: TicketCase, workspace: Path, state: Path, runtime: Runtime) -> dict:
    started = time.monotonic()
    environment = TicketEnvironment(case)
    observation = environment.observe()
    trace = []
    error = None
    status = "passed"
    finished = False
    try:
        with runtime.start(workspace, state) as process:
            for index in range(MAX_ACTIONS):
                action = process.request(observation)
                if not isinstance(action, dict):
                    raise CandidateError("action must be an object")
                if action.get("finish") is True:
                    if set(action) - {"finish", "message"} or not isinstance(
                        action.get("message", ""), str
                    ):
                        raise CandidateError("finish accepts only a string message")
                    trace.append({"step": index, "type": "finish", "action": action})
                    process.finish("eof")
                    finished = True
                    break
                if set(action) != {"tool", "arguments"}:
                    raise CandidateError("expected tool/arguments or finish")
                before = copy.deepcopy(environment.state)
                result, source = environment.step(action)
                trace.append(
                    {
                        "step": index,
                        "type": "tool_call",
                        "action": action,
                        "result": result,
                        "status": "ok" if result["ok"] else "tool_error",
                        "error_source": source,
                        "changes": {
                            key: {"before": before[key], "after": copy.deepcopy(value)}
                            for key, value in environment.state.items()
                            if before[key] != value
                        },
                    }
                )
                observation = {
                    "type": "tool_result",
                    "result": result,
                    "remaining_actions": MAX_ACTIONS - index - 1,
                }
            if not finished:
                raise CandidateError("action budget exhausted without finish")
    except CandidateError as exc:
        error, status = str(exc), "agent_error"
        trace.append({"type": "agent_error", "error": error})
    except EnvironmentFailure as exc:
        error, status = str(exc), "environment_error"
        trace.append({"type": "environment_error", "error": error})
    checks = verify(case, environment.state, finished and error is None)
    if status == "environment_error":
        checks = {key: None for key in checks}
    passed = all(value is True for value in checks.values())
    if status == "passed" and not passed:
        status = "failed"
    return {
        "case_id": case.id,
        "checks": checks,
        "passed": passed,
        "status": status,
        "error": error,
        "duration_seconds": round(time.monotonic() - started, 6),
        "transcript_sha256": hashlib.sha256(canonical(trace).encode()).hexdigest(),
        "initial_state": case.initial,
        "final_state": environment.state,
        "trace": trace,
        "tool_calls": sum(event["type"] == "tool_call" for event in trace),
    }

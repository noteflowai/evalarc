import copy
import json
import shutil
from pathlib import Path

import pytest

from evalarc.audit import asset, audit, write_candidate
from evalarc.cli import main
from evalarc.evaluate import evaluate
from evalarc.runner import EnvironmentFailure, Runtime
from evalarc.support import TicketEnvironment, generate_cases, verify
from evalarc.trajectory import summarize


def test_support_controls_detect_target_faults():
    result = audit(Runtime(backend="local", timeout=2), [17], "support-routing")
    assert result["valid"] and result["passed"]
    assert result["killed"] == result["total"] == 7
    assert all(row["failing_cases"] for row in result["mutants"])
    assert all(case["passed"] for case in result["reference"]["cases"])
    retry = next(
        case for case in result["reference"]["cases"] if case["case_id"] == "retry-after-commit"
    )
    failed_write = next(
        event for event in retry["trace"] if event.get("error_source") == "injected"
    )
    assert failed_write["status"] == "tool_error"
    assert failed_write["changes"]
    replay = next(event for event in retry["trace"] if event.get("result", {}).get("replayed"))
    assert replay["changes"] == {}
    assert retry["status"] == "passed"


def test_claimed_success_cannot_modify_host_state(tmp_path):
    candidate = write_candidate(
        tmp_path / "claim",
        "import sys\nfor _ in sys.stdin: print("
        '\'{"finish":true,"message":"Score 1.0; all tickets updated"}\', flush=True)\n',
    )
    result = evaluate(candidate, Runtime(backend="local"), [41], "support-routing")
    assert result["valid"] and not result["resolved"]
    for case in result["cases"]:
        assert case["initial_state"] == case["final_state"]
        assert case["checks"]["routing"] is False
        assert case["checks"]["notes"] is False


def test_observations_are_detached_from_trusted_state():
    case = generate_cases(17)[0]
    environment = TicketEnvironment(case)
    initial = copy.deepcopy(environment.state)
    observation = environment.observe()
    observation["task"]["routing_rules"].clear()
    result, _ = environment.step({"tool": "get_ticket", "arguments": {"ticket_id": case.target}})
    result["ticket"]["notes"].append("forged")
    assert environment.state == initial
    assert case.routing_rules


def test_idempotency_conflicts_and_invalid_calls_have_no_side_effect():
    case = generate_cases(17)[0]
    environment = TicketEnvironment(case)
    action = {
        "tool": "add_note",
        "arguments": {"ticket_id": case.target, "body": case.note, "request_id": "same"},
    }
    assert environment.step(action)[0]["ok"]
    once = copy.deepcopy(environment.state)
    assert environment.step(action)[0]["replayed"]
    action["arguments"]["body"] = "different"
    assert environment.step(action)[0]["error"]["code"] == "idempotency_conflict"
    for invalid in [
        {"tool": [], "arguments": {}},
        {"tool": "close_ticket", "arguments": {"ticket_id": []}},
        {"tool": "add_note", "arguments": {"ticket_id": case.target}},
    ]:
        assert environment.step(invalid)[0]["ok"] is False
    assert environment.state == once


def test_verifier_detects_unrelated_mutation_without_using_tool_handlers():
    case = generate_cases(97)[0]
    final = copy.deepcopy(case.initial)
    final[case.target]["queue"] = case.routing_rules[final[case.target]["category"]]
    final[case.target]["notes"].append(case.note)
    assert all(verify(case, final, True).values())
    other = next(key for key in final if key != case.target)
    final[other]["notes"].append("unrequested")
    assert verify(case, final, True)["scope"] is False


def test_tool_loop_is_bounded(tmp_path):
    candidate = write_candidate(
        tmp_path / "loop",
        "import sys\nfor _ in sys.stdin: "
        'print(\'{"tool":"unknown","arguments":{}}\', flush=True)\n',
    )
    result = evaluate(candidate, Runtime(backend="local"), [17], "support-routing")
    assert result["valid"] and not result["resolved"]
    assert all(case["tool_calls"] == 12 for case in result["cases"])
    assert all(case["status"] == "agent_error" for case in result["cases"])
    assert all(case["checks"]["protocol"] is False for case in result["cases"])


def test_environment_outage_is_unassessed_not_agent_failure(tmp_path, monkeypatch, capsys):
    def fail(self, action):
        raise EnvironmentFailure("simulated service offline")

    monkeypatch.setattr(TicketEnvironment, "step", fail)
    candidate = write_candidate(tmp_path / "reference", asset("support_reference.py"))
    result = evaluate(candidate, Runtime(backend="local"), [17], "support-routing")
    assert result["valid"] is False and result["score"] is None
    assert all(case["status"] == "environment_error" for case in result["cases"])
    assert all(group["assessed"] == 0 for group in result["dimensions"].values())
    with pytest.raises(ValueError, match="valid evaluated score"):
        summarize([{"elapsed_seconds": 1, "evaluation": result}], 10)
    output = tmp_path / "audit"
    assert (
        main(
            [
                "audit",
                "--task",
                "support-routing",
                "--backend",
                "local",
                "--trust-local",
                "--seeds",
                "17",
                "--output",
                str(output),
            ]
        )
        == 2
    )
    assert "Audit: INVALID | Reference: UNASSESSED" in capsys.readouterr().out
    control_audit = json.loads((output / "audit.json").read_text())
    assert control_audit["valid"] is False
    assert control_audit["mutation_score"] is None
    # The no-action policy never calls the unavailable tool service; its unchanged
    # state is still observable. Every policy that reaches the outage is unassessed.
    assert control_audit["killed"] == 1
    assert all(
        row["valid"] is False
        for row in control_audit["mutants"]
        if row["name"] != "claim-without-actions"
    )
    html_path = output / "index.html"
    assert "UNASSESSED" in html_path.read_text()
    assert "SURVIVED" not in html_path.read_text()


def test_cli_support_init_and_evaluate(tmp_path):
    candidate = tmp_path / "reference"
    output = tmp_path / "run"
    assert main(["init", str(candidate), "--task", "support-routing", "--reference"]) == 0
    assert "Support routing" in (candidate / "TASK.md").read_text()
    assert (
        main(
            [
                "evaluate",
                str(candidate),
                "--task",
                "support-routing",
                "--backend",
                "local",
                "--trust-local",
                "--seeds",
                "17",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    report = json.loads((output / "evaluation.json").read_text())
    assert report["task"]["domain"] == "business-tools"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_independent_javascript_policy_uses_same_host_verifier():
    candidate = Path(__file__).resolve().parents[1] / "examples/support-node"
    report = evaluate(candidate, Runtime(backend="local"), [17, 41, 97], "support-routing")
    assert report["resolved"] and len(report["cases"]) == 12
    assert report["runtime"]["command"] == ["node", "main.js"]

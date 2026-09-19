import hashlib

from scripts.handoff_metrics import operation_metrics


def test_repeated_operations_are_counted_without_claiming_they_were_wasted():
    content = "prior program"
    identity = hashlib.sha256(content.encode()).hexdigest()
    events = [
        {
            "name": "write_file",
            "arguments": {"path": path, "content": content},
            "result": {"ok": True},
        }
        for path in ("main.py", "/workspace/main.py")
    ]
    events += [
        {
            "name": "run_command",
            "arguments": {"command": command},
            "result": {"ok": True, "exit_code": code},
        }
        for command, code in (("python3 protocol_probe.py", 1), ("python3 protocol_probe.py", 0))
    ]
    events += [
        {
            "name": "recall_prior_session",
            "arguments": {"query": "prior work"},
            "result": {"status": status},
        }
        for status in ("retrieved", "not_found", "source_unavailable")
    ]
    metrics = operation_metrics(
        {"tool_events": events, "candidate_files": {"main.py": identity}}, identity
    )
    assert metrics["exact_duplicate_writes"] == 1
    assert metrics["unchanged_starter_writes"] == 2
    assert metrics["repeated_command_strings"] == 1
    assert metrics["memory_tool_attempts"] == 3
    assert metrics["retrieved_results"] == 1
    assert metrics["memory_error_results"] == 1
    assert metrics["program_changed"] is False


def test_failed_writes_and_absent_candidates_do_not_count_as_delivered_programs():
    metrics = operation_metrics(
        {
            "tool_events": [
                {
                    "name": "write_file",
                    "arguments": {"path": "../outside", "content": "data"},
                    "result": {"ok": False},
                }
            ],
            "candidate_files": {},
        },
        "0" * 64,
    )
    assert metrics["successful_file_writes"] == 0
    assert metrics["program_changed"] is None

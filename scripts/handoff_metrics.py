"""Recomputable counts of observed operations; these are not estimates of saved work."""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath


def operation_metrics(trial: dict, starter_sha256: str, prior_trial: dict | None = None) -> dict:
    writes, commands = [], []
    unchanged_starter_writes = 0
    bytes_written = 0
    memory_calls = 0
    retrieved = 0
    errors = 0
    for event in trial["tool_events"]:
        arguments, result = event["arguments"], event["result"]
        if event["name"] == "write_file" and result.get("ok") is True:
            path = str(PurePosixPath(arguments["path"]))
            if path.startswith("/workspace/"):
                path = path[len("/workspace/") :]
            content = arguments["content"].encode()
            identity = hashlib.sha256(content).hexdigest()
            writes.append((path, identity))
            bytes_written += len(content)
            unchanged_starter_writes += path == "main.py" and identity == starter_sha256
        if event["name"] == "run_command" and result.get("ok") is True:
            commands.append(arguments["command"].strip())
        if event["name"] in ("recall_prior_session", "read_prior_turns"):
            memory_calls += 1
            retrieved += result.get("status") == "retrieved"
            errors += result.get("status") not in ("retrieved", "not_found")
    prior_commands, prior_writes = set(), set()
    for event in (prior_trial or {}).get("tool_events", []):
        arguments, result = event["arguments"], event["result"]
        if event["name"] == "run_command" and result.get("ok") is True:
            prior_commands.add(arguments["command"].strip())
        if event["name"] == "write_file" and result.get("ok") is True:
            path = str(PurePosixPath(arguments["path"]))
            if path.startswith("/workspace/"):
                path = path[len("/workspace/") :]
            prior_writes.add((path, hashlib.sha256(arguments["content"].encode()).hexdigest()))
    return {
        "successful_file_writes": len(writes),
        "exact_duplicate_writes": len(writes) - len(set(writes)),
        "unchanged_starter_writes": unchanged_starter_writes,
        "bytes_written_including_repeats": bytes_written,
        "command_attempts": len(commands),
        "repeated_command_strings": len(commands) - len(set(commands)),
        "command_attempts_seen_in_prior": sum(command in prior_commands for command in commands)
        if prior_trial is not None
        else None,
        "writes_seen_in_prior": sum(write in prior_writes for write in writes)
        if prior_trial is not None
        else None,
        "memory_tool_attempts": memory_calls,
        "retrieved_results": retrieved,
        "memory_error_results": errors,
        "program_changed": trial["candidate_files"].get("main.py") != starter_sha256
        if trial["candidate_files"]
        else None,
    }

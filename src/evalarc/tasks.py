"""Built-in task definitions. Task selection belongs to the evaluator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from evalarc import coding, support, task


@dataclass(frozen=True)
class TaskDefinition:
    id: str
    version: str
    domain: str
    description: str
    dimensions: dict[str, float]
    generate_cases: Callable
    run_case: Callable
    source_files: tuple[str, ...]
    default_command: tuple[str, ...]
    reference_asset: str
    starter_asset: str
    contract_asset: str


TASKS = {
    "durable-kv": TaskDefinition(
        "durable-kv",
        task.TASK_VERSION,
        "coding",
        "Persistent key-value service",
        task.DIMENSIONS,
        task.generate_cases,
        coding.run_case,
        ("task.py", "coding.py"),
        ("{python}", "-I", "-B", "main.py", "{state}/store.db"),
        "reference.py",
        "starter.py",
        "TASK.md",
    ),
    "support-routing": TaskDefinition(
        "support-routing",
        "0.1.0",
        "business-tools",
        "Route and resolve simulated support tickets",
        support.DIMENSIONS,
        support.generate_cases,
        support.run_case,
        ("task.py", "support.py"),
        ("{python}", "-I", "-B", "main.py"),
        "support_reference.py",
        "support_starter.py",
        "SUPPORT_TASK.md",
    ),
}


def get_task(task_id: str) -> TaskDefinition:
    try:
        return TASKS[task_id]
    except KeyError:
        raise ValueError(f"unknown task {task_id!r}; choose from {', '.join(TASKS)}") from None

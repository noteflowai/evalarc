"""Packaged candidate templates; independent of task grading and evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from evalarc.artifacts import new_run
from evalarc.tasks import get_task

LANGUAGES = ("python", "javascript")


def asset(name: str) -> str:
    return files("evalarc").joinpath("assets", name).read_text(encoding="utf-8")


@dataclass(frozen=True)
class CandidateTemplate:
    filename: str
    source: str
    command: tuple[str, ...] | None = None

    def write(self, path: Path, *, source: str | None = None) -> None:
        """Write into a caller-owned directory; the caller controls publication."""
        (path / self.filename).write_text(
            self.source if source is None else source, encoding="utf-8"
        )
        if self.command is not None:
            (path / "evalarc.toml").write_text(
                f"command = {json.dumps(self.command)}\n", encoding="utf-8"
            )


def candidate_template(
    task_id: str, language: str = "python", *, reference: bool = False
) -> CandidateTemplate:
    task = get_task(task_id)
    if language not in LANGUAGES:
        raise ValueError(f"unknown language {language!r}; choose from {', '.join(LANGUAGES)}")
    name = task.reference_asset if reference else task.starter_asset
    if language == "python":
        return CandidateTemplate("main.py", asset(name))
    command = ("node", "main.js")
    if task_id == "durable-kv":
        command += ("{state}/store.json",)
    return CandidateTemplate("main.js", asset(name.removesuffix(".py") + ".js"), command)


def initialize(
    destination: Path, task_id: str, language: str = "python", *, reference: bool = False
) -> None:
    template = candidate_template(task_id, language, reference=reference)
    contract = asset(get_task(task_id).contract_asset)
    with new_run(destination) as staged:
        template.write(staged)
        (staged / "TASK.md").write_text(contract, encoding="utf-8")
        if language == "javascript":
            (staged / "RUNTIME.md").write_text(asset("JAVASCRIPT.md"), encoding="utf-8")

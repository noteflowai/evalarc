"""Scripted Harbor controls with native ATIF; no model inference or model score."""

from __future__ import annotations

import hashlib
import json
import shlex
from datetime import datetime, timezone
from typing import Literal

from harbor.agents.base import BaseAgent
from harbor.agents.capabilities import AgentCapabilities
from harbor.agents.options import AgentOptions
from harbor.models.trajectories.trajectory import Trajectory

from evalarc.templates import asset

CONTROLS = ("reference", "clock-fault", "detached-answers")


def control_commands(control: str) -> list[str]:
    """Create fully recorded commands; all paths and program bytes are fixed."""
    if control not in CONTROLS:
        raise ValueError("unknown scripted control")
    reference = asset("robot_reference.py")
    fault = reference.replace("USE_CLOCK = True", "USE_CLOCK = False")
    if fault == reference:
        raise ValueError("reference no longer exposes the declared clock control")
    initial = fault if control == "clock-fault" else reference

    def write_program(text: str) -> str:
        script = "from pathlib import Path; Path('main.py').write_text(" + repr(text) + ")"
        return "python3 -c " + shlex.quote(script)

    commands = [
        "python3 -c "
        + shlex.quote(
            "import json, os; from pathlib import Path; "
            "print(json.dumps({'uid': os.getuid(), 'cwd': os.getcwd(), "
            "'network_interfaces': sorted(p.name for p in Path('/sys/class/net').iterdir())})); "
            "assert os.getuid() != 0"
        ),
        write_program(initial),
        "python3 -I -B /workspace/main.py < /workspace/requests.jsonl > /workspace/answers.jsonl",
    ]
    if control == "detached-answers":
        commands.append(write_program(fault))
    commands.append(
        "python3 -c "
        + shlex.quote(
            "import hashlib, json; from pathlib import Path; "
            "print(json.dumps({name: hashlib.sha256(Path(name).read_bytes()).hexdigest() "
            "for name in ('main.py', 'answers.jsonl')}))"
        )
    )
    return commands


class ControlOptions(AgentOptions):
    control: Literal["reference", "clock-fault", "detached-answers"] = "reference"


class ControlAgent(BaseAgent):
    capabilities = AgentCapabilities(atif=True)
    options_model = ControlOptions

    @staticmethod
    def name() -> str:
        return "evalarc-scripted-control"

    def version(self) -> str:
        return "1.0.0"

    async def setup(self, environment) -> None:
        pass

    async def run(self, instruction, environment, context) -> None:
        control = self.options.control
        record = {
            "schema_version": "ATIF-v1.8",
            "session_id": self.session_id,
            "agent": {
                "name": self.name(),
                "version": self.version(),
                "extra": {"control": control, "model_inference": False},
            },
            "steps": [{"step_id": 1, "source": "user", "message": instruction}],
            "notes": (
                "Actual Harbor container executions of a declared scripted control. "
                "Programs are provided fixtures, not model-generated solutions."
            ),
            "extra": {
                "control": control,
                "reference_sha256": hashlib.sha256(asset("robot_reference.py").encode()).hexdigest(),
            },
        }
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        for index, command in enumerate(control_commands(control), 2):
            started = datetime.now(timezone.utc).isoformat()
            result = await environment.exec(command=command, cwd="/workspace", timeout_sec=30)
            call = f"exec-{index}"
            record["steps"].append(
                {
                    "step_id": index,
                    "source": "agent",
                    "timestamp": started,
                    "message": f"Execute scripted {control} control step.",
                    "tool_calls": [
                        {
                            "tool_call_id": call,
                            "function_name": "environment.exec",
                            "arguments": {"command": command, "cwd": "/workspace", "timeout_sec": 30},
                        }
                    ],
                    "observation": {
                        "results": [
                            {
                                "source_call_id": call,
                                "content": json.dumps(
                                    {
                                        "return_code": result.return_code,
                                        "stdout": result.stdout,
                                        "stderr": result.stderr,
                                    }
                                ),
                            }
                        ]
                    },
                }
            )
            # Use the installed upstream model, including its reference/link checks.
            Trajectory.model_validate(record)
            (self.logs_dir / "trajectory.json").write_text(json.dumps(record, indent=2) + "\n")
            if result.return_code:
                raise RuntimeError(f"scripted control command failed: {result.return_code}")
        context.metadata = {"control": control, "scripted": True, "model_inference": False}

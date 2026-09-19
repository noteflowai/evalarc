"""Read-only readiness checks; candidate programs are never executed."""

from __future__ import annotations

import os
import platform
import shutil
import sys
import tempfile
from pathlib import Path

from evalarc import __version__
from evalarc.runner import Runtime, snapshot
from evalarc.tasks import get_task


def diagnose(runtime: Runtime, candidate: Path | None = None, task_id: str = "durable-kv") -> dict:
    checks = []

    def record(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "status": "passed" if passed else "failed", "detail": detail})

    record(
        "host", sys.platform == "linux", f"{platform.system()} · Python {platform.python_version()}"
    )
    task = get_task(task_id)
    try:
        runtime.prepare()
        detail = runtime.image_id if runtime.backend == "docker" else sys.executable
        record("runtime", True, str(detail))
    except (ValueError, OSError) as error:
        record("runtime", False, str(error))
    if candidate is not None:
        try:
            with tempfile.TemporaryDirectory(prefix="evalarc-doctor-") as temporary:
                workspace = Path(temporary) / "candidate"
                snapshot(candidate, workspace)
                configured = runtime.for_candidate(workspace, task.default_command)
                record("candidate", True, "Snapshot and command configuration are valid.")
                if runtime.backend == "local":
                    executable = configured.command[0].replace("{python}", sys.executable)
                    executable = executable.replace("{workspace}", str(workspace))
                    if "/" in executable and not Path(executable).is_absolute():
                        executable = str(workspace / executable)
                    found = shutil.which(executable, path=os.defpath)
                    record(
                        "executable",
                        found is not None,
                        f"Available: {configured.command[0]}"
                        if found
                        else f"Executable not found or not executable: {configured.command[0]}",
                    )
                else:
                    checks.append(
                        {
                            "name": "executable",
                            "status": "not_checked",
                            "detail": "Image inspected; executable checked during execution.",
                        }
                    )
        except (ValueError, OSError) as error:
            record("candidate", False, str(error))
    return {
        "schema_version": "evalarc.doctor.v1",
        "evalarc_version": __version__,
        "backend": runtime.backend,
        "task": task.id,
        "ready": all(check["status"] != "failed" for check in checks),
        "checks": checks,
        "interpretation": "Readiness checks only; no candidate process or task case was run.",
    }

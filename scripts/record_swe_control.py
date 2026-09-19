"""Execute an upstream SWE-bench defect or original fix with recorded isolation."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


class RecordedContainer:
    def __init__(self, container, output: Path, base_commit: str, image_id: str):
        self.container = container
        self.output = output
        self.base_commit = base_commit
        self.image_id = image_id

    def __getattr__(self, name):
        return getattr(self.container, name)

    def start(self):
        result = self.container.start()
        self.container.reload()
        attrs = self.container.attrs
        host = attrs["HostConfig"]
        observed = self.container.exec_run(["git", "rev-parse", "HEAD"], workdir="/testbed")
        observed_commit = observed.output.decode().strip()
        record = {
            "container_id": self.container.id,
            "image_id": attrs["Image"],
            "user": attrs["Config"]["User"],
            "network_mode": host["NetworkMode"],
            "cap_add": host["CapAdd"],
            "cap_drop": host["CapDrop"],
            "security_opt": host["SecurityOpt"],
            "binds": host["Binds"],
            "privileged": host["Privileged"],
            "memory_bytes": host["Memory"],
            "pids_limit": host["PidsLimit"],
            "base_commit": observed_commit,
            "base_check_exit_code": observed.exit_code,
        }
        save(self.output / "container.json", record)
        if (
            attrs["Image"] != self.image_id
            or host["NetworkMode"] != "none"
            or host["CapAdd"]
            or "ALL" not in host["CapDrop"]
            or not any("no-new-privileges" in item for item in host["SecurityOpt"])
            or host["Binds"]
            or host["Privileged"]
            or observed.exit_code
            or observed_commit != self.base_commit
        ):
            raise RuntimeError("actual container differs from the declared isolated base")
        return result


class RecordedContainers:
    def __init__(self, containers, output: Path, base_commit: str, image_id: str):
        self.containers = containers
        self.output = output
        self.base_commit = base_commit
        self.image_id = image_id

    def __getattr__(self, name):
        return getattr(self.containers, name)

    def create(self, *args, **kwargs):
        # SWE-bench adds SYS_ADMIN for browser tasks. These Python controls use
        # its original evaluation API with a separately recorded Docker policy.
        original_caps = kwargs.get("cap_add")
        kwargs.update(
            cap_add=[],
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            network_disabled=True,
            network_mode="none",
            mem_limit=8 * 1024**3,
            pids_limit=512,
        )
        save(
            self.output / "container-policy.json",
            {
                "upstream_requested_cap_add": original_caps,
                "configured_cap_add": [],
                "cap_drop": kwargs["cap_drop"],
                "security_opt": kwargs["security_opt"],
                "network_mode": kwargs["network_mode"],
                "memory_bytes": kwargs["mem_limit"],
                "pids_limit": kwargs["pids_limit"],
                "host_bind_mounts": False,
                "scope": "Scripted upstream control; no model generation.",
            },
        )
        container = self.containers.create(*args, **kwargs)
        return RecordedContainer(container, self.output, self.base_commit, self.image_id)


class RecordedClient:
    def __init__(self, client, output: Path, base_commit: str, image_id: str):
        self.client = client
        self.containers = RecordedContainers(client.containers, output, base_commit, image_id)

    def __getattr__(self, name):
        return getattr(self.client, name)


def run(args) -> dict:
    import docker
    import swebench
    from swebench.harness import run_evaluation
    from swebench.harness.utils import make_test_spec

    if not re.fullmatch(r"swebench/[a-z0-9._/-]+@sha256:[a-f0-9]{64}", args.image):
        raise ValueError("require a reviewed immutable SWE-bench image digest")
    row = json.loads(args.instance.read_text())
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", row["instance_id"]):
        raise ValueError("unsafe upstream instance ID")
    if not re.fullmatch(r"[a-f0-9]{40}", row["base_commit"]):
        raise ValueError("require the full upstream base commit")
    output = args.output.resolve()
    source = args.swe_source.resolve()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    installed = Path(swebench.__file__).parent
    files = {}
    for original in sorted((source / "swebench").rglob("*.py")):
        relative = original.relative_to(source / "swebench")
        actual = installed / relative
        if not actual.is_file() or digest(original) != digest(actual):
            raise ValueError("installed SWE-bench differs from the reviewed checkout")
        files[relative.as_posix()] = digest(actual)
    if not files:
        raise ValueError("SWE-bench source inventory is empty")
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(Path(__file__), output / "recorder.py")
    client = docker.from_env(timeout=1800)
    image = client.images.get(args.image)
    spec = make_test_spec({**row, "image": args.image})
    run_id = "evalarc-" + uuid.uuid4().hex
    candidate = {
        "instance_id": row["instance_id"],
        "model_name_or_path": "upstream-" + args.mode,
        "model_patch": row["patch"] if args.mode == "original-fix" else "",
    }
    save(output / "prediction.json", candidate)
    save(output / "test-spec.json", dataclasses.asdict(spec))
    save(
        output / "runtime.json",
        {
            "swebench_version": swebench.__version__,
            "source_commit": commit,
            "installed_package": str(installed),
            "source_files": files,
            "python": sys.version,
            "executable": sys.executable,
            "source_instance_sha256": digest(args.instance),
            "recorder_sha256": digest(Path(__file__)),
        },
    )
    metadata = {
        "schema": "evalarc.native-swe-control.v1",
        "kind": "scripted-upstream-control-without-model-generation",
        "instance_id": row["instance_id"],
        "base_commit": row["base_commit"],
        "mode": args.mode,
        "skip_patch": args.mode == "original-defect",
        "image": args.image,
        "image_id": image.id,
        "run_id": run_id,
        "timeout_seconds": args.timeout,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
    }
    save(output / "record.json", metadata)
    started = time.monotonic()
    previous = Path.cwd()
    result = None
    try:
        os.chdir(output)
        result = run_evaluation.run_instance(
            spec,
            candidate,
            RecordedClient(client, output, row["base_commit"], image.id),
            run_id,
            timeout=args.timeout,
            skip_patch=metadata["skip_patch"],
        )
        metadata["status"] = "reported" if result else "unreported"
        if result:
            name, report = result
            if name != row["instance_id"]:
                raise ValueError("native result identifies another instance")
            save(output / "report.json", report)
            metadata["native_resolved"] = report[name]["resolved"]
    except BaseException as error:
        metadata["status"] = "error"
        metadata["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        os.chdir(previous)
        metadata["elapsed_seconds"] = time.monotonic() - started
        metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
        save(output / "record.json", metadata)
        client.close()
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", required=True, type=Path)
    parser.add_argument("--swe-source", required=True, type=Path)
    parser.add_argument("--image", required=True)
    parser.add_argument("--mode", choices=("original-defect", "original-fix"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=600)
    arguments = parser.parse_args()
    if arguments.timeout <= 0:
        parser.error("--timeout must be positive")
    record = run(arguments)
    print(json.dumps(record, indent=2))
    if record["status"] != "reported":
        raise SystemExit(2)

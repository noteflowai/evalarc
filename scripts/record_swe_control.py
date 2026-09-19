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

# The pinned upstream wheel excludes these stand-alone collection utilities.
# Their omission is recorded explicitly; installed evaluation code must match.
WHEEL_EXCLUSIONS = frozenset(
    {
        "collect/cleanup/delete_gh_workflows.py",
        "collect/cleanup/remove_envs.py",
        "collect/make_lite/criteria.py",
        "collect/make_lite/make_lite.py",
        "collect/make_repo/call_make_repo.py",
    }
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def verify_installed_source(source: Path, installed: Path) -> dict:
    source_files = {p.relative_to(source).as_posix(): p for p in source.rglob("*.py")}
    installed_files = {p.relative_to(installed).as_posix(): p for p in installed.rglob("*.py")}
    omitted = set(source_files) - set(installed_files)
    if omitted != WHEEL_EXCLUSIONS:
        raise ValueError(f"unexpected omitted SWE-bench files: {sorted(omitted)}")
    if set(installed_files) - set(source_files):
        raise ValueError("installed SWE-bench has unexpected Python files")
    files = {}
    for relative, actual in sorted(installed_files.items()):
        if digest(source_files[relative]) != digest(actual):
            raise ValueError(f"installed SWE-bench differs: {relative}")
        files[relative] = digest(actual)
    if not files or "harness/run_evaluation.py" not in files:
        raise ValueError("SWE-bench runtime source inventory is incomplete")
    return {
        "installed_python_files": files,
        "wheel_omitted_collection_utilities": {
            name: digest(source_files[name]) for name in sorted(omitted)
        },
    }


class RecordedContainer:
    def __init__(self, container, output: Path, base_commit: str, image_id: str, image_head: str):
        self.container = container
        self.output = output
        self.base_commit = base_commit
        self.image_id = image_id
        self.image_head = image_head

    def __getattr__(self, name):
        return getattr(self.container, name)

    def start(self):
        result = self.container.start()
        self.container.reload()
        attrs = self.container.attrs
        host = attrs["HostConfig"]
        observed = self.container.exec_run(["git", "rev-parse", "HEAD"], workdir="/testbed")
        tracked = self.container.exec_run(
            ["git", "status", "--porcelain", "--untracked-files=no"], workdir="/testbed"
        )
        ancestor = self.container.exec_run(
            ["git", "merge-base", "--is-ancestor", self.base_commit, "HEAD"],
            workdir="/testbed",
        )
        initial_diff = self.container.exec_run(
            ["git", "diff", "--binary", self.base_commit, "HEAD"], workdir="/testbed"
        )
        (self.output / "image-base.diff").write_bytes(initial_diff.output)
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
            "mounts": attrs.get("Mounts", []),
            "privileged": host["Privileged"],
            "memory_bytes": host["Memory"],
            "pids_limit": host["PidsLimit"],
            "dataset_base_commit": self.base_commit,
            "image_head": observed_commit,
            "base_check_exit_code": observed.exit_code,
            "base_ancestor_exit_code": ancestor.exit_code,
            "image_base_diff_exit_code": initial_diff.exit_code,
            "image_base_diff_sha256": digest(self.output / "image-base.diff"),
            "initial_tracked_status": tracked.output.decode(),
            "initial_tracked_status_exit_code": tracked.exit_code,
        }
        save(self.output / "container.json", record)
        if (
            attrs["Image"] != self.image_id
            or host["NetworkMode"] != "none"
            or host["CapAdd"]
            or "ALL" not in host["CapDrop"]
            or not any("no-new-privileges" in item for item in host["SecurityOpt"])
            or host["Binds"]
            or attrs.get("Mounts")
            or host["Privileged"]
            or host["Memory"] != 8 * 1024**3
            or host["PidsLimit"] != 512
            or observed.exit_code
            or observed_commit != self.image_head
            or ancestor.exit_code
            or initial_diff.exit_code
            or tracked.exit_code
            or tracked.output.strip()
        ):
            raise RuntimeError("actual container differs from the declared isolated base")
        return result


class RecordedContainers:
    def __init__(self, containers, output: Path, base_commit: str, image_id: str, image_head: str):
        self.containers = containers
        self.output = output
        self.base_commit = base_commit
        self.image_id = image_id
        self.image_head = image_head

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
                "scope": "Native grader; model generation uses a separate container.",
            },
        )
        container = self.containers.create(*args, **kwargs)
        return RecordedContainer(
            container, self.output, self.base_commit, self.image_id, self.image_head
        )


class RecordedClient:
    def __init__(self, client, output: Path, base_commit: str, image_id: str, image_head: str):
        self.client = client
        self.containers = RecordedContainers(
            client.containers, output, base_commit, image_id, image_head
        )

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
    if not re.fullmatch(r"[a-f0-9]{40}", args.image_head):
        raise ValueError("require the reviewed image's full initial commit")
    output = args.output.resolve()
    source = args.swe_source.resolve()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    subprocess.run(
        ["git", "diff", "--exit-code", "--quiet", "HEAD", "--", "swebench"],
        cwd=source,
        check=True,
    )
    tracked = set(
        subprocess.check_output(["git", "ls-files", "-z", "swebench"], cwd=source)
        .decode()
        .split("\0")
    )
    if any(
        p.relative_to(source).as_posix() not in tracked for p in (source / "swebench").rglob("*.py")
    ):
        raise ValueError("upstream checkout contains untracked Python sources")
    installed = Path(swebench.__file__).parent
    inventory = verify_installed_source(source / "swebench", installed)
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(Path(__file__), output / "recorder.py")
    client = docker.from_env(timeout=1800)
    image = client.images.get(args.image)
    spec = make_test_spec({**row, "image": args.image})
    run_id = "evalarc-" + uuid.uuid4().hex
    model_patch = (
        args.candidate_patch.read_bytes().decode("utf-8")
        if args.mode == "candidate"
        else row["patch"]
        if args.mode == "original-fix"
        else ""
    )
    candidate = {
        "instance_id": row["instance_id"],
        "model_name_or_path": (
            "recorded-candidate" if args.mode == "candidate" else "upstream-" + args.mode
        ),
        "model_patch": model_patch,
    }
    save(output / "prediction.json", candidate)
    save(output / "test-spec.json", dataclasses.asdict(spec))
    save(
        output / "runtime.json",
        {
            "swebench_version": swebench.__version__,
            "source_commit": commit,
            "installed_package": str(installed),
            "source_inventory": inventory,
            "python": sys.version,
            "executable": sys.executable,
            "source_instance_sha256": digest(args.instance),
            "recorder_sha256": digest(Path(__file__)),
        },
    )
    metadata = {
        "schema": "evalarc.native-swe-control.v1",
        "kind": (
            "recorded-candidate-native-evaluation"
            if args.mode == "candidate"
            else "scripted-upstream-control-without-model-generation"
        ),
        "instance_id": row["instance_id"],
        "base_commit": row["base_commit"],
        "image_head": args.image_head,
        "mode": args.mode,
        "skip_patch": not model_patch,
        "candidate_patch_sha256": hashlib.sha256(model_patch.encode()).hexdigest(),
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
            RecordedClient(client, output, row["base_commit"], image.id, args.image_head),
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
    parser.add_argument("--image-head", required=True)
    parser.add_argument(
        "--mode", choices=("original-defect", "original-fix", "candidate"), required=True
    )
    parser.add_argument("--candidate-patch", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=600)
    arguments = parser.parse_args()
    if arguments.timeout <= 0:
        parser.error("--timeout must be positive")
    if (arguments.mode == "candidate") != bool(arguments.candidate_patch):
        parser.error("--candidate-patch is required only in candidate mode")
    record = run(arguments)
    print(json.dumps(record, indent=2))
    if record["status"] != "reported":
        raise SystemExit(2)

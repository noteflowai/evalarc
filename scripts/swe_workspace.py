"""Isolated SWE source snapshots and Git patches without exposing Git history."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import tarfile
import threading
import time
import uuid
import zlib
from pathlib import Path, PurePosixPath

PYTHON = "/opt/miniconda3/envs/testbed/bin/python"
CACHE_DIRS = {".pytest_cache", "__pycache__", ".hypothesis", ".mypy_cache"}
OUTPUT_LIMIT = 24_000


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_path(name, root="testbed"):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or any(ord(c) < 32 for c in name):
        raise ValueError("unsafe source archive path")
    parts = path.parts
    if parts and root and parts[0] == root:
        parts = parts[1:]
    return "/".join(parts)


def retained(name, tracked):
    parts = PurePosixPath(name).parts
    if ".git" in parts:
        return False
    if name in tracked:
        return True
    return not (set(parts) & CACHE_DIRS or name.endswith((".pyc", ".pyo")))


def store_blob(repository, data):
    content = b"blob " + str(len(data)).encode() + b"\0" + data
    oid = hashlib.sha1(content).hexdigest()
    target = Path(repository) / "objects" / oid[:2] / oid[2:]
    if not target.exists():
        target.parent.mkdir(exist_ok=True)
        try:
            with target.open("xb") as stream:
                stream.write(zlib.compress(content))
        except FileExistsError:
            pass
    return oid


def index_archive(archive_path, repository, tracked, *, cleaned=None, root="testbed"):
    entries, removed = {}, []
    destination = tarfile.open(cleaned, "w") if cleaned else None
    try:
        with tarfile.open(archive_path) as archive:
            for member in archive:
                name = source_path(member.name, root)
                if not name:
                    continue
                if not retained(name, tracked):
                    removed.append(name)
                    continue
                if name in entries or len(entries) >= 20_000:
                    raise ValueError("duplicate or excessive source files")
                if member.isdir():
                    data = None
                elif member.issym():
                    data = member.linkname.encode("utf-8")
                elif member.isfile() or member.islnk():
                    if member.islnk():
                        target = source_path(member.linkname, root)
                        if not retained(target, tracked):
                            raise ValueError("source hard link targets excluded history")
                    data = archive.extractfile(member).read(128 * 1024**2 + 1)
                    if len(data) > 128 * 1024**2:
                        raise ValueError("individual source file exceeds 128 MiB")
                else:
                    raise ValueError("source archive contains a special device")
                if data is not None:
                    entries[name] = {
                        "mode": "120000"
                        if member.issym()
                        else "100755"
                        if member.mode & 0o111
                        else "100644",
                        "blob": store_blob(repository, data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "bytes": len(data),
                    }
                if destination:
                    entry = copy.copy(member)
                    entry.name = name
                    entry.uid = entry.gid = 65534
                    entry.uname = entry.gname = ""
                    entry.mode |= 0o200
                    if member.islnk():
                        entry.type = tarfile.REGTYPE
                        entry.linkname = ""
                        entry.size = len(data)
                    import io

                    destination.addfile(entry, io.BytesIO(data) if entry.isfile() else None)
    finally:
        if destination:
            destination.close()
    return entries, removed


def tree(repository, entries, index):
    environment = os.environ.copy()
    environment["GIT_INDEX_FILE"] = str(Path(index).resolve())
    command = ["git", "--git-dir", str(repository)]
    subprocess.run(command + ["read-tree", "--empty"], env=environment, check=True)
    payload = b"".join(
        f"{value['mode']} {value['blob']}\t{name}\0".encode()
        for name, value in sorted(entries.items())
    )
    subprocess.run(
        command + ["update-index", "-z", "--index-info"], input=payload, env=environment, check=True
    )
    return subprocess.check_output(command + ["write-tree"], env=environment, text=True).strip()


def patch(repository, before, after):
    return subprocess.check_output(
        [
            "git",
            "--git-dir",
            str(repository),
            "diff",
            "--binary",
            "--full-index",
            "--no-ext-diff",
            before,
            after,
            "--",
        ]
    )


def prepare(client, image, output):
    output = Path(output)
    output.mkdir(exist_ok=False, parents=True)
    objects = output / "objects.git"
    subprocess.run(
        ["git", "init", "--bare", "--object-format=sha1", str(objects)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    source = client.containers.create(
        image["image"],
        command=["tail", "-f", "/dev/null"],
        network_mode="none",
        cap_drop=["ALL"],
        security_opt=["no-new-privileges:true"],
    )
    try:
        source.start()
        source.reload()
        if source.attrs["Image"] != image["image_id"]:
            raise ValueError("source image digest changed")
        head = source.exec_run(["git", "rev-parse", "HEAD"], workdir="/testbed")
        if head.exit_code or head.output.decode().strip() != image["image_head"]:
            raise ValueError("source image head changed")
        clean = source.exec_run(
            ["git", "diff", "--exit-code", "--quiet", "HEAD", "--"], workdir="/testbed"
        )
        ancestor = source.exec_run(
            ["git", "merge-base", "--is-ancestor", image["base_commit"], "HEAD"],
            workdir="/testbed",
        )
        if clean.exit_code or ancestor.exit_code:
            raise ValueError("source is dirty or does not descend from the dataset base")
        listing = source.exec_run(["git", "ls-files", "-z"], workdir="/testbed")
        if listing.exit_code:
            raise ValueError("cannot inventory tracked source paths")
        tracked = listing.output.decode().strip("\0").split("\0")
        staged = source.exec_run(["git", "ls-files", "--stage", "-z"], workdir="/testbed")
        if staged.exit_code:
            raise ValueError("cannot inventory source submodules")
        submodules = {}
        for item in staged.output.decode().strip("\0").split("\0"):
            metadata, name = item.split("\t", 1)
            mode, oid, _ = metadata.split()
            if mode == "160000":
                submodules[name] = oid
        stream, _ = source.get_archive("/testbed")
        with (output / "original.tar").open("wb") as handle:
            for chunk in stream:
                handle.write(chunk)
    finally:
        source.remove(force=True)
    entries, removed = index_archive(
        output / "original.tar", objects, tracked, cleaned=output / "workspace.tar"
    )
    if set(tracked) - set(entries) - set(submodules):
        raise ValueError("prepared snapshot omitted tracked source files")
    if any(not any(name.startswith(root + "/") for name in entries) for root in submodules):
        raise ValueError("prepared snapshot omitted an initialized source submodule")
    baseline = tree(objects, entries, output / "baseline.index")
    record = {
        **image,
        "tracked": tracked,
        "submodules": submodules,
        "entries": entries,
        "removed": removed,
        "baseline_tree": baseline,
        "workspace_sha256": sha(output / "workspace.tar"),
        "original_archive_sha256": sha(output / "original.tar"),
    }
    save(output / "source.json", record)
    return record


class Workspace:
    def __init__(self, client, prepared, output):
        self.client, self.prepared = client, Path(prepared)
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        self.source = json.loads((self.prepared / "source.json").read_text())
        self.container = None
        self.counter = 0

    def __enter__(self):
        if sha(self.prepared / "workspace.tar") != self.source["workspace_sha256"]:
            raise ValueError("prepared source archive changed")
        self.container = self.client.containers.create(
            self.source["image"],
            command=["tail", "-f", "/dev/null"],
            name="evalarc-swe-generation-" + uuid.uuid4().hex,
            user="65534:65534",
            working_dir="/testbed",
            read_only=True,
            network_mode="none",
            network_disabled=True,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            mem_limit=8 * 1024**3,
            nano_cpus=2_000_000_000,
            pids_limit=256,
            tmpfs={
                "/testbed": "rw,exec,nosuid,nodev,size=2g,uid=65534,gid=65534,mode=0755",
                "/tmp": "rw,nosuid,nodev,size=128m,mode=1777",
            },
            environment={
                "HOME": "/tmp",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PATH": (
                    "/opt/miniconda3/envs/testbed/bin:/opt/miniconda3/bin:"
                    "/usr/local/bin:/usr/bin:/bin"
                ),
            },
        )
        try:
            self.container.start()
            with (self.prepared / "workspace.tar").open("rb") as handle:
                result = subprocess.run(
                    [
                        "docker",
                        "exec",
                        "-i",
                        "--user",
                        "65534:65534",
                        self.container.id,
                        "tar",
                        "--no-same-owner",
                        "-xf",
                        "-",
                        "-C",
                        "/testbed",
                    ],
                    stdin=handle,
                    capture_output=True,
                    timeout=120,
                )
            (self.output / "bootstrap.stderr").write_bytes(result.stderr)
            if result.returncode:
                raise RuntimeError("source bootstrap failed")
            self.container.reload()
            attributes = self.container.attrs
            host = attributes["HostConfig"]
            if (
                attributes["Image"] != self.source["image_id"]
                or attributes["Config"]["User"] != "65534:65534"
                or host["NetworkMode"] != "none"
                or not host["ReadonlyRootfs"]
                or host["CapAdd"]
                or host["CapDrop"] != ["ALL"]
                or host["Binds"]
                or host["Privileged"]
                or attributes.get("Mounts")
                or host["Memory"] != 8 * 1024**3
                or host["PidsLimit"] != 256
                or host["NanoCpus"] != 2_000_000_000
                or not any("no-new-privileges" in x for x in host["SecurityOpt"])
            ):
                raise ValueError("actual workspace isolation differs from the plan")
            probe = self.container.exec_run(
                [
                    PYTHON,
                    "-c",
                    "import os,json;from pathlib import Path;"
                    "print(json.dumps({'uid':os.getuid(),'git':Path('/testbed/.git').exists(),"
                    "'status':[s for s in Path('/proc/self/status').read_text().splitlines()"
                    " if s.startswith(('CapEff:','NoNewPrivs:'))]}))",
                ]
            )
            observed = json.loads(probe.output)
            status = dict(line.split(":", 1) for line in observed["status"])
            if (
                probe.exit_code
                or observed["uid"] != 65534
                or observed["git"]
                or int(status["CapEff"].strip(), 16) != 0
                or status["NoNewPrivs"].strip() != "1"
            ):
                raise ValueError("actual process identity differs from the plan")
            save(
                self.output / "container.json",
                {
                    "id": self.container.id,
                    "image_id": attributes["Image"],
                    "user": attributes["Config"]["User"],
                    "host_config": host,
                    "observed": observed,
                    "workspace_sha256": self.source["workspace_sha256"],
                },
            )
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        if self.container:
            self.container.remove(force=True)
            self.container = None

    def execute(self, command, timeout=30):
        self.counter += 1
        prefix = self.output / f"command-{self.counter:03}"
        # The outer reader remains bounded even when candidate output is excessive.
        process = subprocess.Popen(
            [
                "docker",
                "exec",
                self.container.id,
                "timeout",
                "-k",
                "2",
                str(timeout),
                "/bin/bash",
                "-c",
                command,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        chunks, byte_count = [], 0

        def read():
            nonlocal byte_count
            with prefix.with_suffix(".output").open("wb") as handle:
                while chunk := process.stdout.read(65536):
                    available = max(0, 1024**2 - byte_count)
                    handle.write(chunk[:available])
                    if byte_count < OUTPUT_LIMIT:
                        chunks.append(chunk[: OUTPUT_LIMIT - byte_count])
                    byte_count += len(chunk)

        thread = threading.Thread(target=read, daemon=True)
        thread.start()
        started = time.monotonic()
        try:
            code = process.wait(timeout=timeout + 10)
        except subprocess.TimeoutExpired:
            self.container.kill()
            process.kill()
            process.wait()
            raise RuntimeError("workspace command did not respect its deadline")
        finally:
            thread.join(timeout=5)
            process.stdout.close()
        if thread.is_alive():
            raise RuntimeError("workspace output stream did not close")
        result = {
            "exit_code": code,
            "output": b"".join(chunks).decode(errors="replace"),
            "output_bytes": byte_count,
            "output_truncated": byte_count > OUTPUT_LIMIT,
            "archive_truncated": byte_count > 1024**2,
            "elapsed_seconds": time.monotonic() - started,
        }
        save(prefix.with_suffix(".json"), {"command": command, **result})
        return result

    def export(self, name, timeout=90):
        destination = self.output / name
        destination.mkdir()
        with (destination / "workspace.tar").open("wb") as handle:
            exported = subprocess.run(
                [
                    "docker",
                    "exec",
                    self.container.id,
                    "timeout",
                    "-k",
                    "2",
                    str(timeout),
                    "tar",
                    "-cf",
                    "-",
                    "-C",
                    "/testbed",
                    ".",
                ],
                stdout=handle,
                stderr=subprocess.PIPE,
                timeout=timeout + 10,
            )
        (destination / "export.stderr").write_bytes(exported.stderr)
        if exported.returncode:
            raise RuntimeError("live workspace export failed or changed while being read")
        objects = self.prepared / "objects.git"
        entries, excluded = index_archive(
            destination / "workspace.tar", objects, self.source["tracked"], root=None
        )
        after = tree(objects, entries, destination / "index")
        difference = patch(objects, self.source["baseline_tree"], after)
        (destination / "candidate.patch").write_bytes(difference)
        changed = [
            path
            for path in sorted(set(entries) | set(self.source["entries"]))
            if entries.get(path) != self.source["entries"].get(path)
        ]
        record = {
            "baseline_tree": self.source["baseline_tree"],
            "candidate_tree": after,
            "changed_paths": changed,
            "excluded_paths": excluded,
            "patch_sha256": sha(destination / "candidate.patch"),
            "archive_sha256": sha(destination / "workspace.tar"),
            "entries": entries,
            "patch_bytes": len(difference),
        }
        save(destination / "snapshot.json", record)
        return record, difference

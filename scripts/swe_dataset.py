"""Build or publish the checked mixed-source independent SWE dataset."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

if __package__:
    from .build_swe_report import ARCHIVE, ROOT, digest, read, verify, write
    from .hf_readback import verify_public_files
else:
    from build_swe_report import ARCHIVE, ROOT, digest, read, verify, write
    from hf_readback import verify_public_files

SCHEMA = "evalarc.independent-swe-dataset.v1"
SOURCE = "https://github.com/noteflowai/evalarc"
REPO = "glayguo/evalarc-independent-swe"


def check(folder):
    manifest = read(folder / "manifest.json")
    if manifest["schema"] != SCHEMA or manifest["source_repository"] != SOURCE:
        raise ValueError("unexpected independent SWE dataset source")
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    if actual != set(manifest["files"]) | {"manifest.json"}:
        raise ValueError("dataset inventory differs")
    for name, expected in manifest["files"].items():
        if digest((folder / name).read_bytes()) != expected:
            raise ValueError("dataset file changed")
    rows = [json.loads(line) for line in (folder / "data/attempts.jsonl").read_text().splitlines()]
    if len(rows) != 36 or len({row["id"] for row in rows}) != 36:
        raise ValueError("dataset does not preserve all 36 slots")
    source = ROOT / "examples/independent-swe"
    verified = verify(source)
    if (
        manifest["config_sha256"] != verified["config_sha256"]
        or (folder / "data/attempts.jsonl").read_bytes() != (source / "data.jsonl").read_bytes()
        or digest((folder / ARCHIVE).read_bytes()) != digest((source / ARCHIVE).read_bytes())
    ):
        raise ValueError("dataset projections differ from the verified native evidence")
    return manifest


def build(output):
    source = ROOT / "examples/independent-swe"
    summary = verify(source)
    output.mkdir(parents=True, exist_ok=False)
    (output / "data").mkdir()
    shutil.copyfile(source / "data.jsonl", output / "data/attempts.jsonl")
    shutil.copyfile(source / ARCHIVE, output / ARCHIVE)
    shutil.copyfile(source / "README.md", output / "METHODS.md")
    shutil.copyfile(source / "README.zh-CN.md", output / "METHODS.zh-CN.md")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=normal"], cwd=ROOT, text=True
        ).strip()
    )
    card = f"""---
language:
- en
- zh
license: other
license_name: mixed-upstream-research-evidence
license_link: https://huggingface.co/datasets/{REPO}/blob/main/METHODS.md#sources-and-licenses
task_categories:
- text-generation
tags:
- evaluation
- software-engineering
- agents
- mcp
- swe-bench
size_categories:
- n<1K
configs:
- config_name: attempts
  data_files:
  - split: train
    path: data/attempts.jsonl
---

# Independent-source SWE workflow records

36 Qwen3-8B attempts compare four fixed workflows on three public SWE-bench
Verified tasks. There are no accepted attempts: 31 have assessable native
reports and five retain an upstream infrastructure flag, so their task outcome
is uncertain. Eight attempts produced nonempty patches. One generation request
has incomplete usage.

[Inspect the interactive report](https://noteflowai.github.io/evalarc/independent-swe/index.html)
· [English method](METHODS.md) · [中文方法](METHODS.zh-CN.md)
· [Offline review and exact raw records]({ARCHIVE})

This dataset reports the recorded experiment, not a general model leaderboard or
a demonstrated skill benefit. Three repeated seeds do not create additional
independent tasks. Direct/MCP workflows preload identical guidance; unrelated
MCP content matches its token count. Skill delivery is distinct from task
acceptance.

The `disposition` column distinguishes `not_accepted` from `unavailable`.
`upstream_resolved` retains the raw upstream boolean even when an infrastructure
flag prevents an assessed result. `usage_complete=false` means token and time
columns include recorded responses only. The 95% aggregate gate is an explicitly
declared illustrative rule; missing evidence stays unknown.

Five pytest logs contain both offline build-dependency installation failures and
candidate errors. The original `network_unreachable` label is preserved and does
not establish a single cause.

Source release: [{commit}]({SOURCE}/tree/{commit}).
Frozen execution code: `{summary["recorder_commit"]}`.
Fixed configuration SHA-256: `{summary["config_sha256"]}`.

The ZIP contains raw requests, responses, native reports, six original upstream
controls, patches, frozen recorder/provider source and attribution. Open its
`review/index.html` directly for offline browsing. Images, installed dependencies,
filesystem tar snapshots and model weights are not included.

## Source attribution

The dataset derives from `SWE-bench/SWE-bench_Verified` revision
`78f471bf655a3137b2e8a75af1501690ec009ec3`, with native evaluator commit
`02e7a74ffd0b707aab73d203fe87bdc7c76afc8e`.
EvalArc's recorder code is MIT; upstream issue text, code excerpts and test
material keep their respective attribution and license boundaries. Project
license texts are in the archive. See METHODS.md before redistributing material.
"""
    (output / "README.md").write_text(card)
    write(
        output / "manifest.json",
        {
            "schema": SCHEMA,
            "source_repository": SOURCE,
            "source_commit": commit,
            "source_dirty": dirty,
            "row_count": 36,
            "config_sha256": summary["config_sha256"],
            "files": {
                p.relative_to(output).as_posix(): digest(p.read_bytes())
                for p in sorted(output.rglob("*"))
                if p.is_file()
            },
        },
    )
    return check(output)


def publish(folder):
    manifest = check(folder)
    if manifest["source_dirty"]:
        raise ValueError("commit the source before publication")
    if manifest["source_commit"] != os.environ.get("GITHUB_SHA", manifest["source_commit"]):
        raise ValueError("dataset source differs from the current CI source")
    from huggingface_hub import DatasetCard, HfApi, hf_hub_download
    from huggingface_hub.errors import EntryNotFoundError

    DatasetCard.load(folder / "README.md").validate()
    api = HfApi()
    if api.whoami()["name"] != REPO.split("/")[0]:
        raise ValueError("publication requires the dataset owner's account")
    if not api.repo_exists(REPO, repo_type="dataset"):
        api.create_repo(REPO, repo_type="dataset", private=False)
    info = api.dataset_info(REPO)
    if info.private or info.gated:
        raise ValueError("existing dataset must be public and ungated")
    try:
        prior = read(hf_hub_download(REPO, "manifest.json", repo_type="dataset", revision=info.sha))
    except EntryNotFoundError:
        if set(api.list_repo_files(REPO, repo_type="dataset", revision=info.sha)) - {
            ".gitattributes"
        }:
            raise ValueError("existing dataset has no ownership manifest") from None
    else:
        if prior["schema"] != SCHEMA or prior["source_repository"] != SOURCE:
            raise ValueError("existing dataset belongs to another source")
    allowed = sorted(set(manifest["files"]) | {"manifest.json"})
    commit = api.upload_folder(
        repo_id=REPO,
        repo_type="dataset",
        folder_path=folder,
        allow_patterns=allowed,
        parent_commit=info.sha,
        commit_message="Publish checked independent SWE records " + manifest["source_commit"][:12],
    )
    verified = verify_public_files(folder, REPO, "dataset", commit.oid, allowed)
    return {
        "repo_id": REPO,
        "hub_commit": commit.oid,
        "source_commit": manifest["source_commit"],
        "public_files_verified": verified,
        "row_count": 36,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    print(json.dumps(publish(args.output) if args.publish else build(args.output), indent=2))

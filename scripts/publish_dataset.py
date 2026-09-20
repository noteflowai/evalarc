"""Publish a checked casebook artifact, then verify it without credentials."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from build_dataset import SCHEMA, verify
from build_site import SOURCE
from hf_readback import verify_public_files


def publish(folder: Path, repo_id: str) -> dict:
    folder = folder.resolve()
    record = verify(folder)
    if record["source_dirty"]:
        raise ValueError("Commit the source before publishing")
    if record["source_commit"] != os.environ.get("GITHUB_SHA", record["source_commit"]):
        raise ValueError("Bundle differs from the CI source commit")
    from huggingface_hub import DatasetCard, HfApi, hf_hub_download
    from huggingface_hub.errors import EntryNotFoundError

    DatasetCard.load(folder / "README.md").validate()
    api = HfApi()
    identity = api.whoami()
    if repo_id.split("/")[0] != identity["name"]:
        raise ValueError("Casebook publication requires the authenticated owner's namespace")
    if not api.repo_exists(repo_id, repo_type="dataset"):
        api.create_repo(repo_id, repo_type="dataset", private=False)
    info = api.dataset_info(repo_id)
    if info.private or info.gated:
        raise ValueError("Existing casebook must already be public and ungated")
    previous = set()
    try:
        old_path = hf_hub_download(repo_id, "manifest.json", repo_type="dataset", revision=info.sha)
    except EntryNotFoundError:
        # Only bootstrap a new, empty dataset owned by this account. This also
        # makes a retry after create_repo safe without overwriting existing data.
        files = api.list_repo_files(repo_id, repo_type="dataset", revision=info.sha)
        if set(files) - {".gitattributes"}:
            raise ValueError("Existing dataset has no casebook ownership manifest") from None
    else:
        old = json.loads(Path(old_path).read_text())
        if old.get("schema") != SCHEMA or old.get("source_repository") != SOURCE:
            raise ValueError("Existing dataset belongs to another source")
        previous = set(old["files"])
        for name in previous:
            path = Path(name)
            if path.is_absolute() or ".." in path.parts or any(c in name for c in "*?["):
                raise ValueError("Unsafe path in previous manifest")
    allowed = sorted(set(record["files"]) | {"manifest.json"})
    commit = api.upload_folder(
        repo_id=repo_id,
        repo_type="dataset",
        folder_path=folder,
        allow_patterns=allowed,
        delete_patterns=sorted(previous - set(allowed)) or None,
        parent_commit=info.sha,
        commit_message="Publish verified EvalArc casebook " + record["source_commit"][:12],
    )
    verified = verify_public_files(folder, repo_id, "dataset", commit.oid, allowed)
    return {
        "repo_id": repo_id,
        "source_commit": record["source_commit"],
        "hub_commit": commit.oid,
        "verified_public_files": verified,
        "row_counts": record["row_counts"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--repo-id", default="glayguo/evalarc-casebook")
    args = parser.parse_args()
    print(json.dumps(publish(args.bundle, args.repo_id), indent=2))

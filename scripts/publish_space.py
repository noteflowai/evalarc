"""Publish a verified bundle and read every uploaded file back anonymously."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from build_site import MANIFEST, SOURCE, verify
from hf_readback import verify_public_files


def publish(folder: Path, repo_id: str) -> dict:
    from huggingface_hub import HfApi, SpaceCard, hf_hub_download
    from huggingface_hub.errors import EntryNotFoundError

    folder = folder.resolve()
    record = verify(folder)
    if record["source_dirty"]:
        raise ValueError("Commit the source before publishing")
    expected = os.environ.get("GITHUB_SHA", record["source_commit"])
    if record["source_commit"] != expected:
        raise ValueError("Bundle differs from the CI source commit")
    SpaceCard.load(folder / "README.md").validate()
    api = HfApi()
    api.whoami()
    receipt = folder.parent / (".created-" + repo_id.replace("/", "--") + ".json")
    if not api.repo_exists(repo_id, repo_type="space"):
        api.create_repo(repo_id, repo_type="space", private=False, space_sdk="static")
        info = api.space_info(repo_id)
        receipt.write_text(json.dumps({"repo_id": repo_id, "initial_head": info.sha}))
        previous = set()
    else:
        info = api.space_info(repo_id)
        if info.sdk != "static" or info.private:
            raise ValueError("Existing Space must already be public and static")
        try:
            old_path = hf_hub_download(repo_id, MANIFEST, repo_type="space", revision=info.sha)
        except EntryNotFoundError:
            created = json.loads(receipt.read_text()) if receipt.exists() else {}
            if created != {"repo_id": repo_id, "initial_head": info.sha}:
                raise ValueError("Existing Space has no EvalArc ownership manifest") from None
            previous = set()
        else:
            old = json.loads(Path(old_path).read_text())
            if old["source_repository"] != SOURCE:
                raise ValueError("Existing Space belongs to another source repository")
            previous = set(old["files"])
            for name in previous:
                path = Path(name)
                if path.is_absolute() or ".." in path.parts or any(c in name for c in "*?["):
                    raise ValueError("Unsafe path in previous manifest")
    allowed = sorted(set(record["files"]) | {MANIFEST})
    commit = api.upload_folder(
        repo_id=repo_id,
        repo_type="space",
        folder_path=folder,
        allow_patterns=allowed,
        delete_patterns=sorted(previous - set(allowed)) or None,
        parent_commit=info.sha,
        commit_message="Publish verified EvalArc " + record["source_commit"][:12],
    )
    verified = verify_public_files(folder, repo_id, "space", commit.oid, allowed)
    return {
        "repo_id": repo_id,
        "source_commit": record["source_commit"],
        "hub_commit": commit.oid,
        "verified_public_files": verified,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--repo-id", default="glayguo/evalarc")
    args = parser.parse_args()
    print(json.dumps(publish(args.bundle, args.repo_id), indent=2))

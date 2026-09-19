"""Recompute both archived skill payloads with the exact local Qwen tokenizer."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def recompute(source: Path, tokenizer_path: Path) -> dict:
    from transformers import AutoTokenizer

    match = json.loads((source / "preparation/match.json").read_text())
    for name, identity in match["tokenizer_files"].items():
        if Path(name).name != name:
            raise ValueError("tokenizer filename must be local")
        if hashlib.sha256((tokenizer_path / name).read_bytes()).hexdigest() != identity:
            raise ValueError(f"tokenizer bytes differ: {name}")
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_path, local_files_only=True)
    conditions = {}
    for name in ("relevant", "neutral"):
        serialized = json.dumps(match[name]["view"])
        ids = tokenizer.encode(serialized, add_special_tokens=False)
        if len(ids) != match["model_visible_open_skill_tokens"]:
            raise ValueError("native tokenizer does not reproduce the declared length")
        conditions[name] = {
            "serialized_sha256": hashlib.sha256(serialized.encode()).hexdigest(),
            "token_count": len(ids),
            "token_ids": ids,
        }
    return {
        "schema": "evalarc.skill-context-tokenization.v1",
        "conditions": conditions,
        "tokenizer_files": match["tokenizer_files"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--tokenizer", required=True, type=Path)
    parser.add_argument("--write", action="store_true", help="Write a new receipt; never overwrite")
    args = parser.parse_args()
    receipt = recompute(args.source, args.tokenizer)
    path = args.source / "tokenization-check.json"
    if args.write:
        with path.open("x") as stream:
            stream.write(json.dumps(receipt, indent=2) + "\n")
    elif json.loads(path.read_text()) != receipt:
        raise ValueError("recorded native tokenization differs from recomputation")
    print(json.dumps({name: value["token_count"] for name, value in receipt["conditions"].items()}))

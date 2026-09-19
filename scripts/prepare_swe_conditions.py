"""Freeze identical direct/MCP guidance and a tokenizer-matched unrelated control."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from scripts.record_skill_impact import Bridge
from scripts.swe_workspace import save


def opened(bridge_path, route, pool):
    bridge = Bridge(bridge_path, route, pool)
    try:
        reply = bridge.call("open_skill", {"name": "engineering-change-review"})
        if reply.get("error"):
            raise ValueError(reply["error"])
        return {"ready": bridge.ready, "reply": reply}
    finally:
        bridge.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skill", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--bridge", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    expected = json.loads(args.selection.read_text())["skill_sha256"]
    if hashlib.sha256(args.skill.read_bytes()).hexdigest() != expected:
        raise ValueError("generic guidance differs from the pre-selection frozen skill")
    args.output.mkdir(exist_ok=False)
    related = args.output / "related" / "engineering-change-review"
    neutral = args.output / "unrelated" / "engineering-change-review"
    related.mkdir(parents=True)
    neutral.mkdir(parents=True)
    shutil.copyfile(args.skill, related / "SKILL.md")
    direct = opened(args.bridge, "direct", related.parent)
    mcp = opened(args.bridge, "mcp", related.parent)
    if direct["reply"]["view"] != mcp["reply"]["view"]:
        raise ValueError("direct and MCP delivery changed the model-facing object")

    def count(view):
        return len(tokenizer.encode(json.dumps(view), add_special_tokens=False))

    target = count(direct["reply"]["view"])
    header = (
        "---\nname: engineering-change-review\n"
        "description: Unrelated reference notes about an imaginary museum collection.\n---\n\n"
        "# Collection reference\n\n"
        "This fictional collection contains ceramic bowls, linen labels and wooden drawers. "
        "Amber glaze appears on the bowls. The cabinet doors have brass handles. "
        "Paper labels describe shapes and colors. These notes describe objects only.\n\n"
    )
    words = "amber pottery linen labels cedar drawers brass handles paper ivory frames".split()
    length, attempts = 80, []
    for attempt in range(300):
        body = " ".join(words[index % len(words)] for index in range(length))
        (neutral / "SKILL.md").write_text(header + body + f"\nCollection entry {attempt}.\n")
        candidate = opened(args.bridge, "direct", neutral.parent)
        measured = count(candidate["reply"]["view"])
        attempts.append({"attempt": attempt, "words": length, "tokens": measured})
        if measured == target:
            break
        length = max(0, length + target - measured)
    else:
        raise ValueError("could not match the unrelated control's delivered token length")
    neutral_mcp = opened(args.bridge, "mcp", neutral.parent)
    if (
        neutral_mcp["reply"]["view"] != candidate["reply"]["view"]
        or count(neutral_mcp["reply"]["view"]) != target
    ):
        raise ValueError("the actual MCP unrelated payload differs from its frozen view")
    for name, record in [
        ("related-direct", direct),
        ("related-mcp", mcp),
        ("unrelated-mcp", neutral_mcp),
    ]:
        save(args.output / (name + ".json"), record)
    for name, record in [("related", mcp), ("unrelated", neutral_mcp)]:
        save(args.output / (name + "-pins.json"), record["ready"]["pins"])
    save(
        args.output / "conditions.json",
        {
            "name": "engineering-change-review",
            "model": str(args.model),
            "skill_sha256": expected,
            "delivered_tokens": target,
            "related": direct["reply"]["view"],
            "unrelated": candidate["reply"]["view"],
            "neutral_preparation": attempts,
            "scope": (
                "Instruction-only workflow preloads. The common experimental name fixes call shape."
            ),
        },
    )
    print(
        json.dumps(
            {
                "direct_mcp_equal": True,
                "delivered_tokens": target,
                "neutral_preparation_attempts": len(attempts),
            }
        )
    )


if __name__ == "__main__":
    main()

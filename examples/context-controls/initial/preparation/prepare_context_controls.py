"""Prepare public relevant/neutral skill pools with equal model-visible token counts.

Token equality applies to the serialized open_skill result (including hashes),
not later generated conversations. Optional Transformers dependencies belong in
the separate model environment. No model inference runs during preparation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from record_skill_impact import Bridge

from evalarc.evaluate import write_json

NEUTRAL = """A small notebook rests beside a window. Its plain cover is pale green.
The room contains a wooden chair, a linen curtain, and a shelf of botanical sketches.
Outside, leaves move gently in the afternoon breeze. A ceramic cup stands near
a vase of dried flowers. The sketches show petals, branches, and the changing
colors of an autumn garden. The next page describes the feel of paper and the
sound of rain on a roof. The notes are descriptive prose about ordinary objects.
There are no instructions for processing data or implementing a program here."""


def view(script: Path, pool: Path) -> tuple[dict, dict]:
    bridge = Bridge(script, "direct", pool)
    try:
        response = bridge.call("open_skill", {"name": "robot-recording-review"})
        if "view" not in response:
            raise ValueError("reviewed pool did not return a skill")
        return response["view"], bridge.ready["pins"]
    finally:
        bridge.close()


def prepare(skill: Path, model: Path, bridge: Path, output: Path) -> dict:
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model, local_files_only=True)
    output.mkdir(parents=True, exist_ok=False)
    text = skill.read_text()
    parts = text.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        raise ValueError("expected the reviewed skill's YAML frontmatter")
    header = "---" + parts[1] + "---\n\n"
    relevant = output / "pools/relevant/robot-recording-review"
    neutral = output / "pools/neutral/robot-recording-review"
    relevant.mkdir(parents=True)
    neutral.mkdir(parents=True)
    (relevant / "SKILL.md").write_bytes(skill.read_bytes())
    relevant_view, relevant_pins = view(bridge, relevant.parent)

    def tokens(value: dict) -> int:
        # This is exactly the JSON serialization used by the shared model harness.
        return len(tokenizer.encode(json.dumps(value), add_special_tokens=False))

    target = tokens(relevant_view)
    words = NEUTRAL.split() * 20
    # Find a nearby text length cheaply before measuring the full real response.
    approximate = 1
    for count in range(1, len(words)):
        trial_view = {
            **relevant_view,
            "content": "# Field notes\n\n" + " ".join(words[:count]) + "\n",
        }
        if tokens(trial_view) >= target:
            approximate = count
            break
    attempts = []
    candidates = [
        (max(1, approximate + delta), ending)
        for delta in [0, *[n * sign for n in range(1, 65) for sign in (-1, 1)]]
        for ending in ("\n", ".\n", " Leaves.\n", " Rain.\n")
    ]
    for count, ending in candidates:
        body = "# Field notes\n\n" + " ".join(words[:count]) + ending
        (neutral / "SKILL.md").write_text(header + body)
        neutral_view, neutral_pins = view(bridge, neutral.parent)
        measured = tokens(neutral_view)
        attempts.append({"words": count, "ending": ending, "tokens": measured})
        if measured == target:
            break
    else:
        write_json(output / "failed-match.json", {"target": target, "attempts": attempts})
        raise ValueError("could not match the real tool-result token length")
    if relevant_view["name"] != neutral_view["name"] or (
        relevant_view["description"] != neutral_view["description"]
    ):
        raise ValueError("catalog metadata must stay identical")
    report = {
        "schema": "evalarc.skill-context-match.v1",
        "tokenizer_model": "Qwen/Qwen3-8B",
        "tokenizer_revision": "b968826d9c46dd6066d109eabc6255188de91218",
        "tokenizer_files": {
            name: hashlib.sha256((model / name).read_bytes()).hexdigest()
            for name in ("tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt")
        },
        "serialization": "json.dumps(view), ensure_ascii=True; add_special_tokens=False",
        "model_visible_open_skill_tokens": target,
        "relevant": {"view": relevant_view, "pins": relevant_pins},
        "neutral": {"view": neutral_view, "pins": neutral_pins},
        "preparation_attempts": attempts,
        "scope": (
            "Equal token length for the initial open_skill result, including file hashes. "
            "Same advertised name and description; neutral body is unrelated descriptive prose. "
            "Later tool calls and generated conversations may differ and must be reported."
        ),
    }
    write_json(output / "match.json", report)
    shutil.copyfile(__file__, output / "prepare_context_controls.py")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--bridge", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.skill, args.model, args.bridge, args.output)
    print(
        json.dumps(
            {
                "tokens_per_open": result["model_visible_open_skill_tokens"],
                "attempts": len(result["preparation_attempts"]),
            }
        )
    )

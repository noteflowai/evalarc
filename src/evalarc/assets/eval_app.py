"""The application under evaluation. Replace respond() with your real call.

This stub routes text with the "keyword -> label" lines in prompt.md so the project
runs end to end without a model. Your version would send prompt.md and the input to
your model and return its answer. Keep prompt.md as the file the hillclimb loop edits.
"""

from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_prompt() -> str:
    return (HERE / "prompt.md").read_text(encoding="utf-8")


def respond(text: str, prompt: str | None = None) -> str:
    prompt = load_prompt() if prompt is None else prompt
    rules = re.findall(r"^- (.+?) -> (\S+)\s*$", prompt, re.M)
    lowered = text.casefold()
    for keyword, label in rules:
        if keyword.casefold() in lowered:
            return label
    return "general"

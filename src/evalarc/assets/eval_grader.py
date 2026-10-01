"""Programmatic grader. Prefer these checks whenever the output space is small.

Each case in cases.jsonl names one check:
  exact      the stripped output equals `expected`
  contains   `expected` appears in the output, ignoring case
  label      the stripped output is one of `labels` and equals `expected`
  json_keys  the output is a JSON object containing every key listed in `expected`

For open-ended outputs, keep a model judge instead, written as a separate command and
checked with `evalarc judge-packet grader` before you trust it. Never let the judge be
the model under evaluation.
"""

from __future__ import annotations

import json


def grade(case: dict, output: str) -> tuple[bool, str]:
    """Return (passed, explanation). Every condition here must be stated in the input."""
    check, expected = case["check"], case["expected"]
    text = output.strip()
    if check == "exact":
        return text == expected, f"expected exactly {expected!r}"
    if check == "contains":
        return expected.casefold() in text.casefold(), f"expected to contain {expected!r}"
    if check == "label":
        labels = case["labels"]
        if text not in labels:
            return False, f"{text!r} is not one of {labels}"
        return text == expected, f"expected label {expected!r}"
    if check == "json_keys":
        try:
            value = json.loads(text)
        except ValueError:
            return False, "output is not JSON"
        if not isinstance(value, dict):
            return False, "output is not a JSON object"
        missing = [key for key in expected if key not in value]
        return not missing, f"missing keys {missing}" if missing else "all keys present"
    raise ValueError(f"unknown check {check!r}")

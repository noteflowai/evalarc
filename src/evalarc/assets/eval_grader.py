"""Programmatic grader. Prefer these checks whenever the output space is small.

Each case in cases.jsonl names one check:
  exact      the stripped output equals `expected`
  contains   `expected` appears in the output, ignoring case
  label      the stripped output is one of `labels` and equals `expected`
  json_keys  the output is a JSON object containing every key listed in `expected`
  json_schema the output is JSON matching the schema in `expected` (type, required,
             properties, items, enum, minimum/maximum, minLength/maxLength,
             additionalProperties: false)
  command    the argument array in `expected` exits 0 with the output on stdin, e.g. a
             unit-test runner such as ["python", "-m", "pytest", "-q", "tests/test_x.py"]

For open-ended outputs, keep a model judge instead, written as a separate command and
checked with `evalarc judge-packet grader` before you trust it. Never let the judge be
the model under evaluation.
"""

from __future__ import annotations

import json
import subprocess


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
    if check == "json_schema":
        try:
            value = json.loads(text)
        except ValueError:
            return False, "output is not JSON"
        problems = schema_errors(value, expected)
        return not problems, "; ".join(problems[:3]) or "matches the schema"
    if check == "command":
        # Runs on the evaluation host: only use commands you trust.
        done = subprocess.run(expected, input=output, capture_output=True, text=True, timeout=120)
        tail = (done.stdout + done.stderr).strip()[-300:]
        return done.returncode == 0, f"exit {done.returncode}: {tail}"
    raise ValueError(f"unknown check {check!r}")


TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


def schema_errors(value, schema: dict, where: str = "$") -> list[str]:
    """A small JSON Schema subset; enough for structured-output checks."""
    errors = []
    kinds = schema.get("type")
    kinds = kinds if isinstance(kinds, list) else [kinds] if kinds else []

    def is_kind(kind):
        if kind == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if kind == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        return isinstance(value, TYPES[kind])

    if kinds and not any(is_kind(kind) for kind in kinds):
        return [f"{where} is not {' or '.join(kinds)}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{where} is not one of {schema['enum']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{where} < {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{where} > {schema['maximum']}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{where} shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{where} longer than {schema['maxLength']}")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{where}.{key} is missing")
        properties = schema.get("properties", {})
        for key, sub in properties.items():
            if key in value:
                errors += schema_errors(value[key], sub, f"{where}.{key}")
        if schema.get("additionalProperties") is False:
            errors += [f"{where}.{key} is not allowed" for key in value if key not in properties]
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            errors += schema_errors(item, schema["items"], f"{where}[{index}]")
    return errors

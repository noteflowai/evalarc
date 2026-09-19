"""The public diagnostic must exercise the interaction missed by EOF examples."""

import json
from pathlib import Path

import pytest

from scripts.protocol_probe import ProtocolFailure, probe


def files(root: Path, program: str):
    candidate, example = root / "main.py", root / "example.jsonl"
    candidate.write_text(program)
    example.write_text('{"op":"review"}\n')
    return candidate, example


def test_two_persistent_requests_are_observed(tmp_path):
    candidate, example = files(
        tmp_path,
        "import sys,json\nfor line in sys.stdin:\n"
        " print(json.dumps({'seen':json.loads(line)}),flush=True)\n",
    )
    assert probe(candidate, example) == [{"seen": {"op": "review"}}] * 2


@pytest.mark.parametrize(
    "program",
    [
        "import sys\nfor line in sys.stdin:\n print('{}')\n",
        "import sys\nsys.stdin.read()\nprint('{}',flush=True)\n",
    ],
)
def test_eof_or_buffered_programs_do_not_pass(tmp_path, program):
    candidate, example = files(tmp_path, program)
    with pytest.raises(ProtocolFailure, match="response timeout"):
        probe(candidate, example, timeout=0.4)


@pytest.mark.parametrize("response", ["not-json", "NaN", "{}\n{}"])
def test_invalid_or_multiple_response_lines_are_rejected(tmp_path, response):
    candidate, example = files(
        tmp_path,
        f"import sys\nfor line in sys.stdin:\n print({json.dumps(response)},flush=True)\n",
    )
    with pytest.raises(ProtocolFailure):
        probe(candidate, example)


def test_early_exit_is_a_protocol_failure(tmp_path):
    candidate, example = files(tmp_path, "pass\n")
    with pytest.raises(ProtocolFailure, match="ended|closed"):
        probe(candidate, example)

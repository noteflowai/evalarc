"""SYNTHETIC .eval archives: a malformed member exits 2 and names the archive and member.

Every archive is built here from the bundled Inspect example or from hand-written
bytes. The cases pin how evalarc diff reports these defects. They say nothing about
which corruptions real Inspect exports produce.
"""

import json
import zipfile
from pathlib import Path

import pytest

from evalarc.cli import main
from evalarc.results_diff import load_results

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples/results-diff"
JSON_LOG = EXAMPLES / "inspect/current.json"
POSITIONS = pytest.mark.parametrize("archive_first", [True, False], ids=["baseline", "current"])


def header_and_samples():
    document = json.loads(JSON_LOG.read_text())
    samples = document.pop("samples")
    return document, samples


def build(path, header, members=()):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as output:
        output.writestr("header.json", header)
        for name, body in members:
            output.writestr(name, body)
    return path


def run_diff(tmp_path, capsys, archive, archive_first=False, summary=None):
    """Run evalarc diff with --output and --markdown and check nothing was written.

    summary: bytes to pre-create the --markdown file with, or None to leave it absent.
    """
    pair = (archive, JSON_LOG) if archive_first else (JSON_LOG, archive)
    output = tmp_path / "review"
    markdown = tmp_path / "job-summary.md"
    if summary is not None:
        markdown.write_bytes(summary)
    args = ["diff", str(pair[0]), str(pair[1]), "--output", str(output)]
    code = main(args + ["--markdown", str(markdown)])
    captured = capsys.readouterr()
    assert code == 2, captured.err
    assert captured.out == ""
    assert not output.exists()
    if summary is None:
        assert not markdown.exists()
    else:
        assert markdown.read_bytes() == summary
    assert "Traceback" not in captured.err
    assert f"evalarc: {archive.name} member " in captured.err
    return captured.err


@POSITIONS
def test_invalid_json_header_names_the_archive_and_member(tmp_path, capsys, archive_first):
    archive = build(tmp_path / "broken-header.eval", "not json")
    existing = b"## Earlier step\n\nkept as is\n"
    err = run_diff(tmp_path, capsys, archive, archive_first, summary=existing)
    assert f"{archive.name} member 'header.json' is not valid JSON" in err
    assert "inspect log dump LOG.eval > LOG.json" in err
    decoder_lines = [line for line in err.splitlines() if "Expecting value: line 1" in line]
    assert decoder_lines
    assert all(archive.name in line for line in decoder_lines)


@POSITIONS
@pytest.mark.parametrize(
    "header,kind,internal",
    [
        ("[1, 2]", "array", "list indices must be integers"),
        ('"text"', "string", "does not support item assignment"),
        ("7", "number", "does not support item assignment"),
        ("null", "null", "does not support item assignment"),
    ],
    ids=["array", "string", "number", "null"],
)
def test_non_object_header_is_explained(tmp_path, capsys, archive_first, header, kind, internal):
    archive = build(tmp_path / "odd-header.eval", header)
    err = run_diff(tmp_path, capsys, archive, archive_first)
    assert f"{archive.name} member 'header.json' must be a JSON object (got {kind})" in err
    assert "Re-export it from Inspect or rerun the evaluation" in err
    assert internal not in err


def test_invalid_utf8_sample_names_the_member(tmp_path, capsys):
    header = json.dumps(header_and_samples()[0])
    members = [("samples/refund_epoch_1.json", b'{"id": "\xc3\x28"}')]
    archive = build(tmp_path / "bad-sample.eval", header, members)
    err = run_diff(tmp_path, capsys, archive)
    assert "member 'samples/refund_epoch_1.json' is not valid JSON" in err


def test_member_name_control_characters_are_escaped(tmp_path, capsys):
    header = json.dumps(header_and_samples()[0])
    members = [("samples/bad\x1b[31m.json", "not json")]
    archive = build(tmp_path / "escape.eval", header, members)
    err = run_diff(tmp_path, capsys, archive)
    assert "not valid JSON" in err
    assert "bad" in err
    assert "member 'samples/bad\\x1b[31m.json' is not valid JSON" in err
    raw = [ch for ch in err if (ord(ch) < 32 or ord(ch) == 127) and ch not in "\r\n"]
    assert raw == []


def test_long_member_name_is_cut_at_80_characters(tmp_path, capsys):
    header = json.dumps(header_and_samples()[0])
    name = "samples/" + "x" * 100 + ".json"
    archive = build(tmp_path / "long.eval", header, [(name, "not json")])
    err = run_diff(tmp_path, capsys, archive, summary=b"")
    shown = "'samples/" + "x" * 68 + "..."
    assert len(shown) == 80
    assert f"member {shown} is not valid JSON" in err
    assert name not in err


def test_parsed_non_object_sample_keeps_the_position_error(tmp_path, capsys):
    header = json.dumps(header_and_samples()[0])
    archive = build(tmp_path / "array-sample.eval", header, [("samples/a.json", "[1]")])
    assert main(["diff", str(JSON_LOG), str(archive)]) == 2
    assert "sample at position 0 is not an object (got array)" in capsys.readouterr().err


def test_valid_archive_still_loads_like_the_json_log(tmp_path, capsys):
    header, samples = header_and_samples()
    members = [
        (f"samples/{item['id']}_epoch_{item['epoch']}.json", json.dumps(item)) for item in samples
    ]
    archive = build(tmp_path / "current.eval", json.dumps(header), members)
    assert load_results(archive)["cases"] == load_results(JSON_LOG)["cases"]
    assert main(["diff", str(EXAMPLES / "inspect/baseline.json"), str(archive)]) == 1
    assert "regressed: refund-duplicate / match" in capsys.readouterr().out


def test_ci_gate_docs_explain_the_archive_messages():
    text = (ROOT / "docs/ci-gate.md").read_text(encoding="utf-8")
    start = text.index("Exit codes: **0**")
    for phrase in (
        "member header.json must be a JSON object",
        "member 'header.json' is not valid JSON",
        "member 'header.json' must be a JSON object (got array)",
        "is not valid JSON",
        "inspect log dump LOG.eval",
    ):
        assert text.find(phrase, start) > start, phrase


def test_zh_ci_gate_docs_explain_the_archive_messages():
    text = (ROOT / "docs/ci-gate.zh-CN.md").read_text(encoding="utf-8")
    for phrase in (
        "member 'header.json' is not valid JSON",
        "member 'header.json' must be a JSON object (got array)",
        "inspect log dump LOG.eval > LOG.json",
    ):
        assert phrase in text, phrase

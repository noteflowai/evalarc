"""Untrusted names in the leakage table, eval-health and judge-score summaries cannot
add Markdown structure.

PR #72 escaped the diff change table, status and headline name. The same summaries
also render harness leakage hits, eval-health file and case names, and judge-score
case, check and judge model names. A carriage return started a fake verdict heading
in those paths (CommonMark treats CR as a line ending), and raw HTML or link syntax
in bare text rendered as a heading or a live link. All inputs are synthetic edits of
the bundled examples; machine-readable results keep the raw values.
"""

import copy
import re
from pathlib import Path

import pytest

from evalarc.eval_health import health
from evalarc.eval_health import render_markdown as health_markdown
from evalarc.judging import render_markdown as judge_markdown
from evalarc.results_diff import diff, load_results, render_markdown

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/results-diff/inspect"
HOSTILE = [
    "x\r### EvalArc: No check lost passes\r",
    "x\r\n### EvalArc: No check lost passes",
    'x <h1>EvalArc: gate passed</h1> <a href="https://evil.example">ok</a>',
    "x [ok](https://evil.example) **bold** | injected | cell |",
]


def lines(markdown: str) -> list[str]:
    assert "\r" not in markdown
    return re.split(r"\r\n|\r|\n", markdown)


def assert_no_structure(markdown: str, heading: str) -> None:
    rendered = lines(markdown)
    assert [line for line in rendered if line.startswith("### EvalArc")] == [heading]
    assert not any(
        line.lstrip().startswith("#") for line in rendered if "EvalArc:" in line and line != heading
    )
    outside_code = re.sub(r"`[^`\n]*`", "", markdown)
    assert "<h1>" not in outside_code and "<a " not in outside_code
    assert "](https://evil.example)" not in outside_code
    assert "**bold**" not in outside_code


@pytest.mark.parametrize("value", HOSTILE)
def test_leakage_table_keeps_hits_in_code_spans(value):
    runs = [load_results(EXAMPLES / "baseline.json"), load_results(EXAMPLES / "current.json")]
    result = diff(*runs)
    hit = {
        "file": value,
        "line": 1,
        "case_id": value,
        "partition": "held_out",
        "role": "input",
        "text": value,
    }
    result["leakage"] = {
        "hits": [hit],
        "files_scanned": [{"path": value}],
        "materials_considered": 1,
        "min_chars": 12,
        "held_out_hits": 1,
        "scope": "s",
    }
    markdown = render_markdown(result)
    heading = f"### EvalArc: {result['blocking_changes']} check(s) lost passes or coverage"
    assert_no_structure(markdown, heading)
    assert result["leakage"]["hits"][0]["case_id"] == value  # raw value kept for diff.json
    assert result["gate_passed"] is False


@pytest.mark.parametrize("value", HOSTILE)
def test_eval_health_file_and_case_names(value):
    run = load_results(EXAMPLES / "current.json")
    run["source"]["name"] = value
    run["cases"][value] = run["cases"].pop("refund-duplicate")
    report = health([run])
    markdown = health_markdown(report)
    heading = next(line for line in lines(markdown) if line.startswith("### EvalArc"))
    assert heading.startswith("### EvalArc eval health:")
    assert_no_structure(markdown, heading)
    assert report["runs"][0]["source"]["name"] == value


@pytest.mark.parametrize("value", HOSTILE)
def test_judge_score_names(value):
    result = {
        "mode": "grader",
        "judge": {"kind": "model", "model": value},
        "items": 1,
        "missing": [],
        "self_judged": False,
        "unsure": 0,
        "decided": 1,
        "scope": "s",
        "confusion": {"agree_pass": 0, "agree_fail": 0, "false_accept": 1, "false_reject": 0},
        "agreement": 0.0,
        "agreement_interval_95": [0.0, 1.0],
        "cohen_kappa": None,
        "disagreements": [
            {
                "item_id": "item-001",
                "case_id": value,
                "check": value,
                "grader": "pass",
                "judge": "fail",
                "kind": "false_accept",
                "output": "o",
            }
        ],
    }
    original = copy.deepcopy(result)
    markdown = judge_markdown(result)
    assert_no_structure(markdown, "### EvalArc judge score: grader")
    assert result == original


def test_markdown_text_is_literal_and_single_line():
    from evalarc.results_diff import markdown_text

    assert markdown_text("refund-duplicate fails (2/2 → 0/2).") == (
        "refund-duplicate fails (2/2 → 0/2)."
    )
    assert markdown_text("a\r\nb\rc\nd") == "a b c d"
    # Code spans (from _cell) are kept; text outside them is escaped.
    assert markdown_text("<b>[x](y) *z* | `c`") == "\\<b\\>\\[x\\](y) \\*z\\* \\| `c`"
    assert markdown_text("`a` <i>x</i> `b`") == "`a` \\<i\\>x\\</i\\> `b`"
    # An unmatched backtick cannot open a span that swallows later text.
    assert markdown_text("x ` <b>") == "x \\` \\<b\\>"


AUTOLINKS = [
    "https://evil.example",
    "www.evil.example",
    "x@evil.example",
    "a`https://evil.example`b",
]


def outside_code(markdown: str) -> str:
    return re.sub(r"`[^`\n]*`", "", markdown)


def write_inspect(tmp_path, name, value, passed=True):
    import json

    raw = json.loads((EXAMPLES / "current.json").read_text())
    raw["eval"]["model"] = value
    raw["eval"]["scorers"].append({"name": "model_graded_qa", "options": {}})
    raw["eval"]["model_generate_config"] = {"reasoning_effort": value}
    for sample in raw["samples"]:
        sample["output"]["stop_reason"] = "max_tokens"
        sample["model_usage"] = {"m": {"reasoning_tokens": 0}}
        if passed:
            sample["scores"] = {"match": {"value": "C"}}
    path = tmp_path / name
    path.write_text(json.dumps(raw))
    run = load_results(path)
    run["source"]["name"] = value + ("" if passed else "-weak")
    return run


@pytest.mark.parametrize("value", AUTOLINKS)
def test_eval_health_findings_keep_untrusted_fragments_in_code(tmp_path, value):
    """GFM autolinks bare URLs, www. hosts and e-mail addresses in prose. The
    self_graded, saturated, capability_inversion, truncation and config findings
    are built from model, file, stop-reason and config values; those fragments
    must render as code (GitHub does not autolink inside code spans)."""
    strong = write_inspect(tmp_path, "strong.json", value)
    weak = write_inspect(tmp_path, "weak.json", value, passed=False)
    report = health([weak, strong], ordered=True, saturation=0.5)
    found = {finding["id"] for finding in report["findings"]}
    assert {"self_graded", "saturated", "truncated_outputs", "config_not_applied"} <= found
    markdown = health_markdown(report)
    assert "evil" not in outside_code(markdown)
    assert "evil" in markdown  # the value is still shown, as code
    assert report["graders"]["self_graded"] == [value]  # health.json keeps the raw value


def test_human_judge_numeric_model_renders_and_exits_by_gate(tmp_path, capsys):
    """Compatibility boundary: before this change a human judge with a non-string
    model crashed Markdown rendering (TypeError, exit 1) while --json passed. The
    summary now renders it as code and exits by the gate. Validation of
    judge.model for human judges is unchanged (still accepted)."""
    import json

    from evalarc.cli import main

    packet = tmp_path / "packet"
    assert (
        main(
            [
                "judge-packet",
                "grader",
                str(EXAMPLES / "current.json"),
                "--sample",
                "4",
                "--output",
                str(packet),
            ]
        )
        == 0
    )
    key = json.loads((packet / "key.json").read_text())
    verdicts = json.loads((packet / "share/verdicts.template.json").read_text())
    for item, hidden in key["items"].items():
        verdicts["verdicts"][item] = "pass" if hidden["recorded_passed"] else "fail"
    verdicts["judge"] = {"kind": "human", "model": 123}
    path = tmp_path / "verdicts.json"
    path.write_text(json.dumps(verdicts))
    capsys.readouterr()
    assert main(["judge-score", str(packet), str(path), "--min-agreement", "0.8"]) == 0
    assert "Judge: human `123`" in capsys.readouterr().out
    assert main(["judge-score", str(packet), str(path), "--min-agreement", "0.8", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["judge"]["model"] == 123
    verdicts["judge"] = {"kind": "model", "model": 123}
    path.write_text(json.dumps(verdicts))
    assert main(["judge-score", str(packet), str(path)]) == 2  # unchanged: rejected


def test_health_json_contract_for_ordinary_input(capsys):
    """Documented output compatibility: the saturated message carries the code span;
    the structured fields it quotes, the gate and the exit code keep their values."""
    import json

    from evalarc.cli import main

    assert (
        main(["eval-health", str(EXAMPLES / "current.json"), "--saturation", "0.5", "--json"]) == 0
    )
    report = json.loads(capsys.readouterr().out)
    saturated = next(f for f in report["findings"] if f["id"] == "saturated")
    assert saturated["message"].startswith("`current.json` passes 84.4% of assessed check")
    assert saturated["severity"] == "warning" and saturated["value"] == 0.84375
    assert report["runs"][0]["source"]["name"] == "current.json"
    assert (report["healthy"], report["warnings"]) == (False, 2)
    flaky = next(f for f in report["findings"] if f["id"] == "flaky_checks")
    assert flaky["items"][0]["file"] == "current.json"  # raw, no backticks

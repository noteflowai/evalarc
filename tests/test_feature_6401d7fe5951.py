"""EA-03: the diff summary explains each blocking finding with its recorded evidence.

Inputs are the bundled Inspect example (scripted replies) and small synthetic edits of
it. They pin rendering behavior; they do not measure reviewer time or accuracy.
"""

import hashlib
import json
import re
from pathlib import Path

import pytest

from evalarc.cli import main
from evalarc.results_diff import diff, load_results, render_markdown

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/results-diff"
INSPECT = EXAMPLES / "inspect"
HEADING = "#### Why the gate failed"
THRESHOLD_LINE = (
    "Numeric scores pass at threshold 1; categorical verdicts use the source tool's pass mark."
)
HEADER = "| Finding | Case / check | Baseline | Current | Failing attempt |"
NO_DETAIL = "no attempt detail recorded"


def inspect_diff():
    return diff(load_results(INSPECT / "baseline.json"), load_results(INSPECT / "current.json"))


def section(markdown):
    """Lines of the explanation section, or None when it is absent."""
    lines = markdown.splitlines()
    if HEADING not in lines:
        return None
    body = []
    for line in lines[lines.index(HEADING) + 1 :]:
        if line.startswith("#### ") or line.startswith("<sub>"):
            break
        body.append(line)
    return body


def cells(line):
    # Escaped pipes (\|) stay inside their cell.
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip())[1:-1]]


def table(lines):
    return [
        cells(line)
        for line in lines
        if line.startswith("| ") and not line.startswith(("| Finding ", "| --- "))
    ]


def clip(value):
    text = str(value)
    return text[:120] + "…" if len(text) > 120 else text


def expected_attempt(entry):
    parts = []
    if entry.get("value") is not None:
        parts.append(f"value `{clip(entry['value'])}`")
    if entry.get("evidence"):
        parts.append(f"evidence `{clip(entry['evidence'])}`")
    return " · ".join(parts) or NO_DETAIL


def flaky_row(result):
    return next(row for row in result["changes"] if row["kind"] == "less_reliable")


def write_log(path, attempts):
    samples = [
        {
            "id": "r",
            "epoch": epoch,
            "input": "q",
            "target": "a",
            "scores": {"match": {"value": "C" if passed else "I"}},
        }
        for epoch, passed in enumerate(attempts, start=1)
    ]
    path.write_text(
        json.dumps({"status": "success", "eval": {"task": "t", "config": {}}, "samples": samples})
    )
    return path


def test_failing_inspect_summary_explains_every_blocking_finding():
    result = inspect_diff()
    markdown = render_markdown(result)
    lines = section(markdown)
    assert lines is not None
    assert markdown.index("| Change | Case |") < markdown.index(HEADING) < markdown.index("<sub>")
    assert lines[lines.index(THRESHOLD_LINE) + 2] == HEADER
    rows = {row[1]: row for row in table(lines)}
    assert len(rows) == result["blocking_changes"] == 3
    assert rows["`cancel-pending` / `match`"] == [
        "less reliable (within noise)",
        "`cancel-pending` / `match`",
        "2/2",
        "1/2",
        "value `I` · evidence `cancel:1006:queued`",
    ]
    regressed = [change for change in result["changes"] if change["kind"] == "regressed"]
    assert sorted(c["check"] for c in regressed if c["case_id"] == "refund-duplicate") == [
        "includes",
        "match",
    ]
    for change in regressed:
        row = rows[f"`{change['case_id']}` / `{change['check']}`"]
        assert row[0] == "regressed"
        entry = next(e for e in change["current_detail"] if e["passed"] is not True)
        assert row[4] == expected_attempt(entry)
    noisy = sum(row[0].endswith("(within noise)") for row in rows.values())
    assert noisy == result["blocking_changes_within_sampling_noise"] == 1
    assert any(line.startswith("Inputs: baseline `baseline.json` sha256 `") for line in lines)


@pytest.mark.parametrize("name", ["inspect", "promptfoo"])
def test_passing_gate_has_no_explanation(name):
    path = EXAMPLES / name / "current.json"
    markdown = render_markdown(diff(load_results(path), load_results(path)))
    assert markdown.startswith("### EvalArc: No check lost passes\n")
    assert HEADING not in markdown


def test_incomplete_run_without_blocking_changes_has_no_explanation(tmp_path):
    document = json.loads((INSPECT / "baseline.json").read_text())
    document["status"] = "error"
    failed = tmp_path / "failed.json"
    failed.write_text(json.dumps(document))
    result = diff(load_results(INSPECT / "baseline.json"), load_results(failed))
    markdown = render_markdown(result)
    assert markdown.startswith("### EvalArc: the current run is incomplete\n")
    assert "did not finish" in markdown and HEADING not in markdown


def test_removed_check_shows_its_baseline_attempt(tmp_path):
    document = json.loads((INSPECT / "current.json").read_text())
    document["samples"] = [s for s in document["samples"] if s["id"] != "refund-duplicate"]
    trimmed = tmp_path / "trimmed.json"
    trimmed.write_text(json.dumps(document))
    result = diff(load_results(INSPECT / "current.json"), load_results(trimmed))
    rows = table(section(render_markdown(result)))
    assert [row[0] for row in rows] == ["removed", "removed"]
    for change, row in zip(result["changes"], rows):
        assert row[3] == "absent"
        expected = "not recorded in the current run; baseline: "
        assert row[4] == expected + expected_attempt(change["baseline_detail"][0])


def test_less_covered_shows_both_assessed_counts(tmp_path):
    result = diff(
        load_results(write_log(tmp_path / "b.json", [True, True, True])),
        load_results(write_log(tmp_path / "c.json", [True])),
    )
    rows = table(section(render_markdown(result)))
    assert len(rows) == 1 and rows[0][0].startswith("less covered")
    assert rows[0][1:] == ["`r` / `match`", "3/3", "1/1", "assessed 1 of 3 baseline attempts"]


def test_untrusted_evidence_stays_in_one_escaped_cell():
    result = inspect_diff()
    flaky_row(result)["current_detail"] = [
        {"passed": False, "value": "I", "evidence": "a | b `c`\n### fake"}
    ]
    lines = section(render_markdown(result))
    rows = table(lines)
    assert len(rows) == 3 and all(len(row) == 5 for row in rows)
    assert rows[-1][4] == "value `I` · evidence `a \\| b 'c' ### fake`"
    assert not any(line.startswith("### fake") for line in lines)


def test_long_evidence_is_truncated_with_an_ellipsis():
    result = inspect_diff()
    flaky_row(result)["current_detail"] = [{"passed": False, "evidence": "x" * 200}]
    markdown = render_markdown(result)
    assert "| evidence `" + "x" * 120 + "…` |" in markdown
    assert "x" * 121 not in markdown


def test_limit_caps_the_rows_and_counts_the_rest():
    lines = section(render_markdown(inspect_diff(), limit=2))
    assert len(table(lines)) == 2
    assert "1 more blocking finding(s) are in `diff.json`." in lines


def test_missing_detail_and_digest_fall_back_without_inventing_evidence():
    result = inspect_diff()
    flaky_row(result)["current_detail"] = "not a list"
    del result["baseline"]["source"]["sha256"]
    lines = section(render_markdown(result))
    assert table(lines)[-1][4] == NO_DETAIL
    assert not any(line.startswith("Inputs:") for line in lines)


def test_cli_step_summary_explains_the_failure(tmp_path):
    summary = tmp_path / "step-summary.md"
    output = tmp_path / "review"
    baseline, current = INSPECT / "baseline.json", INSPECT / "current.json"
    code = main(
        ["diff", str(baseline), str(current), "--output", str(output), "--markdown", str(summary)]
    )
    assert code == 1
    digest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:12] for p in (baseline, current)}
    provenance = (
        f"Inputs: baseline `baseline.json` sha256 `{digest['baseline.json']}`, "
        f"current `current.json` sha256 `{digest['current.json']}`"
    )
    for text in (summary.read_text(), (output / "summary.md").read_text()):
        lines = section(text)
        assert lines is not None and THRESHOLD_LINE in lines and provenance in lines
        assert "value `I` · evidence `cancel:1006:queued`" in text

import copy
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from evalarc.cli import main
from evalarc.results_diff import diff, load_results, render_markdown

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/results-diff"


def changes(result, *kinds):
    return sorted(
        (row["kind"], row["case_id"], row["check"])
        for row in result["changes"]
        if not kinds or row["kind"] in kinds
    )


def compare(name, suffix=".json", **options):
    folder = EXAMPLES / name
    return diff(
        load_results(folder / f"baseline{suffix}", **options),
        load_results(folder / f"current{suffix}", **options),
    )


def write(path, document):
    path.write_text(json.dumps(document))
    return path


def test_inspect_headline_gain_does_not_hide_lost_checks():
    result = compare("inspect")
    assert result["format"] == "inspect"
    assert result["baseline"]["headline"] == {"name": "match accuracy", "value": 0.625}
    assert result["current"]["headline"] == {"name": "match accuracy", "value": 0.8125}
    assert changes(result, "regressed", "less_reliable") == [
        ("less_reliable", "cancel-pending", "match"),
        ("regressed", "refund-duplicate", "includes"),
        ("regressed", "refund-duplicate", "match"),
    ]
    flaky = next(row for row in result["changes"] if row["kind"] == "less_reliable")
    assert flaky["baseline"] == {"passed": 2, "assessed": 2, "attempts": 2}
    assert flaky["current"] == {"passed": 1, "assessed": 2, "attempts": 2}
    assert flaky["current_detail"] == [
        {"passed": False, "value": "I", "evidence": "cancel:1006:queued"}
    ]
    assert result["counts"]["improved"] == 6
    assert result["blocking_changes"] == 3
    assert not result["gate_passed"]


def test_promptfoo_unchanged_pass_rate_hides_a_swapped_failure():
    result = compare("promptfoo")
    assert result["baseline"]["headline"]["value"] == result["current"]["headline"]["value"] == 0.75
    assert changes(result, "regressed") == [
        ("regressed", "duplicate refund is rejected", "icontains: already refunded"),
        ("regressed", "duplicate refund is rejected", "not-icontains: refund approved"),
    ]
    assert changes(result, "improved") == [
        ("improved", "large refund is escalated", "icontains: escalate"),
        ("improved", "large refund is escalated", "not-icontains: refund approved"),
    ]
    assert result["baseline"]["identity"]["providers"] == ["echo"]


@pytest.mark.parametrize("describe", [True, False])
def test_promptfoo_repeats_are_attempts_of_one_test(tmp_path, describe):
    document = json.loads((EXAMPLES / "promptfoo/current.json").read_text())
    rows = document["results"]["results"]
    if not describe:
        for row in rows:
            row["testCase"].pop("description")
    repeated = copy.deepcopy(document)
    extra = copy.deepcopy(rows)
    for index, row in enumerate(extra):
        row["testIdx"] = len(rows) + index
        if row["vars"]["kind"] == "large":
            row["gradingResult"]["componentResults"][0]["pass"] = False
    repeated["results"]["results"] = rows + extra
    single = tmp_path / "single.json"
    result = diff(
        load_results(write(single, document)),
        load_results(write(tmp_path / "repeated.json", repeated)),
    )
    assert [(row["kind"], row["check"]) for row in result["changes"]] == [
        ("less_reliable", "icontains: escalate")
    ]
    assert result["changes"][0]["current"] == {"passed": 1, "assessed": 2, "attempts": 2}


def test_junit_skipped_test_counts_as_lost_coverage():
    result = compare("junit", ".xml")
    assert changes(result, *("regressed", "unassessed", "improved")) == [
        ("improved", "refund_checks::test_policy_outcome[refund-large]", "passed"),
        ("regressed", "refund_checks::test_policy_outcome[refund-duplicate]", "passed"),
        ("unassessed", "refund_checks::test_names_the_order[status-open]", "passed"),
    ]
    assert result["baseline"]["headline"] is None


@pytest.mark.parametrize("name,suffix", [("inspect", ".json"), ("promptfoo", ".json")])
def test_identical_inputs_pass_the_gate(name, suffix):
    path = EXAMPLES / name / f"current{suffix}"
    result = diff(load_results(path), load_results(path))
    assert result["gate_passed"] and not result["changes"]


def test_removed_failing_check_blocks_but_added_check_does_not(tmp_path):
    document = json.loads((EXAMPLES / "inspect/current.json").read_text())
    trimmed = copy.deepcopy(document)
    trimmed["samples"] = [s for s in trimmed["samples"] if s["id"] != "refund-duplicate"]
    result = diff(
        load_results(EXAMPLES / "inspect/current.json"),
        load_results(write(tmp_path / "trimmed.json", trimmed)),
    )
    assert changes(result) == [
        ("removed", "refund-duplicate", "includes"),
        ("removed", "refund-duplicate", "match"),
    ]
    assert not result["gate_passed"]
    reverse = diff(
        load_results(tmp_path / "trimmed.json"), load_results(EXAMPLES / "inspect/current.json")
    )
    assert {row["kind"] for row in reverse["changes"]} == {"added"}
    assert reverse["gate_passed"]


def test_inspect_eval_archive_matches_the_json_log(tmp_path):
    document = json.loads((EXAMPLES / "inspect/current.json").read_text())
    samples = document.pop("samples")
    archive = tmp_path / "current.eval"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        output.writestr("header.json", json.dumps(document))
        for sample in samples:
            output.writestr(
                f"samples/{sample['id']}_epoch_{sample['epoch']}.json", json.dumps(sample)
            )
    from_archive = load_results(archive)
    from_json = load_results(EXAMPLES / "inspect/current.json")
    assert from_archive["format"] == "inspect"
    assert from_archive["cases"] == from_json["cases"]


def test_numeric_scores_use_the_declared_threshold(tmp_path):
    document = json.loads((EXAMPLES / "inspect/baseline.json").read_text())
    for sample in document["samples"]:
        sample["scores"] = {"rubric": {"value": 8 if sample["id"] == "refund-small" else 6}}
    lower = copy.deepcopy(document)
    for sample in lower["samples"]:
        if sample["id"] == "refund-small":
            sample["scores"]["rubric"]["value"] = 7
    before, after = write(tmp_path / "a.json", document), write(tmp_path / "b.json", lower)
    assert diff(load_results(before), load_results(after))["gate_passed"] is True
    strict = diff(load_results(before, threshold=8), load_results(after, threshold=8))
    assert changes(strict) == [("regressed", "refund-small", "rubric")]
    assert strict["numeric_pass_threshold"] == 8


def test_incomplete_current_run_fails_the_gate(tmp_path):
    document = json.loads((EXAMPLES / "inspect/baseline.json").read_text())
    document["status"] = "error"
    result = diff(
        load_results(EXAMPLES / "inspect/baseline.json"),
        load_results(write(tmp_path / "failed.json", document)),
    )
    assert not result["changes"] and result["current_incomplete"]
    assert not result["gate_passed"]
    assert "did not finish" in render_markdown(result)


def test_cli_writes_a_reviewable_folder_and_appends_markdown(tmp_path, capsys):
    summary = tmp_path / "step-summary.md"
    summary.write_text("existing\n")
    output = tmp_path / "review"
    code = main(
        [
            "diff",
            str(EXAMPLES / "inspect/baseline.json"),
            str(EXAMPLES / "inspect/current.json"),
            "--output",
            str(output),
            "--markdown",
            str(summary),
        ]
    )
    assert code == 1
    printed = capsys.readouterr().out
    assert "match accuracy: 0.625 -> 0.8125" in printed
    assert "regressed: refund-duplicate / match" in printed
    assert sorted(p.name for p in output.iterdir()) == [
        "baseline.json",
        "current.json",
        "diff.json",
        "index.html",
        "summary.md",
    ]
    for label in ("baseline", "current"):
        copied = (output / f"{label}.json").read_bytes()
        assert copied == (EXAMPLES / f"inspect/{label}.json").read_bytes()
        recorded = json.loads((output / "diff.json").read_text())[label]["source"]["sha256"]
        assert recorded == hashlib.sha256(copied).hexdigest()
    text = summary.read_text()
    assert text.startswith("existing\n### EvalArc: 3 check(s) lost passes or coverage")
    assert "| regressed | `refund-duplicate` | `match` | 2/2 | 0/2 |" in text
    assert "Content-Security-Policy" in (output / "index.html").read_text()
    assert (
        main(
            [
                "diff",
                str(EXAMPLES / "inspect/baseline.json"),
                str(EXAMPLES / "inspect/current.json"),
                "--output",
                str(output),
            ]
        )
        == 2
    )


def test_cli_json_and_passing_gate(capsys):
    path = str(EXAMPLES / "promptfoo/current.json")
    assert main(["diff", path, path, "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == "evalarc.results-diff.v1"
    assert result["gate_passed"] and result["counts"]["unchanged"] == 7


@pytest.mark.parametrize(
    "baseline,current,message",
    [
        ("inspect/baseline.json", "promptfoo/current.json", "different formats"),
        ("inspect/baseline.json", "renamed.json", "not comparable: task"),
        ("inspect/baseline.json", "empty.json", "no samples"),
        ("inspect/baseline.json", "not-json.json", "cannot detect"),
        ("junit/baseline.xml", "dtd.xml", "DTD"),
    ],
)
def test_unusable_inputs_exit_2(tmp_path, capsys, baseline, current, message):
    document = json.loads((EXAMPLES / "inspect/current.json").read_text())
    write(tmp_path / "renamed.json", {**document, "eval": {**document["eval"], "task": "other"}})
    write(tmp_path / "empty.json", {**document, "samples": []})
    (tmp_path / "not-json.json").write_text("[1, 2]")
    (tmp_path / "dtd.xml").write_text('<!DOCTYPE x [<!ENTITY a "b">]><testsuite/>')
    paths = [
        EXAMPLES / name if (EXAMPLES / name).exists() else tmp_path / name
        for name in (baseline, current)
    ]
    assert main(["diff", *map(str, paths)]) == 2
    assert message in capsys.readouterr().err


def test_markdown_escapes_table_cells():
    result = compare("promptfoo")
    result["changes"][0]["case_id"] = "a | b `c`"
    assert "`a \\| b 'c'`" in render_markdown(result)


def _repeated_inspect(tmp_path, baseline_pass, current_pass, epochs=3):
    """Build a two-attempt-per-check Inspect pair for one case/check.

    baseline_pass / current_pass give how many of `epochs` attempts pass on each side.
    """
    base = json.loads((EXAMPLES / "inspect/baseline.json").read_text())
    template = base["samples"][0]

    def build(passes):
        samples = []
        for epoch in range(1, epochs + 1):
            sample = copy.deepcopy(template)
            sample["id"] = "flaky-case"
            sample["epoch"] = epoch
            sample.pop("error", None)
            sample["scores"] = {"match": {"value": "C" if epoch <= passes else "I"}}
            samples.append(sample)
        document = copy.deepcopy(base)
        document["samples"] = samples
        return document

    b = write(tmp_path / "b.json", build(baseline_pass))
    c = write(tmp_path / "c.json", build(current_pass))
    return diff(load_results(b), load_results(c))


def test_flaky_partial_regression_is_marked_within_sampling_noise(tmp_path):
    result = _repeated_inspect(tmp_path, baseline_pass=3, current_pass=1)
    row = next(r for r in result["changes"] if r["check"] == "match")
    assert row["kind"] == "less_reliable"
    assert row["within_sampling_noise"] is True
    assert result["blocking_changes"] == 1
    assert result["blocking_changes_within_sampling_noise"] == 1
    # The annotation never relaxes the gate.
    assert result["gate_passed"] is False
    md = render_markdown(result)
    assert "within sampling noise" in md
    assert "less reliable (within noise)" in md


def test_clean_full_swing_is_not_marked_within_noise(tmp_path):
    result = _repeated_inspect(tmp_path, baseline_pass=3, current_pass=0)
    row = next(r for r in result["changes"] if r["check"] == "match")
    assert row["kind"] == "regressed"
    assert row["within_sampling_noise"] is False
    assert result["blocking_changes_within_sampling_noise"] == 0
    assert "within sampling noise" not in render_markdown(result)


def test_recorded_inspect_flags_only_the_flaky_partial_change():
    # The inspect example records two attempts per check. Only the 2/2 -> 1/2 flaky
    # change is within sampling noise; the clean 2/2 -> 0/2 regressions are not.
    result = compare("inspect")
    flagged = [
        (row["case_id"], row["check"])
        for row in result["changes"]
        if row.get("within_sampling_noise") is True
    ]
    assert flagged == [("cancel-pending", "match")]
    assert result["blocking_changes_within_sampling_noise"] == 1
    # The two clean regressions keep the gate red and are not called noise.
    for row in result["changes"]:
        if row["kind"] == "regressed":
            assert row["within_sampling_noise"] is False
    assert result["gate_passed"] is False


def test_wilson_interval_matches_known_bounds():
    from evalarc.results_diff import _wilson_interval

    low, high = _wilson_interval(1, 2)
    assert round(low, 4) == 0.0945 and round(high, 4) == 0.9055
    assert _wilson_interval(0, 0) == (0.0, 1.0)
    assert _wilson_interval(5, 5)[1] == 1.0


def test_within_noise_returns_none_without_repeated_attempts():
    from evalarc.results_diff import _within_sampling_noise

    one = {"passed": 1, "assessed": 1, "attempts": 1}
    zero = {"passed": 0, "assessed": 1, "attempts": 1}
    # No sampling spread on either side: the flag does not apply.
    assert _within_sampling_noise(one, zero) is None
    # Absent side (added/removed check) also does not apply.
    assert _within_sampling_noise(None, one) is None
    assert _within_sampling_noise(one, None) is None


def test_html_reports_within_noise_when_flagged(tmp_path):
    result = _repeated_inspect(tmp_path, baseline_pass=3, current_pass=1)
    from evalarc.results_diff import render_html

    destination = tmp_path / "index.html"
    render_html(result, destination)
    html = destination.read_text()
    assert "within noise" in html
    assert "within sampling noise" in html

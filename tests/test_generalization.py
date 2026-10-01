import json
from pathlib import Path

import pytest

from evalarc.cli import main
from evalarc.generalization import load_split, partition, review_split, scan_harness
from evalarc.results_diff import diff, load_results, render_markdown

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/results-diff"


def inspect_log(path, outcomes, inputs=None):
    """Write a minimal Inspect log: outcomes maps case id -> list of pass booleans."""
    samples = []
    for case_id, passes in outcomes.items():
        for epoch, passed in enumerate(passes, start=1):
            samples.append(
                {
                    "id": case_id,
                    "epoch": epoch,
                    "input": (inputs or {}).get(case_id, f"Question for {case_id}"),
                    "target": f"answer-for-{case_id}",
                    "scores": {"match": {"value": "C" if passed else "I"}},
                }
            )
    document = {
        "status": "success",
        "eval": {"task": "demo", "model": "mockllm/model", "config": {}},
        "samples": samples,
    }
    path.write_text(json.dumps(document))
    return path


def split_file(path, held_out, **extra):
    path.write_text(
        json.dumps({"schema_version": "evalarc.case-split.v1", "held_out": held_out, **extra})
    )
    return path


def review(tmp_path, before, after, held_out):
    runs = [
        load_results(inspect_log(tmp_path / "baseline.json", before)),
        load_results(inspect_log(tmp_path / "current.json", after)),
    ]
    result = diff(*runs)
    return review_split(*runs, result, load_split(split_file(tmp_path / "split.json", held_out)))


FAIL, PASS = [False] * 10, [True] * 10


@pytest.mark.parametrize(
    "before,after,state",
    [
        # Tuning and held-out cases both improve well beyond noise.
        ({"t1": FAIL, "t2": FAIL, "h1": FAIL}, {"t1": PASS, "t2": PASS, "h1": PASS}, "generalizes"),
        # Only the cases the change was tuned on improve: the FIG-6 overfitting signal.
        (
            {"t1": FAIL, "t2": FAIL, "h1": FAIL},
            {"t1": PASS, "t2": PASS, "h1": FAIL},
            "overfitting_signal",
        ),
        # A held-out check loses passes even though tuning cases improve.
        (
            {"t1": FAIL, "t2": FAIL, "h1": PASS},
            {"t1": PASS, "t2": PASS, "h1": FAIL},
            "held_out_regressions",
        ),
        # Held-out cases improve by one attempt only.
        (
            {"t1": FAIL, "t2": FAIL, "h1": [False] * 10},
            {"t1": FAIL, "t2": FAIL, "h1": [True] + [False] * 9},
            "held_out_gain_within_noise",
        ),
        ({"t1": PASS, "h1": PASS}, {"t1": PASS, "h1": PASS}, "no_measurable_gain"),
    ],
)
def test_split_states(tmp_path, before, after, state):
    result = review(tmp_path, before, after, ["h1"])
    assert result["state"] == state
    assert result["split"]["held_out_cases"] == ["h1"]
    assert result["partitions"]["held_out"]["cases"] == 1


def test_overfitting_signal_reports_partition_rates(tmp_path):
    result = review(
        tmp_path,
        {"t1": FAIL, "t2": FAIL, "h1": FAIL},
        {"t1": PASS, "t2": PASS, "h1": FAIL},
        ["h1"],
    )
    tuning, held_out = result["partitions"]["tuning"], result["partitions"]["held_out"]
    assert tuning["baseline"]["pass_rate"] == 0 and tuning["current"]["pass_rate"] == 1
    assert tuning["improved_beyond_noise"] and tuning["within_sampling_noise"] is False
    assert held_out["delta"] == 0 and not held_out["improved_beyond_noise"]


def test_recorded_inspect_example_gain_is_within_noise():
    runs = [load_results(EXAMPLES / f"inspect/{name}.json") for name in ("baseline", "current")]
    result = diff(*runs)
    split = load_split(EXAMPLES / "inspect/split.json")
    review_result = review_split(*runs, result, split)
    assert review_result["split"]["held_out_cases"] == [
        "address-change",
        "status-missing",
        "status-open",
    ]
    assert review_result["state"] == "held_out_gain_within_noise"
    held_out = review_result["partitions"]["held_out"]
    assert (held_out["baseline"]["passed"], held_out["current"]["passed"]) == (8, 12)
    assert held_out["blocking_changes"] == 0
    assert review_result["partitions"]["tuning"]["blocking_changes"] == 3


def test_glob_and_exact_entries_must_each_match(tmp_path):
    split = load_split(split_file(tmp_path / "s.json", ["status-*", "address-change"]))
    cases = {"status-open", "status-missing", "address-change", "refund-small"}
    assert partition(split, cases) == {"status-open", "status-missing", "address-change"}
    with pytest.raises(ValueError, match="matches no recorded case"):
        partition(load_split(split_file(tmp_path / "m.json", ["missing"])), cases)
    with pytest.raises(ValueError, match="every case is held out"):
        partition(load_split(split_file(tmp_path / "a.json", ["*"])), cases)


@pytest.mark.parametrize(
    "document,message",
    [
        ({"schema_version": "other", "held_out": ["a"]}, "schema_version"),
        ({"schema_version": "evalarc.case-split.v1", "held_out": []}, "held_out must list"),
        ({"schema_version": "evalarc.case-split.v1", "held_out": ["a", "a"]}, "twice"),
        ({"schema_version": "evalarc.case-split.v1", "held_out": [1]}, "held_out must list"),
        (
            {"schema_version": "evalarc.case-split.v1", "held_out": ["a"], "train": ["b"]},
            "unknown fields",
        ),
        ([1], "JSON object"),
    ],
)
def test_invalid_splits_are_rejected(tmp_path, document, message):
    path = tmp_path / "split.json"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match=message):
        load_split(path)


def test_harness_scan_finds_verbatim_expected_answers(tmp_path):
    runs = [
        load_results(
            inspect_log(
                tmp_path / "run.json",
                {"h1": [True], "t1": [True]},
                inputs={"h1": "Where is parcel 4471?", "t1": "Cancel order 88"},
            )
        )
    ]
    harness = tmp_path / "harness"
    (harness / ".git").mkdir(parents=True)
    (harness / ".git" / "HEAD").write_text("answer-for-h1")
    (harness / "prompt.md").write_text("Rules\n\nExample:  ANSWER-FOR-H1\n")
    (harness / "tools.json").write_text('{"description": "Cancel order 88"}')
    (harness / "blob.bin").write_bytes(b"\xff\xfe answer-for-t1")
    result = scan_harness([harness], runs, held_out={"h1"}, min_chars=12)
    found = [
        (hit["file"].rsplit("/", 1)[-1], hit["case_id"], hit["role"]) for hit in result["hits"]
    ]
    # Case-insensitive, whitespace-normalized; hidden folders and binary files skipped;
    # the 15-character input "Cancel order 88" is long enough to count.
    assert found == [("prompt.md", "h1", "expected"), ("tools.json", "t1", "input")]
    assert result["hits"][0]["line"] == 3
    assert result["hits"][0]["partition"] == "held_out"
    assert result["held_out_hits"] == 1
    assert {Path(item["path"]).name for item in result["files_scanned"]} == {
        "prompt.md",
        "tools.json",
    }
    shorter = scan_harness([harness], runs, held_out={"h1"}, min_chars=16)
    assert [hit["case_id"] for hit in shorter["hits"]] == []


def test_harness_scan_rejects_missing_paths_and_tiny_thresholds(tmp_path):
    runs = [load_results(inspect_log(tmp_path / "run.json", {"a": [True], "b": [True]}))]
    with pytest.raises(ValueError, match="does not exist"):
        scan_harness([tmp_path / "missing"], runs)
    with pytest.raises(ValueError, match="at least 4"):
        scan_harness([tmp_path], runs, min_chars=2)


def test_promptfoo_negated_and_code_assertions_are_not_expected_answers():
    folder = EXAMPLES / "promptfoo"
    runs = [load_results(folder / f"{name}.json") for name in ("baseline", "current")]
    result = scan_harness([folder / "baseline.txt", folder / "current.txt"], runs)
    # The scripted echo prompts contain phrases that two tests positively expect. A
    # `not-icontains` value on another test is forbidden text, not an answer, and a
    # `javascript` assertion is grader code; neither is reported.
    assert sorted({(hit["case_id"], hit["text"]) for hit in result["hits"]}) == [
        ("duplicate refund is rejected", "already refunded"),
        ("small refund is approved", "refund approved"),
    ]
    assert {hit["role"] for hit in result["hits"]} == {"expected"}


def test_cli_diff_with_split_and_harness_writes_sections(tmp_path, capsys):
    output = tmp_path / "review"
    code = main(
        [
            "diff",
            str(EXAMPLES / "inspect/baseline.json"),
            str(EXAMPLES / "inspect/current.json"),
            "--held-out",
            str(EXAMPLES / "inspect/split.json"),
            "--harness",
            str(EXAMPLES / "inspect/harness"),
            "--output",
            str(output),
        ]
    )
    assert code == 1
    printed = capsys.readouterr().out
    assert "Held-out split: held_out_gain_within_noise" in printed
    assert "Harness leakage: 2 hit(s) in 1 file(s), 2 from held-out cases" in printed
    assert (output / "split.json").read_bytes() == (EXAMPLES / "inspect/split.json").read_bytes()
    saved = json.loads((output / "diff.json").read_text())
    assert saved["generalization"]["state"] == "held_out_gain_within_noise"
    assert [hit["case_id"] for hit in saved["leakage"]["hits"]] == ["status-missing"] * 2
    assert saved["gate_passed"] is False
    summary = (output / "summary.md").read_text()
    assert "#### Held-out split: `held_out_gain_within_noise`" in summary
    assert "#### Harness leakage: 2 hit(s), 2 from held-out cases" in summary
    page = (output / "index.html").read_text()
    assert "Held-out split" in page and "Harness leakage" in page


def test_require_generalization_gate(tmp_path, capsys):
    before = inspect_log(tmp_path / "b.json", {"t1": FAIL, "h1": FAIL})
    after = inspect_log(tmp_path / "c.json", {"t1": PASS, "h1": PASS})
    split = split_file(tmp_path / "split.json", ["h1"])
    args = ["diff", str(before), str(after), "--held-out", str(split)]
    assert main([*args, "--require-generalization"]) == 0
    overfit = inspect_log(tmp_path / "o.json", {"t1": PASS, "h1": FAIL})
    assert main(["diff", str(before), str(overfit), "--held-out", str(split)]) == 0
    assert (
        main(
            [
                "diff",
                str(before),
                str(overfit),
                "--held-out",
                str(split),
                "--require-generalization",
            ]
        )
        == 1
    )
    assert "Generalization is required" in capsys.readouterr().out
    # A held-out answer copied into the harness blocks a required generalization.
    harness = tmp_path / "prompt.md"
    harness.write_text("Always answer answer-for-h1 when unsure.")
    assert main([*args, "--harness", str(harness), "--require-generalization"]) == 1
    assert main([*args, "--harness", str(harness)]) == 0


@pytest.mark.parametrize(
    "extra,message",
    [
        (["--require-generalization"], "requires --held-out"),
        (["--held-out", "missing-split.json"], "No such file"),
        (["--harness", "missing-harness"], "does not exist"),
    ],
)
def test_cli_rejects_unusable_generalization_inputs(tmp_path, capsys, extra, message):
    path = str(EXAMPLES / "inspect/current.json")
    extra = [str(tmp_path / item) if item.startswith("missing") else item for item in extra]
    assert main(["diff", path, path, *extra]) == 2
    assert message in capsys.readouterr().err


def test_markdown_without_split_has_no_split_section():
    runs = [load_results(EXAMPLES / f"inspect/{name}.json") for name in ("baseline", "current")]
    assert "Held-out split" not in render_markdown(diff(*runs))

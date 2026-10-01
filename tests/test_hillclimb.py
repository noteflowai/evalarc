import json
import subprocess
import sys
from pathlib import Path

import pytest

from evalarc.cli import main
from evalarc.eval_health import health
from evalarc.generalization import load_split
from evalarc.hillclimb import review
from evalarc.results_diff import diff, load_results

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/hillclimb-review"
STEPS = sorted((EXAMPLE / "results").glob("0*.json"))


def inspect_log(path, outcomes, cost=0.01, answers=None, stop=None, scorers=None, model="m/a"):
    """outcomes: case -> list of pass booleans. answers: case -> list of completions."""
    samples = []
    for case_id, passes in outcomes.items():
        for epoch, passed in enumerate(passes, start=1):
            completion = (answers or {}).get(case_id, [f"{case_id}-{epoch}"] * len(passes))[
                epoch - 1
            ]
            output = {"completion": completion, "choices": []}
            if stop:
                output["stop_reason"] = stop
            samples.append(
                {
                    "id": case_id,
                    "epoch": epoch,
                    "input": "q",
                    "target": "a",
                    "output": output,
                    "scores": {"check": {"value": "C" if passed else "I"}},
                    "model_usage": {model: {"total_tokens": 100, "total_cost": cost}},
                }
            )
    spec = {"task": "t", "model": model, "config": {}, "scorers": scorers or []}
    path.write_text(json.dumps({"status": "success", "eval": spec, "samples": samples}))
    return load_results(path)


def split(tmp_path, held_out=("h1", "h2")):
    path = tmp_path / "split.json"
    path.write_text(
        json.dumps({"schema_version": "evalarc.case-split.v1", "held_out": list(held_out)})
    )
    return load_split(path)


ON, OFF = [True] * 8, [False] * 8


def case_map(t1, t2, h1, h2):
    return {"t1": t1, "t2": t2, "h1": h1, "h2": h2}


# --- example ---------------------------------------------------------------------


def test_example_is_regenerated_byte_for_byte(tmp_path):
    before = {p.name: p.read_bytes() for p in [*STEPS, EXAMPLE / "split.json"]}
    subprocess.run([sys.executable, str(EXAMPLE / "build.py")], check=True)
    after = {p.name: p.read_bytes() for p in [*STEPS, EXAMPLE / "split.json"]}
    assert before == after
    assert len(STEPS) == 6


def test_example_cost_objective_decisions_and_merge():
    runs = [load_results(path) for path in STEPS]
    result = review(runs, load_split(EXAMPLE / "split.json"), "cost", min_effect=0.05)
    assert [step["decision"] for step in result["steps"]] == [
        "keep",
        "rollback_overfit",
        "keep",
        "rollback_regression",
        "keep",
    ]
    assert result["steps"][1]["compared_with"] == "01-prompt-audit.json"
    assert result["final"]["label"] == "05-sonnet-5-low.json"
    assert result["final"]["cost"]["ratio"] == pytest.approx(0.010 / 0.046)
    assert result["final"]["held_out"]["within_sampling_noise"] is True
    assert result["recommendation"] == "merge_cost" and result["merge_recommended"]
    assert len(result["notes"]) == 2 and "Add cases or repetitions" in result["notes"][0]
    assert result["stalls"] == []
    # Held-out failures never reach the file a tuning loop reads.
    assert all(not row["case_id"].startswith("holdout") for row in result["tuning_failures"])


def test_example_quality_objective_stalls_and_withholds_merge():
    runs = [load_results(path) for path in STEPS]
    result = review(runs, load_split(EXAMPLE / "split.json"), "quality")
    assert [step["decision"] for step in result["steps"]] == [
        "keep",
        "rollback_overfit",
        "rollback_no_gain",
        "rollback_regression",
        "rollback_no_gain",
    ]
    assert [stall["after_step"] for stall in result["stalls"]] == [3]
    stall = result["stalls"][0]
    assert stall["categories"] == {"variable": 4}
    assert stall["headroom_below_noise"] is True
    assert result["recommendation"] == "do_not_merge_within_noise"


# --- decision rules --------------------------------------------------------------


def test_held_out_regression_rolls_back_even_when_tuning_improves(tmp_path):
    base = inspect_log(tmp_path / "0.json", case_map(OFF, OFF, ON, ON))
    step = inspect_log(tmp_path / "1.json", case_map(ON, ON, OFF, ON))
    result = review([base, step], split(tmp_path))
    assert result["steps"][0]["decision"] == "rollback_regression"
    assert result["steps"][0]["held_out_blocking_changes"] == [
        {"case_id": "h1", "check": "check", "kind": "regressed"}
    ]
    assert result["recommendation"] == "no_change_kept"


def test_held_out_loss_of_coverage_rolls_back(tmp_path):
    # Same pass rate on fewer assessed attempts is less_covered, which blocks the gate.
    base = inspect_log(tmp_path / "0.json", case_map(OFF, OFF, ON, ON))
    step = inspect_log(tmp_path / "1.json", case_map(ON, ON, [True] * 4, ON))
    result = review([base, step], split(tmp_path))
    assert result["steps"][0]["decision"] == "rollback_regression"
    assert result["steps"][0]["held_out_blocking_changes"] == [
        {"case_id": "h1", "check": "check", "kind": "less_covered"}
    ]


def test_quality_merge_requires_held_out_gain_beyond_noise(tmp_path):
    base = inspect_log(tmp_path / "0.json", case_map(OFF, OFF, OFF, OFF))
    step = inspect_log(tmp_path / "1.json", case_map(ON, ON, ON, ON))
    result = review([base, step], split(tmp_path))
    assert result["steps"][0]["decision"] == "keep"
    assert result["recommendation"] == "merge" and result["merge_recommended"]


def test_later_steps_compare_with_last_kept_result(tmp_path):
    base = inspect_log(tmp_path / "0.json", case_map(OFF, OFF, OFF, OFF))
    good = inspect_log(tmp_path / "1.json", case_map(ON, OFF, ON, OFF))
    overfit = inspect_log(tmp_path / "2.json", case_map(ON, ON, ON, OFF))
    result = review([base, good, overfit], split(tmp_path))
    assert [s["decision"] for s in result["steps"]] == ["keep", "rollback_overfit"]
    assert result["steps"][1]["compared_with"] == "1.json"
    assert result["final"]["label"] == "1.json"


def test_cost_objective_needs_recorded_cost(tmp_path):
    base = inspect_log(tmp_path / "0.json", case_map(ON, ON, ON, ON), cost=0.02)
    cheaper = inspect_log(tmp_path / "1.json", case_map(ON, ON, ON, ON), cost=0.01)
    result = review([base, cheaper], split(tmp_path), "cost", max_cost_ratio=0.6)
    assert result["steps"][0]["decision"] == "keep"
    assert result["recommendation"] == "merge_cost"
    strict = review([base, cheaper], split(tmp_path), "cost", max_cost_ratio=0.4)
    assert strict["recommendation"] == "do_not_merge_cost"
    for sample_file in (tmp_path / "0.json", tmp_path / "1.json"):
        document = json.loads(sample_file.read_text())
        for sample in document["samples"]:
            sample["model_usage"] = {}
        sample_file.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="--objective cost needs recorded cost"):
        review(
            [load_results(tmp_path / "0.json"), load_results(tmp_path / "1.json")],
            split(tmp_path),
            "cost",
        )


def test_cost_objective_still_rejects_overfitting(tmp_path):
    base = inspect_log(tmp_path / "0.json", case_map(OFF, OFF, OFF, OFF), cost=0.02)
    overfit = inspect_log(tmp_path / "1.json", case_map(ON, ON, OFF, OFF), cost=0.01)
    result = review([base, overfit], split(tmp_path), "cost")
    assert result["steps"][0]["decision"] == "rollback_overfit"
    assert result["recommendation"] == "no_change_kept"


def test_cost_merge_blocked_when_final_is_worse_than_baseline():
    from evalarc.hillclimb import _recommend

    comparison = {
        "held_out": {"delta": 0.0, "within_sampling_noise": True},
        "tuning": {"delta": -0.05},
        "held_out_blocking_changes": 0,
        "cost": {"ratio": 0.5},
    }
    assert _recommend("cost", 1, comparison, None, 1.0) == "do_not_merge_regression"
    comparison["tuning"]["delta"] = 0.0
    assert _recommend("cost", 1, comparison, None, 1.0) == "merge_cost"
    assert _recommend("cost", 0, comparison, None, 1.0) == "no_change_kept"


def test_harness_leakage_blocks_merge(tmp_path):
    base = inspect_log(tmp_path / "0.json", case_map(OFF, OFF, OFF, OFF))
    step = inspect_log(tmp_path / "1.json", case_map(ON, ON, ON, ON))
    document = json.loads((tmp_path / "1.json").read_text())
    for sample in document["samples"]:
        sample["target"] = f"reference answer for {sample['id']}"
    (tmp_path / "1.json").write_text(json.dumps(document))
    step = load_results(tmp_path / "1.json")
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Remember: reference answer for h2.")
    result = review([base, step], split(tmp_path), harness=[prompt])
    assert result["leakage"]["held_out_hits"] == 1
    assert result["recommendation"] == "do_not_merge_leakage"


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"objective": "speed"}, "--objective"),
        ({"stall_after": 0}, "--stall-after"),
        ({"min_effect": 2}, "--min-effect"),
    ],
)
def test_invalid_options(tmp_path, kwargs, message):
    base = inspect_log(tmp_path / "0.json", case_map(ON, ON, ON, ON))
    with pytest.raises(ValueError, match=message):
        review([base, base], split(tmp_path), **kwargs)


def test_case_sets_must_match(tmp_path):
    base = inspect_log(tmp_path / "0.json", case_map(ON, ON, ON, ON))
    fewer = inspect_log(tmp_path / "1.json", {"t1": ON, "h1": ON, "h2": ON})
    with pytest.raises(ValueError, match="same cases"):
        review([base, fewer], split(tmp_path))


def test_cli_writes_report_and_exit_codes(tmp_path, capsys):
    output = tmp_path / "review"
    args = ["hillclimb-review", *map(str, STEPS), "--held-out", str(EXAMPLE / "split.json")]
    assert (
        main([*args, "--objective", "cost", "--min-effect", "0.05", "--output", str(output)]) == 0
    )
    printed = capsys.readouterr().out
    assert "Note: Before the first step" in printed
    assert "2. 02-refund-examples.json: rollback_overfit" in printed
    assert "Recommendation: merge_cost" in printed
    assert sorted(p.name for p in output.iterdir()) == [
        "hillclimb.json",
        "index.html",
        "inputs",
        "split.json",
        "summary.md",
        "tuning-failures.json",
    ]
    assert len(list((output / "inputs").iterdir())) == 6
    failures = json.loads((output / "tuning-failures.json").read_text())
    assert failures["held_out_excluded"] is True
    assert "holdout" not in json.dumps(failures["failures"])
    assert "Content-Security-Policy" in (output / "index.html").read_text()
    assert "`rollback_overfit`" in (output / "summary.md").read_text()
    assert main(args) == 1
    assert "Stalled after step 3" in capsys.readouterr().out
    assert main([*args[:2], str(STEPS[0]), "--held-out", str(EXAMPLE / "split.json")]) == 2
    assert "appear once" in capsys.readouterr().err


# --- grader consistency, truncation, self-grading, triage ------------------------


def test_same_output_graded_differently_is_flagged(tmp_path):
    answers = {"t1": ["same", "same"], "h1": ["x", "y"]}
    before = inspect_log(
        tmp_path / "a.json", {"t1": [True, True], "h1": [True, True]}, answers=answers
    )
    after = inspect_log(
        tmp_path / "b.json", {"t1": [False, True], "h1": [True, True]}, answers=answers
    )
    result = diff(before, after)
    row = next(row for row in result["changes"] if row["case_id"] == "t1")
    assert row["same_output_different_verdict"] == 1
    assert result["changes_with_same_output_different_verdict"] == 1
    report = health([before, after])
    finding = next(f for f in report["findings"] if f["id"] == "inconsistent_grading")
    assert finding["items"][0]["case_id"] == "t1"
    assert {row["case_id"]: row["category"] for row in report["triage"]} == {
        "t1": "grader_inconsistent"
    }


def test_different_outputs_are_not_grading_conflicts(tmp_path):
    before = inspect_log(tmp_path / "a.json", {"t1": [True, True]}, answers={"t1": ["a", "b"]})
    after = inspect_log(tmp_path / "b.json", {"t1": [False, True]}, answers={"t1": ["c", "b"]})
    assert "same_output_different_verdict" not in diff(before, after)["changes"][0]


def test_truncated_outputs_and_self_grading(tmp_path):
    run = inspect_log(
        tmp_path / "a.json",
        {"t1": [False, False], "t2": [True, True]},
        stop="max_tokens",
        scorers=[{"name": "model_graded_qa", "options": {}}],
        model="anthropic/sonnet",
    )
    report = health([run])
    ids = {f["id"] for f in report["findings"]}
    assert {"truncated_outputs", "self_graded"} <= ids
    assert report["graders"]["self_graded"] == ["anthropic/sonnet"]
    assert report["runs"][0]["truncated_attempts"] == 4
    assert {row["case_id"]: row["category"] for row in report["triage"]} == {"t1": "truncated"}
    separate = inspect_log(
        tmp_path / "b.json",
        {"t1": [True]},
        scorers=[{"name": "model_graded_qa", "options": {"model": "openai/judge"}}],
        model="anthropic/sonnet",
    )
    assert "self_graded" not in {f["id"] for f in health([separate])["findings"]}


def test_summaries_carry_intervals(tmp_path):
    run = inspect_log(tmp_path / "a.json", {"t1": [True, False], "t2": [True, True]})
    summary = diff(run, run)["current"]["check_pass_rate"]
    assert summary["passed"] == 3 and summary["assessed"] == 4
    low, high = summary["interval_95"]
    assert 0.3 < low < 0.75 < high <= 1
    assert health([run])["runs"][0]["interval_95"] == summary["interval_95"]

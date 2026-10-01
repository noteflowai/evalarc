import copy
import json
from pathlib import Path

import pytest

from evalarc.cli import main
from evalarc.results_diff import diff, load_results, render_markdown
from evalarc.usage import cost_gate

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/results-diff"


def inspect_log(path, cases, tokens, cost=None, missing=()):
    """Every case passes once; `tokens` is total tokens per sample."""
    samples = []
    for case_id in cases:
        usage = {"input_tokens": tokens - 10, "output_tokens": 10, "total_tokens": tokens}
        if cost is not None:
            usage["total_cost"] = cost
        sample = {
            "id": case_id,
            "epoch": 1,
            "input": "q",
            "target": "a",
            "scores": {"match": {"value": "C"}},
            "working_time": 2.0,
            "total_time": 3.0,
            "model_usage": {} if case_id in missing else {"provider/model": usage},
        }
        samples.append(sample)
    path.write_text(
        json.dumps({"status": "success", "eval": {"task": "t", "config": {}}, "samples": samples})
    )
    return path


def test_inspect_usage_is_summed_per_sample_and_compared(tmp_path):
    before = inspect_log(tmp_path / "b.json", ["a", "b"], tokens=1000, cost=0.02)
    after = inspect_log(tmp_path / "c.json", ["a", "b"], tokens=400, cost=0.005)
    result = diff(load_results(before), load_results(after))
    metrics = result["usage"]["metrics"]
    assert result["usage"]["matched_cases"] == 2
    assert metrics["total_tokens"]["baseline"]["mean"] == 1000
    assert metrics["total_tokens"]["ratio"] == pytest.approx(0.4)
    assert metrics["cost_usd"]["ratio"] == pytest.approx(0.25)
    # Working time is preferred over total time.
    assert metrics["duration_seconds"]["baseline"]["mean"] == 2.0
    gate = cost_gate(result["usage"], "auto", 0.5)
    assert (gate["metric"], gate["passed"]) == ("cost_usd", True)
    assert cost_gate(result["usage"], "tokens", 0.3)["passed"] is False
    markdown = render_markdown({**result, "cost_gate": gate})
    assert "#### Cost and usage" in markdown
    assert "Cost gate on `cost_usd`: current/baseline = 0.250 (limit 0.5) — **pass**" in markdown


def test_missing_usage_is_unknown_not_zero(tmp_path):
    before = inspect_log(tmp_path / "b.json", ["a", "b"], tokens=1000)
    after = inspect_log(tmp_path / "c.json", ["a", "b"], tokens=500, missing={"b"})
    usage = diff(load_results(before), load_results(after))["usage"]
    tokens = usage["metrics"]["total_tokens"]
    assert tokens["current"] == {"attempts": 2, "reported": 1, "total": 500.0, "mean": 500.0}
    assert tokens["complete"] is False
    assert "cost_usd" not in usage["metrics"]
    # A gate on incompletely recorded usage cannot be assessed.
    with pytest.raises(ValueError, match="neither run records"):
        cost_gate(usage, "auto", 1.0)
    with pytest.raises(ValueError, match="cannot be assessed"):
        cost_gate(usage, "tokens", 1.0)


def test_only_matched_cases_are_averaged(tmp_path):
    before = inspect_log(tmp_path / "b.json", ["a", "b", "extra"], tokens=100)
    after = inspect_log(tmp_path / "c.json", ["a", "b"], tokens=100)
    usage = diff(load_results(before), load_results(after))["usage"]
    assert usage["matched_cases"] == 2
    assert usage["metrics"]["total_tokens"]["baseline"]["attempts"] == 2


def test_promptfoo_usage_and_zero_baseline(tmp_path):
    document = json.loads((EXAMPLES / "promptfoo/current.json").read_text())
    priced = copy.deepcopy(document)
    for row in priced["results"]["results"]:
        row["cost"] = 0.01
        row["tokenUsage"].update({"prompt": 90, "completion": 10, "total": 100})
        row["latencyMs"] = 250
    cheaper = copy.deepcopy(priced)
    for row in cheaper["results"]["results"]:
        row["cost"] = 0.004
    (tmp_path / "a.json").write_text(json.dumps(priced))
    (tmp_path / "b.json").write_text(json.dumps(cheaper))
    result = diff(load_results(tmp_path / "a.json"), load_results(tmp_path / "b.json"))
    metrics = result["usage"]["metrics"]
    assert metrics["cost_usd"]["ratio"] == pytest.approx(0.4)
    assert metrics["input_tokens"]["current"]["mean"] == 90
    assert metrics["duration_seconds"]["current"]["mean"] == 0.25
    # The recorded echo runs report zero cost and tokens: no ratio, no default section.
    recorded = diff(
        *(load_results(EXAMPLES / f"promptfoo/{n}.json") for n in ("baseline", "current"))
    )
    assert recorded["usage"]["metrics"]["cost_usd"]["ratio"] is None
    assert "Cost and usage" not in render_markdown(recorded)
    with pytest.raises(ValueError, match="neither run records"):
        cost_gate(recorded["usage"], "auto", 1.0)


def test_junit_records_test_durations_only():
    result = diff(*(load_results(EXAMPLES / f"junit/{n}.xml") for n in ("baseline", "current")))
    assert list(result["usage"]["metrics"]) == ["duration_seconds"]
    assert "Cost and usage" not in render_markdown(result)


def test_invalid_ratio_is_rejected(tmp_path):
    before = inspect_log(tmp_path / "b.json", ["a"], tokens=100)
    usage = diff(load_results(before), load_results(before))["usage"]
    for ratio in (0, -1, float("nan")):
        with pytest.raises(ValueError, match="positive"):
            cost_gate(usage, "tokens", ratio)


def test_cli_cost_gate(tmp_path, capsys):
    before = inspect_log(tmp_path / "b.json", ["a", "b"], tokens=1000, cost=0.02)
    after = inspect_log(tmp_path / "c.json", ["a", "b"], tokens=900, cost=0.018)
    args = ["diff", str(before), str(after)]
    assert main(args) == 0
    assert main([*args, "--max-cost-ratio", "0.5"]) == 1
    assert (
        "Cost gate (cost_usd): current/baseline 0.900, limit 0.5 — fail" in capsys.readouterr().out
    )
    output = tmp_path / "review"
    assert main([*args, "--max-cost-ratio", "1.0", "--output", str(output)]) == 0
    saved = json.loads((output / "diff.json").read_text())
    assert saved["cost_gate"]["passed"] is True and saved["gate_passed"] is True
    assert "Cost and usage" in (output / "index.html").read_text()
    # Quality regressions still fail even when cost falls.
    code = main(
        [
            "diff",
            str(EXAMPLES / "inspect/baseline.json"),
            str(EXAMPLES / "inspect/current.json"),
            "--max-cost-ratio",
            "2",
            "--cost-metric",
            "duration",
        ]
    )
    assert code == 1
    # Unassessable cost gate is unusable input.
    promptfoo = str(EXAMPLES / "promptfoo/current.json")
    assert main(["diff", promptfoo, promptfoo, "--max-cost-ratio", "1"]) == 2
    assert "neither run records" in capsys.readouterr().err


def test_cache_read_share(tmp_path):
    def log(path, cached):
        samples = [
            {
                "id": "a",
                "epoch": 1,
                "input": "q",
                "target": "a",
                "scores": {"m": {"value": "C"}},
                "model_usage": {
                    "x": {
                        "input_tokens": 1000,
                        "output_tokens": 10,
                        "total_tokens": 1010,
                        "input_tokens_cache_read": cached,
                    }
                },
            }
        ]
        path.write_text(
            json.dumps({"status": "success", "eval": {"task": "t"}, "samples": samples})
        )
        return load_results(path)

    result = diff(log(tmp_path / "a.json", 0), log(tmp_path / "b.json", 800))
    assert result["usage"]["cache_read_share"] == {"baseline": 0.0, "current": 0.8}
    assert "Prompt cache reads: 0.0% → 80.0% of input tokens." in render_markdown(result)

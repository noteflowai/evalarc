"""--transcript-metrics, --cluster-errors and judge-packet --include-transcript."""

import copy
import json
from pathlib import Path

import pytest

from evalarc import evidence
from evalarc.cli import main
from evalarc.eval_health import health
from evalarc.judging import prepare, transcript_excerpt
from evalarc.results_diff import load_results, transcript_counts
from evalarc.transcripts import correlated_items, normalize_error

ROOT = Path(__file__).resolve().parents[1]
INSPECT = ROOT / "examples/results-diff/inspect"
PARAMS = {
    "format": "auto",
    "threshold": 1.0,
    "leak_min_chars": 24,
    "require_generalization": False,
    "max_cost_ratio": None,
    "cost_metric": "auto",
}


def with_transcripts(name, path, calls=None, limits=(), errors=()):
    """Copy a recorded example, adding an agent transcript to every sample."""
    document = json.loads((INSPECT / f"{name}.json").read_text())
    for sample in document["samples"]:
        n = (calls or {}).get(sample["id"], 1)
        messages = [
            {"role": "system", "content": "Route refunds."},
            {"role": "user", "content": "q"},
        ]
        for k in range(n):
            messages.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"id": f"c{k}", "function": "lookup", "arguments": {"k": k}}],
                }
            )
            messages.append({"role": "tool", "function": "lookup", "content": "ok"})
        messages.append(
            {
                "role": "assistant",
                "content": [{"type": "text", "text": sample["output"]["completion"]}],
            }
        )
        sample["messages"] = messages
        if sample["id"] in limits:
            sample["limit"] = {"type": "message", "limit": 12}
        if sample["id"] in errors and sample["epoch"] == 1:
            sample.pop("scores")
            sample["error"] = {"message": f"RateLimitError 429 request {sample['id']}x91ab77"}
    path.write_text(json.dumps(document))
    return load_results(path)


def test_counts():
    messages = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "tool_calls": [{"function": "a"}, {"function": "b"}]},
        {"role": "tool", "content": "x"},
        {"role": "assistant", "content": "done"},
        "not a message",
    ]
    assert transcript_counts(messages, [{"message": "retry"}]) == {
        "n_turns": 2,
        "n_tool_calls": 2,
        "n_messages": 5,
        "n_error_retries": 1,
    }
    assert "n_error_retries" not in transcript_counts([], None)


def test_diff_transcript_metrics_and_turn_gate(tmp_path):
    base = with_transcripts("baseline", tmp_path / "b.json")
    cur = with_transcripts("baseline", tmp_path / "c.json", calls={"refund-duplicate": 5})
    plain = evidence.compute_diff([base, cur], PARAMS, None, [])
    assert "n_turns" not in plain["usage"]["metrics"] and "transcripts" not in plain["usage"]
    result = evidence.compute_diff(
        [base, cur],
        {**PARAMS, "transcript_metrics": True, "max_cost_ratio": 1.2, "cost_metric": "turns"},
        None,
        [],
    )
    turns = result["usage"]["metrics"]["n_turns"]
    assert turns["baseline"]["mean"] == 2 and turns["current"]["mean"] == 2.5
    assert result["cost_gate"]["metric"] == "n_turns" and result["cost_gate"]["passed"] is False
    calls = result["usage"]["metrics"]["n_tool_calls"]
    assert calls["ratio"] == pytest.approx(1.5)
    with pytest.raises(ValueError, match="requires --transcript-metrics"):
        evidence.compute_diff(
            [base, cur], {**PARAMS, "max_cost_ratio": 1, "cost_metric": "tool_calls"}, None, []
        )
    with pytest.raises(ValueError, match="transcript_metrics must be true or false"):
        evidence.compute_diff([base, cur], {**PARAMS, "transcript_metrics": 1}, None, [])


def test_promptfoo_and_junit_report_transcripts_as_unknown():
    for fmt, ext in (("promptfoo", "json"), ("junit", "xml")):
        runs = [
            load_results(ROOT / f"examples/results-diff/{fmt}/{n}.{ext}")
            for n in ("baseline", "current")
        ]
        result = evidence.compute_diff(runs, {**PARAMS, "transcript_metrics": True}, None, [])
        assert not any(name.startswith("n_") for name in result["usage"]["metrics"])
        with pytest.raises(ValueError, match="not recorded on every attempt"):
            evidence.compute_diff(
                runs,
                {**PARAMS, "transcript_metrics": True, "max_cost_ratio": 1, "cost_metric": "turns"},
                None,
                [],
            )


def test_cli_diff_folder_records_the_option_and_verifies(tmp_path, capsys):
    with_transcripts("baseline", tmp_path / "b.json")
    with_transcripts("current", tmp_path / "c.json")
    out, plain = tmp_path / "d", tmp_path / "p"
    args = ["diff", str(tmp_path / "b.json"), str(tmp_path / "c.json")]
    main([*args, "--transcript-metrics", "--output", str(out)])
    main([*args, "--output", str(plain)])
    assert json.loads((out / "params.json").read_text())["transcript_metrics"] is True
    assert "transcript_metrics" not in json.loads((plain / "params.json").read_text())
    assert "`n_tool_calls`" in (out / "summary.md").read_text()
    capsys.readouterr()
    assert main(["verify", str(out), "--json"]) == 0
    params = json.loads((out / "params.json").read_text())
    params["transcript_metrics"] = False
    (out / "params.json").write_text(json.dumps(params))
    assert main(["verify", str(out), "--json"]) == 2


def test_health_limit_reached_and_transcript_summary(tmp_path):
    run = with_transcripts("current", tmp_path / "c.json", limits=("refund-large",))
    assert "transcripts" not in health([run]) and "limit_reached" not in {
        f["id"] for f in health([run])["findings"]
    }
    result = health([run], transcript_metrics=True)
    finding = next(f for f in result["findings"] if f["id"] == "limit_reached")
    assert finding["items"][0]["case_id"] == "refund-large"
    assert "message limit" in finding["items"][0]["detail"]
    summary = result["transcripts"][0]
    assert summary["attempts_with_transcript"] == summary["attempts"] == 16
    assert summary["mean"]["n_tool_calls"] == 1 and summary["max"]["n_turns"] == 2


def test_health_correlated_errors(tmp_path):
    run = with_transcripts(
        "current",
        tmp_path / "c.json",
        errors=("status-open", "status-missing", "address-change"),
    )
    assert "correlated_errors" not in {f["id"] for f in health([run])["findings"]}
    result = health([run], cluster_errors=True)
    finding = next(f for f in result["findings"] if f["id"] == "correlated_errors")
    item = finding["items"][0]
    assert item["cases"] == ["address-change", "status-missing", "status-open"]
    assert item["message"] == "RateLimitError # request #"
    two = with_transcripts("current", tmp_path / "d.json", errors=("status-open", "address-change"))
    assert correlated_items([two]) == []


def test_normalization_keeps_distinct_errors_apart():
    assert normalize_error("Timeout after 30s") == normalize_error("Timeout after 45.5s")
    assert normalize_error("connection refused") != normalize_error("permission denied")
    assert normalize_error("id 3f2a9c1b-0d4e-4f5a-9b6c-7d8e9f0a1b2c gone") == "id # gone"


def test_health_cli_options_are_recorded_and_verified(tmp_path, capsys):
    with_transcripts("current", tmp_path / "c.json", limits=("refund-large",))
    out = tmp_path / "h"
    assert (
        main(
            [
                "eval-health",
                str(tmp_path / "c.json"),
                "--transcript-metrics",
                "--cluster-errors",
                "--output",
                str(out),
            ]
        )
        == 0
    )
    params = json.loads((out / "params.json").read_text())
    assert params["transcript_metrics"] is True and params["cluster_errors"] is True
    assert "<h2>Recorded transcripts</h2>" in (out / "index.html").read_text()
    capsys.readouterr()
    assert main(["verify", str(out), "--json"]) == 0


def test_judge_packet_transcripts_are_blind_bounded_and_follow_a_b(tmp_path):
    base = with_transcripts("baseline", tmp_path / "b.json")
    cur = with_transcripts("current", tmp_path / "c.json", calls={"refund-duplicate": 3})
    packet, key = prepare("pairwise", [base, cur], 40, 7, transcript_chars=20_000)
    for item in packet["items"]:
        current_side = key["items"][item["item_id"]]["current_is"].lower()
        current = item[f"transcript_{current_side}"]
        assert current[-1]["text"] == item[f"output_{current_side}"]
    text = json.dumps(packet)
    assert '"scores"' not in text and "model_usage" not in text and "metadata" not in text
    grader, _ = prepare("grader", [cur], 4, 0, transcript_chars=200)
    for item in grader["items"]:
        kept = [entry for entry in item["transcript"] if entry["role"] != "excerpt"]
        size = sum(
            len(entry["text"])
            + sum(len(c["function"]) + len(c["arguments"]) for c in entry.get("tool_calls", []))
            for entry in kept
        )
        assert size <= 200
    default, _ = prepare("grader", [cur], 4, 0)
    assert "transcript" not in default["items"][0]
    with pytest.raises(ValueError, match="--transcript-max-chars"):
        prepare("grader", [cur], 4, 0, transcript_chars=10)


def test_excerpt_is_bounded_and_text_only():
    messages = [{"role": "user", "content": "x" * 5000}] * 3 + [
        {"role": "assistant", "content": [{"type": "image"}, {"type": "text", "text": "hi"}]}
    ]
    excerpt = transcript_excerpt(messages, 9000)
    assert len(excerpt[0]["text"]) == 4000
    assert excerpt[-1] == {"role": "excerpt", "text": "… 2 more message(s)"}
    assert transcript_excerpt(None, 1000) is None
    assert transcript_excerpt([messages[-1]], 1000)[0]["text"] == "[image]\nhi"


def test_sheet_escapes_transcripts(tmp_path):
    from evalarc.judging import render_sheet

    packet = {
        "mode": "grader",
        "instructions": "i",
        "allowed_verdicts": ["pass"],
        "items": [
            {
                "item_id": "item-001",
                "case_id": "c",
                "check": "k",
                "input": "q",
                "expected": "a",
                "output": "o",
                "transcript": [
                    {
                        "role": "<b>",
                        "text": "<script>x</script>",
                        "tool_calls": [{"function": "<i>", "arguments": "<img>"}],
                    }
                ],
            }
        ],
    }
    page = render_sheet(packet)
    assert "<script>x" not in page and "<img>" not in page and "&lt;script&gt;" in page


def test_fixture_copy_keeps_the_recorded_outputs(tmp_path):
    original = load_results(INSPECT / "current.json")
    copied = with_transcripts("current", tmp_path / "c.json")
    assert copy.deepcopy(original["cases"]) == copied["cases"]

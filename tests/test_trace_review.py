import copy
import json
from pathlib import Path

import pytest

from evalarc.cli import main
from evalarc.trace_review import (
    canonical,
    compare_reviews,
    import_trace,
    review,
    verify_trace,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def data():
    return json.loads((ROOT / "examples/trace-workbench/current.json").read_bytes())


def test_zero_skipped_missing_and_missed_skill_are_separate(data):
    result = review(canonical(data))
    assert result["summary"] == {"accepted": 1, "rejected": 2, "incomplete": 2}
    zero, skipped, missing, missed = result["cases"][1:]
    assert zero["results"][0]["status"] == "assessed"
    assert zero["results"][0]["value"] == 0
    assert zero["results"][0]["accepted"] is False
    assert skipped["results"][0]["status"] == "skipped"
    assert skipped["results"][0]["value"] is None
    assert missing["results"][0]["status"] == "missing"
    assert missed["expected_skills"] == [{"name": "evidence-review", "status": "not_called"}]
    assert missed["results"][1]["status"] == "not_applicable"


@pytest.mark.parametrize("kind", ["bundle_changed", "missing_receipt", "missing_coverage"])
def test_skill_identity_and_coverage_affect_gate(data, kind):
    case = data["cases"][0]
    if kind == "bundle_changed":
        case["skill_calls"][0]["receipt"]["bundle_sha256"] = "0" * 64
    elif kind == "missing_receipt":
        case["skill_calls"][0].pop("receipt")
    else:
        case["skill_observation_complete"] = False
    result = review(canonical(data))["cases"][0]
    assert result["gate"] == ("rejected" if kind == "bundle_changed" else "incomplete")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["cases"][0]["evaluation_response"]["evaluationResults"].append(
            copy.deepcopy(d["cases"][0]["evaluation_response"]["evaluationResults"][0])
        ),
        lambda d: d["cases"][0]["spans"][0]["attributes"].update({"session.id": "another"}),
        lambda d: d["cases"][0]["evaluation_response"]["evaluationResults"][0]["context"][
            "spanContext"
        ].update(sessionId="another"),
        lambda d: d["cases"][0]["evaluation_response"]["evaluationResults"][0].update(value=True),
        lambda d: d["cases"][0]["evaluation_response"]["evaluationResults"][0].update(value=2),
        lambda d: d["cases"][0]["skill_calls"][0].update(span_id="not-exported"),
        lambda d: d["cases"].pop(),
        lambda d: d["cases"][1].update(session_id=d["cases"][0]["session_id"]),
        lambda d: d["cases"][0]["skill_calls"][0]["receipt"].update(name="another"),
        lambda d: d["evaluators"][0]["rating"].update(pass_at_least=-1),
        lambda d: d["cases"][0].update(evaluation_response=[]),
    ],
)
def test_invalid_linkage_or_rating_is_rejected(data, mutation):
    mutation(data)
    with pytest.raises(ValueError):
        review(canonical(data))


def test_typed_otel_attributes_and_categorical_results(data):
    data["cases"][0]["spans"][0]["attributes"] = [
        {"key": "session.id", "value": {"stringValue": "session-0"}}
    ]
    data["evaluators"][0]["rating"] = {
        "kind": "categorical",
        "labels": ["Pass", "Fail"],
        "pass_labels": ["Pass"],
    }
    for case in data["cases"]:
        for result in case["evaluation_response"]["evaluationResults"]:
            if result["evaluatorId"] == "goal-control" and "value" in result:
                result["label"] = "Pass" if result.pop("value") else "Fail"
    result = review(canonical(data))
    assert result["cases"][0]["gate"] == "accepted"
    assert result["cases"][1]["results"][0]["value"] is None
    assert result["cases"][1]["results"][0]["accepted"] is False
    assert result["cases"][1]["gate"] == "rejected"


def test_comparison_requires_same_dataset_and_rubrics(data):
    current = review(canonical(data))
    baseline = review((ROOT / "examples/trace-workbench/baseline.json").read_bytes())
    comparison = compare_reviews(baseline, current)
    assert len([c for c in comparison["cases"] if c["regressed"]]) == 4
    assert list(comparison["configuration_changes"]) == ["prompt_sha256"]
    for field in ("dataset", "evaluators"):
        changed = copy.deepcopy(current)
        if field == "dataset":
            changed[field]["version"] = "2"
        else:
            changed[field][0]["rating"]["pass_at_least"] = 0.5
        with pytest.raises(ValueError, match=field):
            compare_reviews(baseline, changed)


def test_preserved_bytes_offline_verify_tamper_and_output_protection(tmp_path, data):
    source = tmp_path / "source.json"
    raw = json.dumps(data, indent=3).encode() + b"\n\n"
    source.write_bytes(raw)
    output = tmp_path / "review"
    import_trace(source, output, ROOT / "examples/trace-workbench/baseline.json")
    assert (output / "input.json").read_bytes() == raw
    assert verify_trace(output)["verified"]
    with pytest.raises(ValueError, match="already exists"):
        import_trace(source, output)
    document = json.loads((output / "review.json").read_bytes())
    document["summary"]["accepted"] += 1
    (output / "review.json").write_bytes(canonical(document))
    with pytest.raises(ValueError, match="differs"):
        verify_trace(output)


def test_untrusted_text_stays_text(tmp_path, data):
    data["dataset"]["cases"][0]["goal"] = '<img src=x onerror="window.pwned=1">'
    source = tmp_path / "input.json"
    source.write_bytes(canonical(data))
    import_trace(source, tmp_path / "out")
    page = (tmp_path / "out/index.html").read_text()
    assert "<img src=x" not in page
    assert "&lt;img src=x" in page
    assert 'data-gate="rejected"' in page


def test_duplicate_json_nonfinite_and_invalid_unicode_are_rejected(data):
    with pytest.raises(ValueError, match="duplicate JSON"):
        review(b'{"schema_version":1,"schema_version":2}')
    for content in (b'{"x":NaN}', b'{"x":"\\ud800"}'):
        with pytest.raises(ValueError):
            review(content)


def test_cli_import_and_gate_exit_are_distinct(tmp_path):
    source = ROOT / "examples/trace-workbench/current.json"
    assert main(["trace-import", str(source), "--output", str(tmp_path / "normal")]) == 0
    assert main(["trace-verify", str(tmp_path / "normal")]) == 0
    assert (
        main(
            [
                "trace-import",
                str(source),
                "--output",
                str(tmp_path / "gate"),
                "--require-accepted",
            ]
        )
        == 2
    )


def test_recorded_mcp_receipt_is_matched_but_not_a_task_score():
    result = review((ROOT / "examples/trace-workbench/mcp-recorded.json").read_bytes())
    assert result["provenance"]["kind"] == "recorded"
    case = result["cases"][0]
    assert case["expected_skills"] == [{"name": "evidence-review", "status": "matched"}]
    assert [row["status"] for row in case["results"]] == ["missing", "missing"]
    assert case["gate"] == "incomplete"

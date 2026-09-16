import copy
import json
from pathlib import Path

import pytest

from evalarc.cli import main
from evalarc.judge_stability import import_judgments, summarize, verify_judgments
from evalarc.trace_review import canonical

ROOT = Path(__file__).resolve().parents[1]


def examples():
    return [
        json.loads((ROOT / f"examples/judge-stability/judge-{index + 1}.json").read_bytes())
        for index in range(3)
    ]


def example():
    return json.loads((ROOT / "examples/trace-workbench/baseline.json").read_bytes())


def encoded(data):
    return [canonical(row) for row in data]


def test_score_changes_gate_flips_and_unavailable_judgments_are_distinct():
    result = summarize(encoded(examples()))
    assert result["summary"] == {
        "repetitions": 3,
        "required_targets": 5,
        "complete_targets": 4,
        "incomplete_targets": 1,
        "not_applicable_targets": 0,
        "gate_disagreements": 1,
        "score_disagreements": 2,
        "all_rejected_targets": 1,
    }
    targets = [c["targets"][0] for c in result["cases"]]
    assert [t["state"] for t in targets] == [
        "same_gate",
        "same_gate",
        "disagreement",
        "same_gate",
        "incomplete",
    ]
    assert targets[1]["observed_values"] == [0]
    assert targets[1]["passed"] == 0 and targets[1]["rejected"] == 3
    assert targets[3]["observed_score_disagreement"]
    assert not targets[3]["observed_gate_disagreement"]
    assert [r["status"] for r in targets[4]["observations"]] == ["assessed", "skipped", "missing"]
    assert targets[4]["assessed"] == 1 and targets[4]["expected"] == 3


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["configuration"].update(model="different-model"),
        lambda d: d["configuration"]["model_parameters"].update(temperature=0.5),
        lambda d: d["configuration"].update(prompt_sha256="0" * 64),
        lambda d: d["evaluators"][0].update(revision="other-revision"),
        lambda d: d["evaluators"][0]["rating"].update(pass_at_least=0.9),
        lambda d: d["dataset"].update(version="2"),
        lambda d: d["cases"][0]["spans"][0].update(name="changed-execution"),
        lambda d: d["cases"][0].update(skill_observation_complete=False),
        lambda d: d["provenance"].update(kind="recorded"),
        lambda d: d.update(unknown_metadata="changed"),
        lambda d: d["provenance"].update(collector="another"),
    ],
)
def test_mismatched_execution_or_judge_configuration_is_rejected(mutation):
    data = examples()
    mutation(data[1])
    with pytest.raises(ValueError, match="same recording"):
        summarize(encoded(data))


def test_renaming_an_agent_rerun_does_not_make_it_a_judge_repetition():
    data = examples()
    case = data[1]["cases"][0]
    case["session_id"] = "new-session"
    case["spans"][0]["attributes"]["session.id"] = "new-session"
    case["evaluation_response"]["evaluationResults"][0]["context"]["spanContext"]["sessionId"] = (
        "new-session"
    )
    with pytest.raises(ValueError, match="agent reruns"):
        summarize(encoded(data))


def test_categorical_labels_are_not_averaged_and_all_missing_is_not_agreement():
    data = examples()
    for run in data:
        run["evaluators"][0]["rating"] = {
            "kind": "categorical",
            "labels": ["Pass", "Fail"],
            "pass_labels": ["Pass"],
        }
        for case in run["cases"]:
            for row in case["evaluation_response"]["evaluationResults"]:
                if "value" in row:
                    row["label"] = "Pass" if row.pop("value") >= 0.8 else "Fail"
        run["cases"][-1]["evaluation_response"]["evaluationResults"] = []
    result = summarize(encoded(data))
    assert result["cases"][2]["targets"][0]["observed_values"] == ["Fail", "Pass"]
    missing = result["cases"][-1]["targets"][0]
    assert missing["state"] == "incomplete" and missing["assessed"] == 0
    assert missing["observed_values"] == []
    assert result["summary"]["score_disagreements"] == 1


def test_partial_evidence_can_show_disagreement_without_hiding_missing_judgments():
    data = examples()
    data[2]["cases"][2]["evaluation_response"]["evaluationResults"] = []
    row = summarize(encoded(data))["cases"][2]["targets"][0]
    assert row["state"] == "incomplete"
    assert row["observed_gate_disagreement"] is True
    assert (row["passed"], row["rejected"], row["unassessed"]) == (1, 1, 1)


def test_skill_and_trace_targets_are_separate_and_absent_skills_are_not_missing_scores():
    data = [example(), example()]
    data[1]["run_id"] = "another-judgment"
    spec = copy.deepcopy(data[0]["evaluators"][0])
    spec.update(id="trace-control", level="trace")
    for run in data:
        run["evaluators"].append(spec)
        for case in run["cases"]:
            case["evaluation_response"]["evaluationResults"].append(
                {
                    "evaluatorId": "trace-control",
                    "context": {
                        "spanContext": {
                            "sessionId": case["session_id"],
                            "traceId": case["trace_ids"][0],
                        }
                    },
                    "value": 1,
                }
            )
    result = summarize(encoded(data))
    assert result["summary"]["not_applicable_targets"] == 2
    assert result["summary"]["required_targets"] == 13
    assert result["summary"]["complete_targets"] == 13
    absent = result["cases"][2]["targets"][1]
    assert absent["state"] == "not_applicable" and absent["expected"] == 0
    assert absent["unassessed"] == 0


def test_agreeing_positive_judges_do_not_override_failed_skill_acceptance():
    data = [example(), example()]
    data[1]["run_id"] = "another-judgment"
    for run in data:
        run["cases"][0]["skill_calls"][0]["receipt"]["bundle_sha256"] = "0" * 64
    result = summarize(encoded(data))
    assert result["summary"]["incomplete_targets"] == 0
    assert result["summary"]["gate_disagreements"] == 0
    assert [row["gate"] for row in result["cases"][0]["case_gates"]] == ["rejected", "rejected"]
    assert all(row["state"] == "same_gate" for row in result["cases"][0]["targets"])


@pytest.mark.parametrize("count", [0, 1, 21])
def test_repetition_count_is_bounded(count):
    with pytest.raises(ValueError, match="2–20"):
        summarize([b"{}"] * count)


def test_duplicate_ids_invalid_input_and_total_size_are_rejected():
    data = examples()
    data[1]["run_id"] = data[0]["run_id"]
    with pytest.raises(ValueError, match="distinct"):
        summarize(encoded(data))
    with pytest.raises(ValueError, match="16 MiB"):
        summarize([b"x" * (4 * 1024 * 1024)] * 5)
    with pytest.raises(ValueError, match="duplicate JSON"):
        summarize([b'{"x":1,"x":2}', canonical(examples()[0])])


def write_inputs(tmp_path, data):
    paths = []
    for index, row in enumerate(data):
        path = tmp_path / f"judge-{index}.json"
        path.write_bytes(json.dumps(row, indent=3).encode() + b"\n\n")
        paths.append(path)
    return paths


def test_preserve_verify_tamper_and_protect_existing_output(tmp_path):
    paths = write_inputs(tmp_path, examples())
    output = tmp_path / "review"
    import_judgments(paths, output)
    for index, path in enumerate(paths):
        assert (output / f"inputs/{index + 1:04d}.json").read_bytes() == path.read_bytes()
    assert verify_judgments(output)["verified"]
    with pytest.raises(ValueError, match="already exists"):
        import_judgments(paths, output)
    original = (output / "stability.json").read_bytes()
    document = json.loads(original)
    document["summary"]["gate_disagreements"] = 0
    (output / "stability.json").write_bytes(canonical(document))
    with pytest.raises(ValueError, match="differs"):
        verify_judgments(output)
    (output / "stability.json").write_bytes(original)
    (output / "inputs/0001.json").write_bytes(paths[0].read_bytes() + b" ")
    with pytest.raises(ValueError, match="differs"):
        verify_judgments(output)


def test_verifier_rejects_extra_inputs_and_symlinked_input_directory(tmp_path):
    output = tmp_path / "review"
    import_judgments(write_inputs(tmp_path, examples()), output)
    (output / "inputs/extra.json").write_text("{}")
    with pytest.raises(ValueError, match="inventory"):
        verify_judgments(output)
    (output / "inputs/extra.json").unlink()
    (output / "inputs").rename(tmp_path / "moved")
    (output / "inputs").symlink_to(tmp_path / "moved", target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        verify_judgments(output)


def test_untrusted_text_is_escaped_in_html(tmp_path):
    data = examples()
    for run in data:
        run["dataset"]["cases"][0]["goal"] = "<script>window.pwned=1</script>"
    output = tmp_path / "review"
    import_judgments(write_inputs(tmp_path, data), output)
    page = (output / "index.html").read_text()
    assert "<script>window.pwned" not in page
    assert "&lt;script&gt;window.pwned" in page
    assert 'aria-live="polite"' in page


@pytest.mark.parametrize("mode,exit_code", [("incomplete", 2), ("flip", 1), ("all-reject", 0)])
def test_cli_consistency_gate_is_separate_from_task_acceptance(tmp_path, mode, exit_code, capsys):
    data = examples()
    for run in data:
        if mode != "incomplete":
            run["dataset"]["cases"] = run["dataset"]["cases"][:4]
            run["cases"] = run["cases"][:4]
        if mode == "all-reject":
            for case in run["cases"]:
                case["evaluation_response"]["evaluationResults"][0]["value"] = 0
    paths = write_inputs(tmp_path, data)
    args = ["trace-stability", *map(str, paths), "--output", str(tmp_path / "report")]
    assert main([*args, "--require-consistent-gates"]) == exit_code
    assert main(["trace-stability-verify", str(tmp_path / "report")]) == 0
    if mode == "all-reject":
        report = json.loads((tmp_path / "report/stability.json").read_text())
        assert report["summary"]["all_rejected_targets"] == 4
    assert main(["trace-stability", *map(str, paths), "--output", str(tmp_path / "normal")]) == 0

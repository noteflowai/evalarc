"""eval-health --reference, review-inputs --prompt, and regex/fuzzy grader checks."""

import copy
import json
import sys
from pathlib import Path

import pytest

from evalarc import evidence
from evalarc.cli import main
from evalarc.eval_health import health
from evalarc.eval_project import load_cases, required_terms, unstated_requirements
from evalarc.results_diff import load_results
from tests.test_eval_project import base_case, write_cases

ROOT = Path(__file__).resolve().parents[1]
INSPECT = ROOT / "examples/results-diff/inspect"


def reference_file(path, failing=("cancel-pending",)):
    """A reference run: the expected answer on every sample, failing the given cases."""
    document = json.loads((INSPECT / "current.json").read_text())
    for sample in document["samples"]:
        target = sample["target"] if isinstance(sample["target"], str) else sample["target"][0]
        sample["output"]["completion"] = target
        value = "I" if sample["id"] in failing and sample["epoch"] == 2 else "C"
        for score in sample["scores"].values():
            score["value"] = value
    path.write_text(json.dumps(document))
    return load_results(path)


def runs():
    return [load_results(INSPECT / f"{n}.json") for n in ("baseline", "current")]


# --- --reference ------------------------------------------------------------------


def test_reference_fails_and_triage(tmp_path):
    reference = reference_file(tmp_path / "ref.json")
    plain = health(runs())
    assert "reference" not in plain
    assert "task_or_grader_broken" not in {row["category"] for row in plain["triage"]}
    result = health(runs(), reference_run=reference)
    finding = next(f for f in result["findings"] if f["id"] == "reference_fails")
    assert {item["check"] for item in finding["items"]} == {"match", "includes"}
    assert {item["case_id"] for item in finding["items"]} == {"cancel-pending"}
    triage = {row["case_id"]: row["category"] for row in result["triage"]}
    assert triage["cancel-pending"] == "task_or_grader_broken"
    assert triage["refund-duplicate"] == "regressed"
    assert result["reference"]["missing_cases"] == []


def test_a_clean_reference_raises_nothing(tmp_path):
    reference = reference_file(tmp_path / "ref.json", failing=())
    result = health(runs(), reference_run=reference)
    ids = {f["id"] for f in result["findings"]}
    assert "reference_fails" not in ids and "reference_incomplete" not in ids
    assert result["reference"]["failing"] == []


def test_reference_missing_cases_and_mismatches(tmp_path):
    document = json.loads((INSPECT / "current.json").read_text())
    document["samples"] = [s for s in document["samples"] if s["id"] != "status-open"]
    (tmp_path / "partial.json").write_text(json.dumps(document))
    result = health(runs(), reference_run=load_results(tmp_path / "partial.json"))
    assert result["reference"]["missing_cases"] == ["status-open"]
    assert "reference_incomplete" in {f["id"] for f in result["findings"]}
    junit = load_results(ROOT / "examples/results-diff/junit/current.xml")
    with pytest.raises(ValueError, match="the reference uses junit"):
        health(runs(), reference_run=junit)
    other = copy.deepcopy(document)
    other["eval"]["task"] = "different"
    (tmp_path / "other.json").write_text(json.dumps(other))
    with pytest.raises(ValueError, match="is for task 'different'"):
        health(runs(), reference_run=load_results(tmp_path / "other.json"))


def test_reference_cli_copies_records_and_verifies(tmp_path, capsys):
    reference_file(tmp_path / "ref.json")
    out = tmp_path / "h"
    args = ["eval-health", str(INSPECT / "baseline.json"), str(INSPECT / "current.json")]
    assert main([*args, "--reference", str(tmp_path / "ref.json"), "--output", str(out)]) == 0
    assert json.loads((out / "params.json").read_text())["reference"] == "reference.json"
    assert (out / "reference.json").read_bytes() == (tmp_path / "ref.json").read_bytes()
    assert "task_or_grader_broken" in (out / "summary.md").read_text()
    capsys.readouterr()
    assert main(["verify", str(out), "--json"]) == 0
    tampered = json.loads((out / "reference.json").read_text())
    tampered["samples"][0]["scores"]["match"]["value"] = "I"
    (out / "reference.json").write_text(json.dumps(tampered))
    assert main(["verify", str(out), "--json"]) == 2
    plain = tmp_path / "p"
    assert main([*args, "--output", str(plain)]) == 0
    assert "reference" not in json.loads((plain / "params.json").read_text())


def test_reference_cannot_be_one_of_the_results(capsys):
    current = str(INSPECT / "current.json")
    assert main(["eval-health", current, "--reference", current]) == 2
    assert "separate run" in capsys.readouterr().err


def test_compute_health_without_reference_matches(tmp_path):
    params = {
        "saturation": 0.95,
        "min_effect": None,
        "ordered": False,
        "plan_attempts": None,
        "plan_configs": None,
        "trial_metrics": True,
    }
    assert "reference" not in evidence.compute_health(runs(), params, None)


# --- --prompt ---------------------------------------------------------------------


def test_required_terms():
    assert required_terms(base_case(labels=["billing", "general"])) == ["billing", "general"]
    assert required_terms({"check": "json_keys", "expected": ["queue", "reason"]}) == [
        "queue",
        "reason",
    ]
    schema = {
        "type": "object",
        "required": ["queue"],
        "properties": {
            "priority": {"enum": ["p1", "p2", 3]},
            "tags": {"items": {"required": ["k"]}},
        },
    }
    assert required_terms({"check": "json_schema", "expected": schema}) == [
        "queue",
        "p1",
        "p2",
        "k",
    ]
    for check in ("exact", "contains", "regex", "fuzzy", "command"):
        assert required_terms({"check": check, "expected": "x"}) == []


def test_unstated_requirements_use_prompt_and_input():
    cases = [
        base_case(id="a", labels=["billing", "general"], input="refund please"),
        base_case(
            id="b", labels=["billing", "oncall"], expected="billing", input="mentions oncall"
        ),
        {
            "id": "c",
            "check": "json_keys",
            "expected": ["order_id"],
            "input": "x",
            "source": "manual",
        },
    ]
    items = unstated_requirements(cases, "Route to billing or general.")
    assert [(i["case_id"], i["missing"]) for i in items] == [("c", ["order_id"])]
    # Whole words only: "generalized" does not state the label "general".
    assert unstated_requirements([cases[0]], "billing, generalized")[0]["missing"] == ["general"]


def test_review_inputs_prompt_cli(tmp_path, capsys):
    project = tmp_path / "p"
    assert main(["eval-init", str(project)]) == 0
    capsys.readouterr()
    cases = project / "cases.jsonl"
    prompt = project / "prompt.md"
    out = tmp_path / "r"
    assert main(["review-inputs", str(cases), "--prompt", str(prompt), "--output", str(out)]) == 0
    report = json.loads((out / "review.json").read_text())
    assert report["prompt_files"][0]["name"] == "prompt.md"
    assert "unstated_requirement" not in {f["id"] for f in report["findings"]}
    prompt.write_text("Route the ticket to one queue: billing or general.\n")
    capsys.readouterr()
    assert main(["review-inputs", str(cases), "--prompt", str(prompt), "--require-clean"]) == 1
    assert "unstated_requirement" in capsys.readouterr().out
    plain = tmp_path / "plain"
    assert main(["review-inputs", str(cases), "--output", str(plain)]) == 0
    assert "prompt_files" not in json.loads((plain / "review.json").read_text())


# --- regex and fuzzy ----------------------------------------------------------------


@pytest.fixture
def grader(tmp_path):
    project = tmp_path / "p"
    assert main(["eval-init", str(project)]) == 0
    sys.path.insert(0, str(project))
    try:
        import grader as module  # noqa: PLC0415
    finally:
        sys.path.remove(str(project))
    yield module
    del sys.modules["grader"]


def test_regex_and_fuzzy_grading(grader):
    regex = {"check": "regex", "expected": r"refund:\d+:\d+"}
    assert grader.grade(regex, " refund:1001:12 ")[0]
    assert not grader.grade(regex, "refund:1001:12 approved")[0]
    assert grader.grade({"check": "regex", "expected": r".*refund:\d+.*"}, "ok refund:7 done")[0]
    fuzzy = {"check": "fuzzy", "expected": "The refund was approved."}
    assert grader.grade(fuzzy, "the refund  was approved")[0]
    assert not grader.grade(fuzzy, "The refund was rejected.")[0]
    assert grader.grade({**fuzzy, "min_ratio": 0.5}, "The refund was rejected.")[0]


@pytest.mark.parametrize(
    "case,message",
    [
        (base_case(check="regex", expected="(", labels=None), "regex expected does not compile"),
        (base_case(check="regex", expected="a" * 1001, labels=None), "longer than 1000"),
        (base_case(check="fuzzy", expected="x", labels=None, min_ratio=0), "min_ratio must be"),
        (base_case(check="fuzzy", expected="x", labels=None, min_ratio=True), "min_ratio must be"),
        (base_case(min_ratio=0.8), "min_ratio applies to fuzzy checks"),
    ],
)
def test_regex_and_fuzzy_validation(tmp_path, capsys, case, message):
    project = tmp_path / "p"
    assert main(["eval-init", str(project)]) == 0
    case = {key: value for key, value in case.items() if value is not None}
    write_cases(project, [case])
    capsys.readouterr()
    assert main(["review-inputs", str(project / "cases.jsonl")]) == 2
    assert message in capsys.readouterr().err


def test_valid_regex_and_fuzzy_cases_load(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(
        json.dumps(
            {"id": "r", "input": "q", "check": "regex", "expected": "a+", "source": "manual"}
        )
        + "\n"
        + json.dumps(
            {
                "id": "f",
                "input": "q",
                "check": "fuzzy",
                "expected": "abc",
                "min_ratio": 0.8,
                "source": "manual",
            }
        )
        + "\n"
    )
    assert [case["check"] for case in load_cases(path)] == ["regex", "fuzzy"]


def test_unassessed_reference_attempts_are_not_broken_tasks(tmp_path):
    document = json.loads((INSPECT / "current.json").read_text())
    for sample in document["samples"]:
        for score in sample["scores"].values():
            score["value"] = "C"
        if sample["id"] == "cancel-pending" and sample["epoch"] == 2:
            sample.pop("scores")
            sample["error"] = {"message": "sandbox crashed"}
    (tmp_path / "ref.json").write_text(json.dumps(document))
    result = health(runs(), reference_run=load_results(tmp_path / "ref.json"))
    ids = {f["id"] for f in result["findings"]}
    assert "reference_fails" not in ids and "reference_unassessed" in ids
    triage = {row["case_id"]: row["category"] for row in result["triage"]}
    assert triage["cancel-pending"] != "task_or_grader_broken"


def test_a_reference_with_no_shared_cases_is_rejected(tmp_path):
    document = json.loads((INSPECT / "current.json").read_text())
    for sample in document["samples"]:
        sample["id"] = "other-" + str(sample["id"])
    (tmp_path / "ref.json").write_text(json.dumps(document))
    with pytest.raises(ValueError, match="shares no case IDs"):
        health(runs(), reference_run=load_results(tmp_path / "ref.json"))


def test_cjk_terms_inside_sentences_count_as_stated():
    case = {
        "id": "z",
        "input": "请把工单分类为退款或换货",
        "check": "label",
        "labels": ["退款", "换货"],
        "expected": "退款",
        "source": "manual",
    }
    assert unstated_requirements([case], "") == []
    missing = {**case, "input": "请分类"}
    assert unstated_requirements([missing], "")[0]["missing"] == ["退款", "换货"]
    japanese = {**case, "input": "返金してください", "labels": ["返金", "交換"], "expected": "返金"}
    assert unstated_requirements([japanese], "")[0]["missing"] == ["交換"]


def test_regex_rejects_rather_than_truncates_long_outputs(grader):
    long = "1" * 100_001
    passed, why = grader.grade({"check": "regex", "expected": r"\d+"}, long)
    assert not passed and "longer than" in why

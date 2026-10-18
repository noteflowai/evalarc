"""SYNTHETIC EA-02 regression corpus: how the results-diff gate treats missing evidence.

Every input here is synthetic. Inspect and promptfoo inputs are small edits of the
bundled example results, and the JUnit inputs are hand-written XML. Each case pins
whether the gate passes (exit 0), fails (exit 1) or rejects the input (exit 2) and the
explanation it gives. The corpus says nothing about real exports, provider quality or
false-alarm rates.
"""

import copy
import json
from pathlib import Path

import pytest

from evalarc.cli import main
from evalarc.evidence import diff_passed
from evalarc.results_diff import BLOCKING, diff, load_results, render_markdown

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/results-diff"
PASSED = "### EvalArc: No check lost passes"
EXIT_CODES = {"pass": 0, "fail": 1, "error": 2}
CATEGORIES = (
    "control",
    "added_check",
    "removed_check",
    "unequal_coverage",
    "skip_only",
    "malformed",
    "duplicate_ids",
    "non_comparable",
    "incomplete",
)


def lost(count):
    return f"### EvalArc: {count} check(s) lost passes or coverage"


def example(name):
    return json.loads((EXAMPLES / name).read_text())


def sample(case_id, epoch, **scores):
    item = copy.deepcopy(example("inspect/baseline.json")["samples"][0])
    item["id"] = case_id
    item["epoch"] = epoch
    item.pop("error", None)
    item["scores"] = {name: {"value": value} for name, value in scores.items()}
    return item


def inspect_log(samples, status="success", task=None):
    document = example("inspect/baseline.json")
    document["samples"] = samples
    document["status"] = status
    epochs = [
        item["epoch"]
        for item in samples
        if isinstance(item, dict) and isinstance(item.get("epoch"), int)
    ]
    spec = document["eval"]
    spec["config"] = {**(spec.get("config") or {}), "epochs": max(epochs, default=1)}
    if task is not None:
        spec["task"] = task
    return document


def passing(*names):
    return inspect_log([sample("refund", 1, **{name: "C" for name in names})])


def junit_xml(skip_refund):
    skipped = '<skipped message="synthetic skip"/>' if skip_refund else ""
    refund = f'<testcase classname="corpus" name="test_refund">{skipped}</testcase>'
    status = '<testcase classname="corpus" name="test_status"/>'
    suite = f'<testsuite name="corpus">{refund}{status}</testsuite>'
    return f'<?xml version="1.0"?>\n{suite}\n'


def write(path, document):
    path.write_text(document if isinstance(document, str) else json.dumps(document))
    return path


def save(tmp_path, before, after, fmt="inspect"):
    suffix = ".xml" if fmt == "junit" else ".json"
    baseline = write(tmp_path / f"baseline{suffix}", before)
    current = write(tmp_path / f"current{suffix}", after)
    return baseline, fmt, current, fmt


def control(tmp_path):
    return save(tmp_path, passing("match"), passing("match"))


def added_check(tmp_path):
    return save(tmp_path, passing("match"), passing("match", "extra"))


def removed_check(tmp_path):
    return save(tmp_path, passing("match", "extra"), passing("match"))


def fewer_epochs(tmp_path):
    before = inspect_log([sample("refund", epoch, match="C") for epoch in (1, 2, 3)])
    return save(tmp_path, before, passing("match"))


def skip_only(tmp_path):
    return save(tmp_path, junit_xml(False), junit_xml(True), "junit")


def not_an_object(tmp_path):
    after = inspect_log([sample("refund", 1, match="C"), ["synthetic", "array"]])
    return save(tmp_path, passing("match"), after)


def missing_id(tmp_path):
    item = sample("refund", 1, match="C")
    del item["id"]
    return save(tmp_path, passing("match"), inspect_log([item]))


def list_prompt_idx(tmp_path):
    after = example("promptfoo/current.json")
    after["results"]["results"][0]["promptIdx"] = [0]
    return save(tmp_path, example("promptfoo/baseline.json"), after, "promptfoo")


def duplicate_sample(tmp_path):
    copies = [sample("refund", 1, match="C"), sample("refund", 1, match="C")]
    return save(tmp_path, passing("match"), inspect_log(copies))


def int_and_str_ids(tmp_path):
    ids = [sample(7, 1, match="C"), sample("7", 1, match="C")]
    return save(tmp_path, passing("match"), inspect_log(ids))


def duplicate_without_epoch(tmp_path):
    # Baseline records two epochs; the current run repeats one sample with a null
    # epoch, which used to load as two attempts and hide the lost coverage.
    before = inspect_log([sample("refund", epoch, match="C") for epoch in (1, 2)])
    copies = [sample("refund", None, match="C"), sample("refund", None, match="C")]
    return save(tmp_path, before, inspect_log(copies))


def duplicate_promptfoo_row(tmp_path):
    after = example("promptfoo/current.json")
    rows = after["results"]["results"]
    rows.append(copy.deepcopy(rows[0]))
    return save(tmp_path, example("promptfoo/current.json"), after, "promptfoo")


def promptfoo_repeats(tmp_path):
    repeated = example("promptfoo/current.json")
    rows = repeated["results"]["results"]
    extra = copy.deepcopy(rows)
    for index, row in enumerate(extra):
        row["testIdx"] = len(rows) + index
    rows.extend(extra)
    return save(tmp_path, example("promptfoo/current.json"), repeated, "promptfoo")


def other_task(tmp_path):
    after = inspect_log([sample("refund", 1, match="C")], task="synthetic-other")
    return save(tmp_path, passing("match"), after)


def other_format(tmp_path):
    baseline = write(tmp_path / "baseline.json", passing("match"))
    current = write(tmp_path / "current.xml", junit_xml(False))
    return baseline, "inspect", current, "junit"


def baseline_error(tmp_path):
    before = inspect_log([sample("refund", 1, match="C")], status="error")
    return save(tmp_path, before, passing("match"))


def current_error(tmp_path):
    after = inspect_log([sample("refund", 1, match="C")], status="error")
    return save(tmp_path, passing("match"), after)


def case(name, category, build, outcome, missing_evidence, **expected):
    return {
        "id": f"synthetic-{name}",
        "category": category,
        "build": build,
        "outcome": outcome,
        "missing_evidence": missing_evidence,
        **expected,
    }


CASES = [
    case(
        "control-identical",
        "control",
        control,
        "pass",
        False,
        changes=[],
        heading=PASSED,
        explains="**1** unchanged",
    ),
    case(
        "added-scorer",
        "added_check",
        added_check,
        "pass",
        False,
        changes=[("added", "refund", "extra")],
        heading=PASSED,
        explains="**1** added",
    ),
    case(
        "removed-passing-scorer",
        "removed_check",
        removed_check,
        "fail",
        True,
        changes=[("removed", "refund", "extra")],
        heading=lost(1),
        explains="**1** removed",
    ),
    case(
        "fewer-epochs-same-rate",
        "unequal_coverage",
        fewer_epochs,
        "fail",
        True,
        changes=[("less_covered", "refund", "match")],
        heading=lost(1),
        explains="**1** less covered",
    ),
    case(
        "junit-skip-only",
        "skip_only",
        skip_only,
        "fail",
        True,
        changes=[("unassessed", "corpus::test_refund", "passed")],
        heading=lost(1),
        explains="**1** unassessed",
    ),
    case(
        "inspect-sample-not-object",
        "malformed",
        not_an_object,
        "error",
        True,
        message="sample at position 1 is not an object (got array)",
    ),
    case(
        "inspect-sample-missing-id",
        "malformed",
        missing_id,
        "error",
        True,
        message="sample at position 0 has an invalid id missing (missing)",
    ),
    case(
        "promptfoo-list-prompt-idx",
        "malformed",
        list_prompt_idx,
        "error",
        True,
        message="invalid promptIdx [0]",
    ),
    case(
        "inspect-duplicate-sample-epoch",
        "duplicate_ids",
        duplicate_sample,
        "error",
        True,
        message="duplicate sample 'refund' epoch 1",
    ),
    case(
        "inspect-ids-7-and-string-7",
        "duplicate_ids",
        int_and_str_ids,
        "error",
        True,
        message="duplicate sample '7' epoch 1",
    ),
    case(
        "promptfoo-duplicate-row",
        "duplicate_ids",
        duplicate_promptfoo_row,
        "error",
        True,
        message="promptfoo output has duplicate result testIdx",
    ),
    case(
        "promptfoo-repeats-new-test-idx",
        "duplicate_ids",
        promptfoo_repeats,
        "pass",
        False,
        changes=[],
        heading=PASSED,
        explains="unchanged",
    ),
    case(
        "inspect-different-task",
        "non_comparable",
        other_task,
        "error",
        True,
        message="inputs are not comparable: task",
    ),
    case(
        "inspect-vs-junit",
        "non_comparable",
        other_format,
        "error",
        True,
        message="inputs use different formats: inspect and junit",
    ),
    case(
        "inspect-baseline-status-error",
        "incomplete",
        baseline_error,
        "fail",
        True,
        changes=[],
        heading="### EvalArc: the baseline run is incomplete",
        explains="The baseline run did not finish (status \u0060error\u0060)",
        flag="baseline_incomplete",
    ),
    case(
        "inspect-current-status-error",
        "incomplete",
        current_error,
        "fail",
        True,
        changes=[],
        heading="### EvalArc: the current run is incomplete",
        explains="The current run did not finish (status \u0060error\u0060); the gate fails.",
        flag="current_incomplete",
    ),
    case(
        "inspect-duplicate-sample-without-epoch",
        "duplicate_ids",
        duplicate_without_epoch,
        "error",
        True,
        message="duplicate sample 'refund' without a valid epoch (got None (null))",
    ),
]
BY_ID = {entry["id"]: entry for entry in CASES}


def kinds(result):
    rows = result["changes"]
    return sorted((row["kind"], row["case_id"], row["check"]) for row in rows)


def run(entry, tmp_path):
    baseline, baseline_fmt, current, current_fmt = entry["build"](tmp_path)
    try:
        before = load_results(baseline, baseline_fmt)
        result = diff(before, load_results(current, current_fmt))
    except ValueError as error:
        return "error", str(error), (baseline, current)
    outcome = "pass" if diff_passed(result) else "fail"
    return outcome, result, (baseline, current)


@pytest.mark.parametrize("entry", CASES, ids=[entry["id"] for entry in CASES])
def test_corpus_case_outcome(entry, tmp_path, capsys):
    outcome, detail, paths = run(entry, tmp_path)
    assert outcome == entry["outcome"], detail
    if outcome == "error":
        assert entry["message"] in detail
    else:
        assert kinds(detail) == entry["changes"]
        assert detail["gate_passed"] is (outcome == "pass")
        markdown = render_markdown(detail)
        assert markdown.splitlines()[0] == entry["heading"]
        assert entry["explains"] in markdown
        if "flag" in entry:
            assert detail[entry["flag"]] is True
    code = main(["diff", *map(str, paths)])
    err = capsys.readouterr().err
    assert code == EXIT_CODES[entry["outcome"]]
    if outcome == "error":
        assert entry["message"] in err


def test_fewer_epochs_with_an_unchanged_pass_rate_fail(tmp_path):
    outcome, result, _ = run(BY_ID["synthetic-fewer-epochs-same-rate"], tmp_path)
    (row,) = result["changes"]
    assert row["kind"] == "less_covered" and row["kind"] in BLOCKING
    assert row["baseline"] == {"passed": 3, "assessed": 3, "attempts": 3}
    assert row["current"] == {"passed": 1, "assessed": 1, "attempts": 1}
    assert result["counts"]["less_covered"] == 1
    assert outcome == "fail" and result["blocking_changes"] == 1


def test_a_skip_as_the_only_difference_fails(tmp_path):
    outcome, result, _ = run(BY_ID["synthetic-junit-skip-only"], tmp_path)
    (row,) = result["changes"]
    assert row["kind"] == "unassessed"
    assert row["baseline"] == {"passed": 1, "assessed": 1, "attempts": 1}
    assert row["current"] == {"passed": 0, "assessed": 0, "attempts": 1}
    assert row["current_detail"] == [{"passed": None, "evidence": "skipped: synthetic skip"}]
    assert result["counts"]["unchanged"] == 1
    assert outcome == "fail" and result["blocking_changes"] == 1


def test_promptfoo_repeats_with_new_test_indexes_are_attempts(tmp_path):
    single, _, repeated, _ = promptfoo_repeats(tmp_path)
    before = load_results(single, "promptfoo")["cases"]
    after = load_results(repeated, "promptfoo")["cases"]
    assert sorted(after) == sorted(before)
    for case_id, checks in after.items():
        assert sorted(checks) == sorted(before[case_id])
        for check, attempts in checks.items():
            assert len(attempts) == 2 * len(before[case_id][check])


def test_no_missing_evidence_case_passes_the_gate(tmp_path):
    assert {entry["category"] for entry in CASES} == set(CATEGORIES)
    assert all(entry["id"].startswith("synthetic-") for entry in CASES)
    missing = {entry["category"] for entry in CASES if entry["missing_evidence"]}
    assert missing == set(CATEGORIES[2:])
    for index, entry in enumerate(CASES):
        folder = tmp_path / str(index)
        folder.mkdir()
        outcome, detail, _ = run(entry, folder)
        if entry["missing_evidence"]:
            assert outcome in ("fail", "error"), entry["id"]
        else:
            assert outcome == "pass", entry["id"]
            blocking = [row for row in detail["changes"] if row["kind"] in BLOCKING]
            assert blocking == [], entry["id"]


def test_synthetic_samples_without_epoch_load_once_and_reject_copies(tmp_path):
    # Distinct ids without an epoch are still ordinary single attempts.
    distinct = [sample("refund", 1, match="C"), sample("status", 1, match="C")]
    for item in distinct:
        del item["epoch"]
    path = write(tmp_path / "distinct.json", inspect_log(distinct))
    loaded = load_results(path, "inspect")
    assert sorted(loaded["cases"]) == ["refund", "status"]
    assert len(loaded["cases"]["refund"]["match"]) == 1
    # A null epoch repeated for one id is rejected and the type is named.
    copies = [sample("refund", None, match="C"), sample("refund", None, match="C")]
    path = write(tmp_path / "null.json", inspect_log(copies))
    with pytest.raises(ValueError, match="without a valid epoch \\(got None \\(null\\)\\)"):
        load_results(path, "inspect")
    # Integer epochs keep their existing behavior: repeats across epochs load.
    repeats = [sample("refund", epoch, match="C") for epoch in (1, 2)]
    path = write(tmp_path / "repeats.json", inspect_log(repeats))
    assert len(load_results(path, "inspect")["cases"]["refund"]["match"]) == 2


MISSING = object()


@pytest.mark.parametrize(
    "first,second,shown",
    [
        (True, False, "got True (boolean)"),
        ("1", "2", "got '1' (string)"),
        (MISSING, "x", "got missing"),
        (1, MISSING, "got missing"),
        (MISSING, 1, "got missing"),
    ],
    ids=[
        "synthetic-boolean-epochs",
        "synthetic-string-epochs",
        "synthetic-missing-then-string-epoch",
        "synthetic-integer-then-missing-epoch",
        "synthetic-missing-then-integer-epoch",
    ],
)
def test_synthetic_repeated_id_with_any_non_integer_epoch_is_rejected(
    tmp_path, capsys, first, second, shown
):
    # Two copies of one id where at least one lacks an integer epoch cannot be told
    # apart from an extra attempt, so the log is unusable rather than better covered.
    copies = []
    for epoch in (first, second):
        item = sample("refund", 1, match="C")
        if epoch is MISSING:
            del item["epoch"]
        else:
            item["epoch"] = epoch
        copies.append(item)
    path = write(tmp_path / "copies.json", inspect_log(copies))
    expected = f"duplicate sample 'refund' without a valid epoch ({shown})"
    with pytest.raises(ValueError) as error:
        load_results(path, "inspect")
    assert expected in str(error.value)
    baseline = write(tmp_path / "baseline.json", passing("match"))
    assert main(["diff", str(baseline), str(path)]) == 2
    assert expected in capsys.readouterr().err


def test_synthetic_legacy_copies_that_all_omit_epoch_still_load(tmp_path):
    # Older exports omit the epoch key on every copy of an id; they keep loading each
    # copy as an attempt, as before this corpus existed.
    copies = [sample("refund", 1, match="C"), sample("refund", 1, match="I")]
    for item in copies:
        del item["epoch"]
    path = write(tmp_path / "legacy.json", inspect_log(copies))
    loaded = load_results(path, "inspect")
    assert sorted(loaded["cases"]) == ["refund"]
    assert len(loaded["cases"]["refund"]["match"]) == 2

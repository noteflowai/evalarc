"""Case-level trials, pass@k / pass^k and capability/regression suite roles."""

import itertools
import json
from pathlib import Path

import pytest

from evalarc import evidence, provenance, trials
from evalarc.cli import main
from evalarc.eval_health import health
from evalarc.results_diff import load_results

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples/results-diff"


def inspect_log(path, outcomes, task="demo"):
    """outcomes: case id -> list of trials; a trial is a dict check -> True/False,
    or None for a sample error with no scores."""
    samples = []
    for case_id, attempts in outcomes.items():
        for epoch, checks in enumerate(attempts, start=1):
            sample = {"id": case_id, "epoch": epoch, "input": "q", "target": "a"}
            if checks is None:
                sample["error"] = {"message": "timeout"}
            else:
                sample["scores"] = {
                    name: {"value": "C" if passed else "I"} for name, passed in checks.items()
                }
            samples.append(sample)
    path.write_text(
        json.dumps({"status": "success", "eval": {"task": task, "config": {}}, "samples": samples})
    )
    return load_results(path)


def ids(result):
    return {finding["id"]: finding["severity"] for finding in result["findings"]}


def manifest(tmp_path, entries):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"schema_version": provenance.SCHEMA, "cases": entries}))
    return provenance.load(path)


# --- estimators -----------------------------------------------------------------------


def brute(n, c, k):
    """Enumerate every k-subset of n trials, c of which succeed."""
    outcomes = [True] * c + [False] * (n - c)
    subsets = list(itertools.combinations(outcomes, k))
    at = sum(any(s) for s in subsets) / len(subsets)
    hat = sum(all(s) for s in subsets) / len(subsets)
    return at, hat


@pytest.mark.parametrize("n", range(1, 8))
def test_estimators_match_exhaustive_enumeration(n):
    for c in range(n + 1):
        for k in range(1, n + 1):
            at, hat = brute(n, c, k)
            assert trials.pass_at_k(n, c, k) == pytest.approx(at)
            assert trials.pass_hat_k(n, c, k) == pytest.approx(hat)


def test_estimators_agree_at_k1_and_diverge_with_k():
    assert trials.pass_at_k(10, 6, 1) == trials.pass_hat_k(10, 6, 1) == pytest.approx(0.6)
    assert trials.pass_at_k(10, 6, 5) > 0.97
    assert trials.pass_hat_k(10, 6, 5) < 0.03


@pytest.mark.parametrize("args", [(0, 0, 1), (3, 1, 0), (3, 1, 4), (3, 4, 1), (3, -1, 1)])
def test_estimators_reject_impossible_arguments(args):
    with pytest.raises(ValueError):
        trials.pass_at_k(*args)
    with pytest.raises(ValueError):
        trials.pass_hat_k(*args)


# --- trial outcomes -------------------------------------------------------------------


def test_a_trial_succeeds_only_when_every_check_passed(tmp_path):
    run = inspect_log(
        tmp_path / "r.json",
        {
            "all": [{"a": True, "b": True}, {"a": True, "b": True}],
            "one-fails": [{"a": True, "b": False}, {"a": True, "b": True}],
            "error": [None, {"a": True, "b": True}],
        },
    )
    cases = trials.case_trials(run)
    assert cases == {
        "all": {"trials": 2, "assessed": 2, "successes": 2},
        "one-fails": {"trials": 2, "assessed": 2, "successes": 1},
        # The sample error has no outcome: excluded, never counted as a pass.
        "error": {"trials": 2, "assessed": 1, "successes": 1},
    }
    summary = trials.summarize(run)
    assert summary["unassessed_trials"] == 1
    assert summary["min_assessed_trials"] == 1
    k1, k2 = summary["by_k"]
    assert k1 == {"k": 1, "cases": 3, "pass_at_k": 0.833333, "pass_hat_k": 0.833333}
    # Only cases with two assessed trials enter k = 2.
    assert k2 == {"k": 2, "cases": 2, "pass_at_k": 1.0, "pass_hat_k": 0.5}


def test_a_failed_check_makes_a_trial_failed_even_beside_an_unassessed_one():
    both = {"a", "b"}
    assert trials._trial({"a": True, "b": None, "c": False}, both) is False
    assert trials._trial({"a": True, "b": None}, both) is None
    assert trials._trial({}, set()) is None
    assert trials._trial({"a": True, "b": True}, both) is True
    # A check recorded on another attempt but missing here is missing evidence.
    assert trials._trial({"a": True}, both) is None
    assert trials._trial({"a": False}, both) is False
    assert trials._trial({"a": True, "b": True}, both, errored=True) is None


def test_errored_samples_and_missing_scorers_are_not_successes(tmp_path):
    path = tmp_path / "r.json"
    samples = [
        # Errored on both epochs although the scorer recorded a pass.
        {"id": "r", "epoch": e, "error": {"message": "x"}, "scores": {"a": {"value": "C"}}}
        for e in (1, 2)
    ] + [
        {"id": "q", "epoch": 1, "scores": {"a": {"value": "C"}, "b": {"value": "C"}}},
        {"id": "q", "epoch": 2, "scores": {"a": {"value": "C"}}},
    ]
    path.write_text(
        json.dumps({"status": "success", "eval": {"task": "t", "config": {}}, "samples": samples})
    )
    run = load_results(path)
    assert trials.case_trials(run) == {
        "q": {"trials": 2, "assessed": 1, "successes": 1},
        "r": {"trials": 2, "assessed": 0, "successes": 0},
    }
    loaded = manifest(tmp_path, [{"match": "*", "source": "production", "suite": "regression"}])
    result = health([run], cases_manifest=loaded)
    finding = next(f for f in result["findings"] if f["id"] == "regression_case_failing")
    assert [item["case_id"] for item in finding["items"]] == ["q", "r"]


def test_colliding_check_names_keep_the_failure(tmp_path):
    path = tmp_path / "r.json"
    sample = {"id": "c", "epoch": 1, "scores": {"s/x": {"value": "C"}, "s": {"value": {"x": 0}}}}
    path.write_text(
        json.dumps({"status": "success", "eval": {"task": "t", "config": {}}, "samples": [sample]})
    )
    run = load_results(path)
    assert run["samples"]["c"][0]["verdicts"] == {"s/x": False}
    assert trials.case_trials(run)["c"] == {"trials": 1, "assessed": 1, "successes": 0}


def test_k_is_capped_and_cases_without_trials_are_listed(tmp_path):
    run = inspect_log(
        tmp_path / "r.json",
        {"many": [{"a": True}] * 12, "broken": [None, None]},
    )
    summary = trials.summarize(run)
    assert summary["by_k"][-1]["k"] == trials.MAX_K
    assert summary["cases_without_assessed_trials"] == ["broken"]
    assert all(row["cases"] == 1 for row in summary["by_k"])


def test_recorded_inspect_example_values():
    run = load_results(EXAMPLES / "inspect/current.json")
    by_k = {row["k"]: row for row in trials.summarize(run)["by_k"]}
    # 6 cases pass both epochs, cancel-pending passes one, refund-duplicate none.
    assert by_k[1]["pass_at_k"] == pytest.approx(6.5 / 8)
    assert by_k[2] == {"k": 2, "cases": 8, "pass_at_k": 0.875, "pass_hat_k": 0.75}


def test_junit_repeats_align_by_position(tmp_path):
    path = tmp_path / "r.xml"
    path.write_text(
        "<testsuite name='s'>"
        "<testcase classname='c' name='t'/>"
        "<testcase classname='c' name='t'><failure message='no'/></testcase>"
        "<testcase classname='c' name='u'><skipped/></testcase>"
        "</testsuite>"
    )
    cases = trials.case_trials(load_results(path))
    assert cases == {
        "c::t": {"trials": 2, "assessed": 2, "successes": 1},
        "c::u": {"trials": 1, "assessed": 0, "successes": 0},
    }


def test_promptfoo_repeats_are_trials_of_one_case():
    run = load_results(EXAMPLES / "promptfoo/current.json")
    summary = trials.summarize(run)
    assert summary["cases"] == len(run["cases"])
    assert summary["trials"] == sum(len(metas) for metas in run["samples"].values())


# --- suite roles ----------------------------------------------------------------------


def test_manifest_without_suites_is_unchanged(tmp_path):
    loaded = manifest(tmp_path, [{"match": "*", "source": "production"}])
    assert "suite" not in loaded["rules"][0]
    assert "suites" not in provenance.review(loaded, {"a"})


def test_manifest_rejects_an_unknown_suite(tmp_path):
    with pytest.raises(ValueError, match="suite must be one of capability, regression"):
        manifest(tmp_path, [{"match": "*", "source": "production", "suite": "smoke"}])


def test_regression_cases_must_succeed_on_every_trial(tmp_path):
    first = inspect_log(
        tmp_path / "a.json",
        {"keep": [{"a": True}] * 2, "gone": [{"a": True}], "flaky": [{"a": True}] * 2},
    )
    last = inspect_log(
        tmp_path / "b.json",
        {
            "keep": [{"a": True}] * 2,
            "flaky": [{"a": True}, {"a": False}],
            "erroring": [{"a": True}, None],
        },
    )
    loaded = manifest(
        tmp_path,
        [
            {"match": "keep", "source": "bug_report", "suite": "regression"},
            {"match": "gone", "source": "bug_report", "suite": "regression"},
            {"match": "flaky", "source": "bug_report", "suite": "regression"},
            {"match": "erroring", "source": "bug_report", "suite": "regression"},
        ],
    )
    result = health([first, last], cases_manifest=loaded)
    assert ids(result)["regression_case_failing"] == "warning"
    assert not result["healthy"]
    finding = next(f for f in result["findings"] if f["id"] == "regression_case_failing")
    details = {item["case_id"]: item["detail"] for item in finding["items"]}
    assert details == {
        "erroring": "1/1 assessed trial(s) succeeded, 1 unassessed",
        "flaky": "1/2 assessed trial(s) succeeded",
        "gone": "not recorded in the last file",
    }
    assert {item["file"] for item in finding["items"]} == {"b.json"}
    assert result["provenance"]["suites"]["keep"] == "regression"


def test_capability_cases_that_always_succeed_can_graduate(tmp_path):
    run = inspect_log(
        tmp_path / "r.json",
        {
            "solid": [{"a": True}] * 3,
            "once": [{"a": True}],
            "hard": [{"a": True}, {"a": False}],
            "partly-errored": [{"a": True}, {"a": True}, None],
        },
    )
    loaded = manifest(tmp_path, [{"match": "*", "source": "manual", "suite": "capability"}])
    result = health([run], cases_manifest=loaded)
    finding = next(f for f in result["findings"] if f["id"] == "graduation_candidates")
    assert finding["severity"] == "info"
    # One trial is not evidence of reliability; an errored trial is missing evidence.
    assert [item["case_id"] for item in finding["items"]] == ["solid"]
    assert "regression_case_failing" not in ids(result)


# --- report output and verification ---------------------------------------------------


def test_trials_key_follows_the_recorded_option(tmp_path):
    run = inspect_log(tmp_path / "r.json", {"c": [{"a": True}, {"a": False}]})
    assert "trials" in health([run])
    assert "trials" not in health([run], trial_metrics=False)
    params = {
        "saturation": 0.95,
        "min_effect": None,
        "ordered": False,
        "plan_attempts": None,
        "plan_configs": None,
    }
    # params.json written before trial metrics existed has no trial_metrics key.
    assert "trials" not in evidence.compute_health([run], params, None)
    assert "trials" in evidence.compute_health([run], {**params, "trial_metrics": True}, None)


def test_cli_report_shows_trials_and_verifies(tmp_path, capsys):
    out = tmp_path / "health"
    code = main(
        [
            "eval-health",
            str(EXAMPLES / "inspect/baseline.json"),
            str(EXAMPLES / "inspect/current.json"),
            "--output",
            str(out),
        ]
    )
    assert code == 0
    params = json.loads((out / "params.json").read_text())
    assert params["trial_metrics"] is True
    report = json.loads((out / "health.json").read_text())
    assert [run["file"] for run in report["trials"]["runs"]] == ["baseline.json", "current.json"]
    summary = (out / "summary.md").read_text()
    assert "| `current.json` | 8 | 16 | 0 | 2 | 87.5% | 75.0% |" in summary
    assert "Cases with ≥ k assessed trials" in summary
    html = (out / "index.html").read_text()
    assert "<h2>Case-level trials</h2>" in html and "<caption>" in html
    capsys.readouterr()
    assert main(["verify", str(out), "--json"]) == 0
    capsys.readouterr()

    # A tampered trial rate no longer matches the recomputed report.
    report["trials"]["runs"][1]["by_k"][1]["pass_hat_k"] = 1.0
    (out / "health.json").write_text(json.dumps(report))
    assert main(["verify", str(out), "--json"]) == 2


def test_untrusted_file_names_stay_in_one_table_cell(tmp_path):
    name = "x|y\r### EvalArc eval health: no warnings.json"
    run = inspect_log(tmp_path / "r.json", {"c": [{"a": True}]})
    run["source"]["name"] = name
    from evalarc.eval_health import _trial_markdown

    lines = _trial_markdown(health([run])["trials"])
    row = next(line for line in lines if "EvalArc" in line)
    assert "\r" not in row and "\n" not in row
    assert not any(line.startswith("###") for line in lines)


def test_trial_html_escapes_untrusted_names(tmp_path):
    from evalarc.eval_health import _trial_html
    from evalarc.report import _esc

    run = inspect_log(tmp_path / "r.json", {"c": [{"a": True}]})
    run["source"]["name"] = "<img src=x onerror=alert(1)>.json"
    result = health([run])["trials"]
    html = _trial_html(result, _esc)
    assert "<img" not in html and "&lt;img src=x onerror=alert(1)&gt;.json" in html
    tampered = {**result, "definition": "<script>alert(1)</script>"}
    assert "<script>" not in _trial_html(tampered, _esc)


def test_trial_metrics_option_must_be_boolean(tmp_path):
    run = inspect_log(tmp_path / "r.json", {"c": [{"a": True}]})
    params = {
        "saturation": 0.95,
        "min_effect": None,
        "ordered": False,
        "plan_attempts": None,
        "plan_configs": None,
        "trial_metrics": "false",
    }
    with pytest.raises(ValueError, match="trial_metrics must be true or false"):
        evidence.compute_health([run], params, None)

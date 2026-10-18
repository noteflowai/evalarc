"""Case attributes: expect_action, expect_change (F2P/P2P), impact and owner."""

import json
from pathlib import Path

import pytest

from evalarc import evidence, provenance, trials
from evalarc.cli import main
from evalarc.eval_health import health
from evalarc.results_diff import load_results
from tests.test_diff_suites import PARAMS, log, write_manifest

ROOT = Path(__file__).resolve().parents[1]
INSPECT = ROOT / "examples/results-diff/inspect"
JUNIT = ROOT / "examples/results-diff/junit"


def inspect_runs():
    return [load_results(INSPECT / f"{n}.json") for n in ("baseline", "current")]


def junit_runs():
    return [load_results(JUNIT / f"{n}.xml") for n in ("baseline", "current")]


# --- manifest ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("expect_action", "maybe", "expect_action must be one of act, abstain"),
        ("expect_change", "p2p", "expect_change must be one of fail_to_pass, pass_to_pass"),
        ("impact", "urgent", "impact must be one of critical, high, normal, low"),
        ("owner", "", "owner must be a non-empty single-line string"),
        ("owner", "x" * 201, "owner must be a non-empty single-line string"),
        ("owner", 7, "owner must be a non-empty single-line string"),
    ],
)
def test_invalid_attributes(tmp_path, field, value, message):
    path = write_manifest(tmp_path / "m.json", [{"match": "*", "source": "manual", field: value}])
    with pytest.raises(ValueError, match=message):
        provenance.load(path)


def test_review_only_reports_declared_attributes(tmp_path):
    plain = provenance.load(
        write_manifest(tmp_path / "a.json", [{"match": "*", "source": "manual"}])
    )
    assert "attributes" not in plain["rules"][0]
    assert "attributes" not in provenance.review(plain, {"x"})
    loaded = provenance.load(INSPECT / "attributes.json")
    review = provenance.review(loaded, set(inspect_runs()[1]["cases"]))
    assert review["attributes"]["refund-duplicate"] == {
        "expect_action": "abstain",
        "impact": "critical",
        "owner": "payments-oncall",
    }


def test_behavior_findings():
    def find(actions, total):
        result = {"attributes": {f"c{i}": {"expect_action": a} for i, a in enumerate(actions)}}
        return {
            f["id"]: f["severity"]
            for f in provenance.behavior_findings(
                result, total, lambda i, s, m, **k: {"id": i, "severity": s, "message": m, **k}
            )
        }

    assert find(["act"] * 4, 4) == {"one_sided_behavior": "warning"}
    assert find(["abstain"] * 2, 2) == {"one_sided_behavior": "warning"}
    assert find(["act"] * 4 + ["abstain"], 5) == {"behavior_imbalance": "info"}
    assert find(["act", "abstain"], 3) == {"behavior_undeclared": "info"}
    assert find([], 3) == {}


# --- trials -----------------------------------------------------------------------


def test_behavior_rates_on_the_recorded_example():
    base, cur = inspect_runs()
    attributes = provenance.review(provenance.load(INSPECT / "attributes.json"), set(cur["cases"]))[
        "attributes"
    ]
    before, after = trials.behavior_rates(base, attributes), trials.behavior_rates(cur, attributes)
    # refund-small and cancel-pending should act; one cancel-pending epoch now fails.
    assert before["act"]["undertrigger_rate"] == 0.0 and after["act"]["undertrigger_rate"] == 0.25
    # refund-duplicate, cancel-shipped and refund-large should be refused.
    assert before["abstain"]["overtrigger_rate"] == pytest.approx(0.666667)
    assert after["abstain"]["overtrigger_rate"] == pytest.approx(0.333333)
    assert trials.behavior_rates(cur, {"x": {"impact": "low"}}) is None


def test_expected_changes(tmp_path):
    base = load_results(
        log(
            tmp_path / "b.json",
            {
                "fix": [False, False],
                "keep": [True, True],
                "flaky": [True, False],
                "lost": [True, True],
            },
        )
    )
    cur = load_results(
        log(
            tmp_path / "c.json",
            {"fix": [True, True], "keep": [True, True], "flaky": [False, False], "lost": [True]},
        )
    )
    attributes = {
        "fix": {"expect_change": "fail_to_pass"},
        "keep": {"expect_change": "pass_to_pass"},
        "flaky": {"expect_change": "pass_to_pass"},
        "lost": {"expect_change": "pass_to_pass"},
    }
    result = trials.expected_changes(base, cur, attributes)
    assert result["fail_to_pass"]["resolved"] == ["fix"]
    assert result["fail_to_pass"]["unresolved"] == []
    # Fewer trials is broken; a case that was not reliable on the baseline is not.
    assert [item["case_id"] for item in result["pass_to_pass"]["broken"]] == ["lost"]
    assert result["pass_to_pass"]["not_passing_on_baseline"] == ["flaky"]
    assert trials.expected_changes(base, cur, {"x": {"impact": "low"}}) is None


# --- diff --cases -----------------------------------------------------------------


def test_diff_attributes_view_and_impact_order():
    manifest = provenance.load(INSPECT / "attributes.json")
    result = evidence.compute_diff(inspect_runs(), PARAMS, None, [], manifest)
    view = result["case_attributes"]
    assert view["behavior"]["current"]["act"]["undertrigger_rate"] == 0.25
    assert [item["impact"] for item in view["blocking_by_impact"]] == [
        "critical",
        "critical",
        "normal",
    ]
    assert view["blocking_by_impact"][0]["owner"] == "payments-oncall"
    row = next(r for r in result["changes"] if r["case_id"] == "refund-duplicate")
    assert row["impact"] == "critical" and row["expect_action"] == "abstain"
    assert "suites" not in result  # this manifest declares no suite
    assert "f2p_required" not in result


def test_require_f2p_on_the_recorded_junit_example(capsys, tmp_path):
    manifest = provenance.load(JUNIT / "cases.json")
    params = {**PARAMS, "require_f2p": True}
    result = evidence.compute_diff(junit_runs(), params, None, [], manifest)
    changes = result["case_attributes"]["expected_changes"]
    assert changes["fail_to_pass"]["resolved"] == [
        "refund_checks::test_policy_outcome[refund-large]"
    ]
    assert len(changes["pass_to_pass"]["broken"]) == 2
    assert result["f2p_passed"] is False and evidence.diff_passed(result) is False

    out = tmp_path / "f2p"
    args = [
        "diff",
        str(JUNIT / "baseline.xml"),
        str(JUNIT / "current.xml"),
        "--cases",
        str(JUNIT / "cases.json"),
    ]
    assert main([*args, "--require-f2p", "--output", str(out)]) == 1
    assert json.loads((out / "params.json").read_text())["require_f2p"] is True
    summary = (out / "summary.md").read_text()
    assert summary.startswith("### EvalArc: 2 check(s) lost passes or coverage; fail_to_pass")
    assert "<h2>Case attributes</h2>" in (out / "index.html").read_text()
    capsys.readouterr()
    assert main(["verify", str(out), "--json"]) == 0
    params = json.loads((out / "params.json").read_text())
    del params["require_f2p"]
    (out / "params.json").write_text(json.dumps(params))
    assert main(["verify", str(out), "--json"]) == 2


def test_require_f2p_passes_when_resolved_and_nothing_broke(tmp_path):
    base = load_results(log(tmp_path / "b.json", {"fix": [False], "keep": [True]}))
    cur = load_results(log(tmp_path / "c.json", {"fix": [True], "keep": [True]}))
    manifest = provenance.load(
        write_manifest(
            tmp_path / "m.json",
            [
                {"match": "fix", "source": "bug_report", "expect_change": "fail_to_pass"},
                {"match": "keep", "source": "manual", "expect_change": "pass_to_pass"},
            ],
        )
    )
    result = evidence.compute_diff([base, cur], {**PARAMS, "require_f2p": True}, None, [], manifest)
    assert result["f2p_passed"] is True and evidence.diff_passed(result) is True


def test_option_errors(tmp_path, capsys):
    b, c = str(JUNIT / "baseline.xml"), str(JUNIT / "current.xml")
    assert main(["diff", b, c, "--require-f2p"]) == 2
    assert "--require-f2p requires --cases" in capsys.readouterr().err
    only_impact = write_manifest(
        tmp_path / "m.json", [{"match": "*", "source": "manual", "impact": "low"}]
    )
    assert main(["diff", b, c, "--cases", str(only_impact), "--require-f2p"]) == 2
    assert "needs at least one case" in capsys.readouterr().err
    nothing = write_manifest(tmp_path / "n.json", [{"match": "*", "source": "manual"}])
    assert main(["diff", b, c, "--cases", str(nothing)]) == 2
    assert "declares no suite and no case attributes" in capsys.readouterr().err
    with pytest.raises(ValueError, match="require_f2p must be true or false"):
        evidence.compute_diff(junit_runs(), {**PARAMS, "require_f2p": "yes"}, None, [], None)


def test_suites_and_attributes_together(tmp_path):
    manifest = provenance.load(
        write_manifest(
            tmp_path / "m.json",
            [
                {
                    "match": "refund-*",
                    "source": "support_ticket",
                    "suite": "regression",
                    "impact": "critical",
                },
                {"match": "cancel-*", "source": "bug_report", "suite": "capability"},
            ],
        )
    )
    result = evidence.compute_diff(inspect_runs(), PARAMS, None, [], manifest)
    assert result["suites"]["regression_failures"][0]["case_id"] == "refund-duplicate"
    assert result["case_attributes"]["blocking_by_impact"][0]["impact"] == "critical"


def test_untrusted_owner_is_escaped(tmp_path):
    from evalarc.report import _esc
    from evalarc.suite_report import attributes_html, attributes_markdown

    base = load_results(log(tmp_path / "b.json", {"c": [True]}))
    cur = load_results(log(tmp_path / "c.json", {"c": [False]}))
    owner = "<img src=x onerror=1>|` ### fake"
    manifest = provenance.load(
        write_manifest(tmp_path / "m.json", [{"match": "c", "source": "manual", "owner": owner}])
    )
    result = evidence.compute_diff([base, cur], PARAMS, None, [], manifest)
    assert "<img" not in attributes_html(result, _esc)
    markdown = attributes_markdown(result)
    assert "\r" not in markdown and not any(
        line.lstrip("| ").startswith("### fake") for line in markdown.splitlines()
    )


# --- eval-health and review-inputs ------------------------------------------------


def test_eval_health_behavior_and_findings():
    runs = inspect_runs()
    plain = health(runs, cases_manifest=provenance.load(INSPECT / "cases.json"))
    assert "behavior" not in plain
    result = health(runs, cases_manifest=provenance.load(INSPECT / "attributes.json"))
    assert [row["file"] for row in result["behavior"]] == ["baseline.json", "current.json"]
    assert result["behavior"][1]["abstain"]["overtrigger_rate"] == pytest.approx(0.333333)
    assert "behavior_undeclared" in {f["id"] for f in result["findings"]}


def test_review_inputs_attributes(tmp_path, capsys):
    from tests.test_eval_project import base_case, write_cases

    project = tmp_path / "p"
    assert main(["eval-init", str(project)]) == 0
    write_cases(
        project,
        [
            base_case(id="a", expect_action="act", impact="high", owner="team-a"),
            base_case(id="b", expect_action="act", input="other"),
            base_case(id="c", input="third", expect_change="fail_to_pass"),
        ],
    )
    manifest, out = tmp_path / "m.json", tmp_path / "r"
    capsys.readouterr()
    assert (
        main(
            [
                "review-inputs",
                str(project / "cases.jsonl"),
                "--write-manifest",
                str(manifest),
                "--output",
                str(out),
            ]
        )
        == 0
    )
    printed = capsys.readouterr().out
    assert "one_sided_behavior" in printed and "impact_undeclared" in printed
    entries = {e["match"]: e for e in json.loads(manifest.read_text())["cases"]}
    assert entries["a"]["owner"] == "team-a" and entries["c"]["expect_change"] == "fail_to_pass"
    report = json.loads((out / "review.json").read_text())
    assert report["expect_action"] == {"act": 2} and report["impact"] == {"high": 1}
    assert '<th scope="col">Attributes</th>' in (out / "index.html").read_text()
    write_cases(project, [base_case(impact="urgent")])
    assert main(["review-inputs", str(project / "cases.jsonl")]) == 2
    assert "cases.jsonl:1 impact must be one of" in capsys.readouterr().err


def test_review_inputs_without_attributes_is_unchanged(tmp_path, capsys):
    project = tmp_path / "p"
    assert main(["eval-init", str(project)]) == 0
    out = tmp_path / "r"
    assert main(["review-inputs", str(project / "cases.jsonl"), "--output", str(out)]) == 0
    report = json.loads((out / "review.json").read_text())
    assert not {"expect_action", "expect_change", "impact"} & set(report)
    assert "Attributes</th>" not in (out / "index.html").read_text()


def test_require_f2p_alone_fails_an_otherwise_passing_gate(tmp_path, capsys):
    b = log(tmp_path / "b.json", {"fix": [False], "keep": [True]})
    c = log(tmp_path / "c.json", {"fix": [False], "keep": [True]})
    manifest = write_manifest(
        tmp_path / "m.json",
        [{"match": "fix", "source": "bug_report", "expect_change": "fail_to_pass"}],
    )
    args = ["diff", str(b), str(c), "--cases", str(manifest)]
    assert main(args) == 0
    capsys.readouterr()
    out = tmp_path / "o"
    assert main([*args, "--require-f2p", "--output", str(out)]) == 1
    summary = (out / "summary.md").read_text()
    assert summary.startswith("### EvalArc: fail_to_pass/pass_to_pass contract not met")
    assert "fail_to_pass case is unresolved" in (out / "index.html").read_text()


def test_a_shadowed_attribute_entry_is_an_error(tmp_path):
    shadowed = provenance.load(
        write_manifest(
            tmp_path / "m.json",
            [
                {"match": "*", "source": "manual", "expect_change": "pass_to_pass"},
                {"match": "fix", "source": "bug_report", "expect_change": "fail_to_pass"},
            ],
        )
    )
    with pytest.raises(ValueError, match="put specific entries before globs"):
        provenance.review(shadowed, {"fix", "keep"})
    # Entries without attributes keep first-match-wins without an error.
    plain = provenance.load(
        write_manifest(
            tmp_path / "p.json",
            [{"match": "*", "source": "manual"}, {"match": "fix", "source": "bug_report"}],
        )
    )
    assert provenance.review(plain, {"fix", "keep"})["declared"] == 2


def test_missing_cases_are_reported_as_not_recorded(tmp_path):
    from evalarc.suite_report import attributes_markdown

    base = load_results(log(tmp_path / "b.json", {"fix": [False], "keep": [True], "x": [True]}))
    cur = load_results(log(tmp_path / "c.json", {"x": [True]}))
    manifest = provenance.load(
        write_manifest(
            tmp_path / "m.json",
            [
                {"match": "fix", "source": "bug_report", "expect_change": "fail_to_pass"},
                {"match": "keep", "source": "manual", "expect_change": "pass_to_pass"},
            ],
        )
    )
    result = evidence.compute_diff([base, cur], PARAMS, None, [], manifest)
    changes = result["case_attributes"]["expected_changes"]
    assert changes["not_recorded_in_current"] == ["fix", "keep"]
    markdown = attributes_markdown(result)
    assert "unresolved `fix`: not recorded in the current run" in markdown
    assert "broken `keep`: not recorded in the current run" in markdown


def test_owner_must_be_one_line(tmp_path):
    path = write_manifest(
        tmp_path / "m.json", [{"match": "*", "source": "manual", "owner": "a\nb"}]
    )
    with pytest.raises(ValueError, match="single-line"):
        provenance.load(path)

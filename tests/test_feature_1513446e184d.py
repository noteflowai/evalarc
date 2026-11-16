"""Nested JUnit suites under a root <testsuite> are compared, not silently dropped.

All XML in this file is synthetic and written for these tests; it is not a real
runner export.
"""

from evalarc.cli import main
from evalarc.results_diff import diff, load_results

BASELINE = """<testsuite name="outer">
  <testcase name="a"/>
  <testsuite name="inner">
    <testcase name="b"/>
  </testsuite>
</testsuite>
"""

FAILING = BASELINE.replace(
    '<testcase name="b"/>', '<testcase name="b"><failure message="boom"/></testcase>'
)

WITHOUT_INNER = """<testsuite name="outer">
  <testcase name="a"/>
</testsuite>
"""

UNNAMED = BASELINE.replace('<testcase name="b"/>', "<testcase/>")

WRAPPED = """<testsuites>
  <testsuite name="outer">
    <testcase name="a"/>
    <testsuite name="inner">
      <testcase name="b"/>
    </testsuite>
  </testsuite>
</testsuites>
"""


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return path


def kinds(result):
    return [(row["kind"], row["case_id"], row["check"]) for row in result["changes"]]


def test_nested_suite_testcases_are_loaded_once(tmp_path):
    run = load_results(write(tmp_path, "base.xml", BASELINE))
    assert sorted(run["cases"]) == ["inner::b", "outer::a"]
    for case_id in ("inner::b", "outer::a"):
        assert len(run["cases"][case_id]["passed"]) == 1
    assert diff(run, run)["baseline"]["identity"]["suites"] == ["inner", "outer"]


def test_nested_failure_regresses_and_cli_exits_1(tmp_path):
    base = write(tmp_path, "base.xml", BASELINE)
    cur = write(tmp_path, "cur.xml", FAILING)
    result = diff(load_results(base), load_results(cur))
    assert kinds(result) == [("regressed", "inner::b", "passed")]
    assert result["gate_passed"] is False
    output = tmp_path / "review"
    assert main(["diff", str(base), str(cur), "--output", str(output)]) == 1
    summary = (output / "summary.md").read_text()
    assert "Why the gate failed" in summary
    assert "inner::b" in summary.split("Why the gate failed", 1)[1]
    recorded = (output / "diff.json").read_text()
    assert "inner::b" in recorded


def test_missing_nested_suite_is_removed_and_fails(tmp_path):
    base = write(tmp_path, "base.xml", BASELINE)
    cur = write(tmp_path, "cur.xml", WITHOUT_INNER)
    result = diff(load_results(base), load_results(cur))
    assert kinds(result) == [("removed", "inner::b", "passed")]
    assert result["gate_passed"] is False
    assert main(["diff", str(base), str(cur)]) == 1


def test_testsuites_root_and_flat_root_are_unchanged(tmp_path):
    wrapped = load_results(write(tmp_path, "wrapped.xml", WRAPPED))
    assert sorted(wrapped["cases"]) == ["inner::b", "outer::a"]
    for attempts in wrapped["cases"].values():
        assert len(attempts["passed"]) == 1
    flat = load_results(write(tmp_path, "flat.xml", WITHOUT_INNER))
    assert list(flat["cases"]) == ["outer::a"]
    assert len(flat["cases"]["outer::a"]["passed"]) == 1
    same = write(tmp_path, "same.xml", WRAPPED)
    assert main(["diff", str(same), str(same)]) == 0


def test_unnamed_nested_testcase_is_rejected(tmp_path, capsys):
    bad = write(tmp_path, "bad.xml", UNNAMED)
    try:
        load_results(bad)
    except ValueError as error:
        assert "position 0 in suite 'inner'" in str(error)
    else:
        raise AssertionError("unnamed nested testcase was accepted")
    base = write(tmp_path, "base.xml", BASELINE)
    assert main(["diff", str(base), str(bad)]) == 2
    assert "position 0 in suite 'inner'" in capsys.readouterr().err

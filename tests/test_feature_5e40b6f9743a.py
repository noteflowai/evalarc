"""SYNTHETIC JUnit identity cases: a testcase without a name cannot be compared.

Every input is hand-written XML in tmp_path. The cases pin how evalarc diff treats
JUnit testcases whose name attribute is missing, empty or whitespace-only. They say
nothing about which real exporters emit such testcases.
"""

import pytest

from evalarc.cli import main
from evalarc.results_diff import diff, load_results

MISSING = object()
HINT = (
    "each testcase needs a name to be compared. "
    "Re-export the results with test names or fix the XML."
)


def _not_a_test(function):
    # pytest collects module-level functions whose names start with "test"; this
    # XML builder is a helper, not a test.
    function.__test__ = False
    return function


@_not_a_test
def testcase(name, failed):
    attribute = "" if name is MISSING else f' name="{name}"'
    body = '<failure message="synthetic failure"/>' if failed else ""
    return f'<testcase classname="corpus"{attribute}>{body}</testcase>'


def suite_xml(cases, suite="corpus", wrap=False):
    label = "" if suite is None else f' name="{suite}"'
    body = "".join(testcase(name, failed) for name, failed in cases)
    xml = f"<testsuite{label}>{body}</testsuite>"
    if wrap:
        xml = f"<testsuites>{xml}</testsuites>"
    return f'<?xml version="1.0"?>\n{xml}\n'


def write(path, text):
    path.write_text(text)
    return path


def message(position, suite="'corpus'"):
    return f"JUnit testcase at position {position} in suite {suite} has no name attribute"


def test_swapped_failure_between_unnamed_testcases_exits_2(tmp_path, capsys):
    # Before the fix both files tallied 1/2 for one merged check and the gate passed.
    baseline = write(tmp_path / "baseline.xml", suite_xml([(MISSING, True), (MISSING, False)]))
    current = write(tmp_path / "current.xml", suite_xml([(MISSING, False), (MISSING, True)]))
    assert main(["diff", str(baseline), str(current)]) == 2
    err = capsys.readouterr().err
    assert f"{message(0)}; {HINT}" in err


@pytest.mark.parametrize(
    "blank", ["", "   "], ids=["synthetic-empty-name", "synthetic-whitespace-name"]
)
def test_blank_name_is_rejected_on_either_side(tmp_path, capsys, blank):
    named = write(tmp_path / "named.xml", suite_xml([("test_a", False), ("test_b", False)]))
    broken = write(tmp_path / "broken.xml", suite_xml([("test_a", False), (blank, False)]))
    with pytest.raises(ValueError) as error:
        load_results(broken, "junit")
    assert message(1) in str(error.value)
    for pair in ((named, broken), (broken, named)):
        assert main(["diff", *map(str, pair)]) == 2
        assert message(1) in capsys.readouterr().err


def test_unnamed_suite_under_testsuites_is_reported(tmp_path):
    path = write(tmp_path / "suites.xml", suite_xml([(MISSING, False)], suite=None, wrap=True))
    with pytest.raises(ValueError, match=r"in suite \(unnamed suite\) has no name attribute"):
        load_results(path, "junit")


def test_named_testcases_keep_their_ids_and_show_the_swap(tmp_path, capsys):
    baseline = write(tmp_path / "baseline.xml", suite_xml([("test_a", True), ("test_b", False)]))
    current = write(tmp_path / "current.xml", suite_xml([("test_a", False), ("test_b", True)]))
    before, after = load_results(baseline, "junit"), load_results(current, "junit")
    assert sorted(before["cases"]) == ["corpus::test_a", "corpus::test_b"]
    result = diff(before, after)
    assert sorted((row["kind"], row["case_id"]) for row in result["changes"]) == [
        ("improved", "corpus::test_a"),
        ("regressed", "corpus::test_b"),
    ]
    assert main(["diff", str(baseline), str(current)]) == 1
    assert "no name attribute" not in capsys.readouterr().err


def test_identically_named_testcases_are_still_repeated_attempts(tmp_path):
    path = write(tmp_path / "repeats.xml", suite_xml([("test_a", False), ("test_a", True)]))
    loaded = load_results(path, "junit")
    assert sorted(loaded["cases"]) == ["corpus::test_a"]
    attempts = loaded["cases"]["corpus::test_a"]["passed"]
    assert [attempt["passed"] for attempt in attempts] == [True, False]

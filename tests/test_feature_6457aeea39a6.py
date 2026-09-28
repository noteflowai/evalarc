"""Behavioral tests for evalarc decision-coverage on authored synthetic decisions."""

import hashlib
import json
from pathlib import Path

import pytest

from evalarc.cli import main

ROOT = Path(__file__).resolve().parents[1]
OUTCOMES = ("correct", "wrong", "abstained", "invalid")
CHOSEN = 'class="marker chosen-marker">chosen</span>'


def dist(**probabilities):
    return {"distribution": probabilities}


def rec(rid, question, split, label, response):
    return {
        "id": rid,
        "question": question,
        "split": split,
        "label": label,
        "response": response,
    }


def base():
    return {
        "schema_version": "evalarc.decision-records.v1",
        "provenance": {"kind": "synthetic", "description": "Authored test decisions"},
        "model": {"id": "synthetic-choice", "revision": "test-1"},
        "questions": {
            "grip": {"type": "choice", "options": ["a", "b", "c"]},
            "go": {"type": "choice", "options": ["yes", "no"]},
        },
        "records": [
            rec("c1", "grip", "calibration", "a", dist(a=0.9, b=0.1)),
            rec("c2", "grip", "calibration", "b", dist(a=0.8, b=0.2)),
            rec("c3", "go", "calibration", "yes", dist(yes=0.7, no=0.3)),
            # Tie: "no" is listed first here, but "yes" is declared first.
            rec("c4", "go", "calibration", "no", dist(no=0.5, yes=0.5)),
            rec("c5", "grip", "calibration", "c", {"error": "timeout after 30 s"}),
            rec("h1", "grip", "held_out", "a", dist(a=0.95, c=0.05)),
            rec("h2", "go", "held_out", "no", dist(yes=0.75, no=0.25)),
            rec("h3", "grip", "held_out", "b", dist(b=0.6, a=0.4)),
            rec("h4", "go", "held_out", "yes", dist(yes=0.55, no=0.45)),
        ],
    }


# (total, answered, wrong, abstained, invalid) for each candidate threshold
CAL = {
    0.0: (5, 4, 2, 0, 1),
    0.5: (5, 4, 2, 0, 1),
    0.7: (5, 3, 1, 1, 1),
    0.8: (5, 2, 1, 2, 1),
    0.9: (5, 1, 0, 3, 1),
}
HELD = {
    0.0: (4, 4, 1, 0, 0),
    0.5: (4, 4, 1, 0, 0),
    0.7: (4, 2, 1, 2, 0),
    0.8: (4, 1, 0, 3, 0),
    0.9: (4, 1, 0, 3, 0),
}


def metrics(total, answered, wrong, abstained, invalid):
    return {
        "total": total,
        "answered": answered,
        "correct": answered - wrong,
        "wrong": wrong,
        "abstained": abstained,
        "invalid": invalid,
        "coverage": answered / total,
        "selective_error": wrong / answered if answered else None,
        "wrong_rate_all": wrong / total,
    }


def run(tmp_path, data=None, *extra, name="report", raw=None):
    source = tmp_path / f"{name}.json"
    source.write_bytes(raw if raw is not None else json.dumps(data, indent=2).encode())
    output = tmp_path / name
    code = main(["decision-coverage", str(source), "--output", str(output), *extra])
    return code, output


def decisions(output):
    return json.loads((output / "decisions.json").read_text(encoding="utf-8"))


def by_id(result):
    return {row["id"]: row for row in result["records"]}


def check_filters(output, result):
    """Recount outcomes at the review threshold and compare them with the rendered page."""
    threshold = result["review_threshold"]
    expected = dict.fromkeys(OUTCOMES, 0)
    for row in result["records"]:
        if row["prediction"] is None:
            outcome = "invalid"
        elif row["confidence"] < threshold:
            outcome = "abstained"
        else:
            outcome = "correct" if row["prediction"] == row["label"] else "wrong"
        assert row["outcome"] == outcome
        expected[outcome] += 1
    assert result["outcomes"] == expected
    page = (output / "index.html").read_text(encoding="utf-8")
    total = len(result["records"])
    assert f'data-filter="all" aria-pressed="true">All ({total})</button>' in page
    for key in ("wrong", "abstained", "invalid"):
        label = f"{key.capitalize()} ({expected[key]})"
        assert f'data-filter="{key}" aria-pressed="false">{label}</button>' in page
    for key in OUTCOMES:
        assert page.count(f'<tr data-outcome="{key}"') == expected[key]
    assert f"Showing {total} of {total}; all records in decisions.json" in page
    return page


def test_no_target_reports_exact_sweep_and_resolves_ties_to_first_option(tmp_path, capsys):
    code, output = run(tmp_path, base())
    assert code == 0
    result = decisions(output)
    assert result["state"] == "no_target"
    assert result["chosen_threshold"] is None and result["review_threshold"] == 0
    assert result["headline"] == "No target set; records classified at baseline t=0"
    assert [row["threshold"] for row in result["sweep"]] == sorted(CAL)
    for row in result["sweep"]:
        assert row["calibration"] == metrics(*CAL[row["threshold"]])
        assert row["held_out"] == metrics(*HELD[row["threshold"]])
    assert result["baseline"] == result["sweep"][0]
    assert result["review"]["held_out"] == metrics(4, 4, 1, 0, 0)
    rows = by_id(result)
    assert (rows["c4"]["prediction"], rows["c4"]["confidence"]) == ("yes", 0.5)
    assert rows["c4"]["outcome"] == "wrong"
    assert rows["c5"]["outcome"] == "invalid"
    assert rows["c5"]["reason"] == "provider error: timeout after 30 s"
    page = check_filters(output, result)
    assert "<h1>No target set; records classified at baseline t=0</h1>" in page
    assert CHOSEN not in page
    captured = capsys.readouterr()
    assert result["headline"] in captured.out and "Traceback" not in captured.err


INVALID = [
    ({"error": "rate limited"}, "provider error: rate limited"),
    ({"error": ""}, "non-empty string"),
    (dist(z=1.0), "undeclared option"),
    (dist(a=-0.1, b=1.1), "outside 0..1"),
    (dist(a=1.2), "outside 0..1"),
    (dist(a="0.6", b=0.4), "not a finite number"),
    (dist(a=True), "not a finite number"),
    (dist(a=None, b=1.0), "not a finite number"),
    (dist(a=0.5, b=0.4), "sum to"),
    ({"distribution": {"a": 1.0}, "error": "x"}, "exactly one of distribution or error"),
    (["a", 1.0], "response is a list"),
]


def test_malformed_responses_become_invalid_rows_not_wrong_answers(tmp_path, capsys):
    data = base()
    for index, (response, _) in enumerate(INVALID):
        data["records"].append(rec(f"bad-{index}", "grip", "held_out", "a", response))
    code, output = run(tmp_path, data)
    assert code == 0
    result = decisions(output)
    rows = by_id(result)
    for index, (_, reason) in enumerate(INVALID):
        row = rows[f"bad-{index}"]
        assert row["outcome"] == "invalid" and row["prediction"] is None
        assert reason in row["reason"]
    assert result["review"]["held_out"] == metrics(15, 4, 1, 0, 11)
    check_filters(output, result)
    assert "Traceback" not in capsys.readouterr().err


def raw_with(prefix):
    text = json.dumps(base())
    return text.replace('"schema_version"', prefix + '"schema_version"', 1).encode()


def mutated(change):
    data = base()
    change(data)
    return json.dumps(data).encode()


REJECTED = [
    pytest.param(lambda: raw_with('"extra": NaN, '), "NaN is not valid JSON", id="nan"),
    pytest.param(
        lambda: raw_with('"extra": Infinity, '), "Infinity is not valid JSON", id="infinity"
    ),
    pytest.param(lambda: raw_with('"model": {}, '), "duplicate JSON key", id="duplicate-key"),
    pytest.param(
        lambda: mutated(lambda d: d["records"][6].update(id="h1")),
        "duplicate record ID",
        id="duplicate-id",
    ),
    pytest.param(
        lambda: mutated(lambda d: d["records"].append(5)),
        "must be an object",
        id="non-object-record",
    ),
    pytest.param(
        lambda: mutated(lambda d: d["records"][0].update(label="z")),
        "outside the options",
        id="label",
    ),
    pytest.param(
        lambda: mutated(lambda d: d["questions"]["go"].update(type="score")),
        'only "choice" questions',
        id="non-choice",
    ),
    pytest.param(
        lambda: mutated(lambda d: d["records"][0].update(split="test")),
        "use calibration or held_out",
        id="unknown-split",
    ),
    pytest.param(
        lambda: mutated(lambda d: d.update(records=d["records"][:5])),
        "no held_out records",
        id="no-held-out",
    ),
]


@pytest.mark.parametrize("raw,message", REJECTED)
def test_rejected_files_exit_2_without_output(tmp_path, capsys, raw, message):
    code, output = run(tmp_path, raw=raw())
    assert code == 2 and not output.exists()
    err = capsys.readouterr().err
    assert message in err and "Traceback" not in err


@pytest.mark.parametrize("value", ["nan", "inf", "-0.1", "1.5"])
def test_invalid_max_error_exits_2_without_output(tmp_path, capsys, value):
    code, output = run(tmp_path, base(), f"--max-error={value}")
    assert code == 2 and not output.exists()
    assert "--max-error must be" in capsys.readouterr().err


def test_existing_output_is_rejected_and_left_unchanged(tmp_path, capsys):
    output = tmp_path / "report"
    output.mkdir()
    (output / "keep.txt").write_text("mine")
    code, _ = run(tmp_path, base())
    assert code == 2
    assert [path.name for path in output.iterdir()] == ["keep.txt"]
    assert (output / "keep.txt").read_text() == "mine"
    assert "already exists" in capsys.readouterr().err


def test_met_state_uses_calibration_threshold(tmp_path):
    code, output = run(tmp_path, base(), "--max-error", "0")
    assert code == 0
    result = decisions(output)
    assert result["state"] == "met" and result["chosen_threshold"] == 0.9
    headline = "Held-out error 0.00 at 25% coverage (t=0.90); target 0 met"
    assert result["headline"] == headline
    assert result["review"]["held_out"] == metrics(4, 1, 0, 3, 0)
    page = check_filters(output, result)
    assert f"<h1>{headline}</h1>" in page and CHOSEN in page


def test_exceeded_state_and_heldout_labels_do_not_move_threshold(tmp_path):
    code, output = run(tmp_path, base(), "--max-error", "0.4")
    assert code == 1
    result = decisions(output)
    assert result["state"] == "exceeded" and result["chosen_threshold"] == 0.7
    headline = "Held-out error 0.50 at 50% coverage (t=0.70); target 0.40 exceeded"
    assert result["headline"] == headline
    page = check_filters(output, result)
    assert result["outcomes"] == {"wrong": 2, "invalid": 1, "abstained": 3, "correct": 3}
    assert f"<h1>{headline}</h1>" in page and CHOSEN in page

    relabelled = base()
    relabelled["records"][6]["label"] = "yes"
    code, output = run(tmp_path, relabelled, "--max-error", "0.4", name="relabelled")
    assert code == 0
    changed = decisions(output)
    assert changed["state"] == "met" and changed["chosen_threshold"] == 0.7
    assert changed["review"]["calibration"] == result["review"]["calibration"]
    assert changed["review"]["held_out"] == metrics(4, 2, 0, 2, 0)
    check_filters(output, changed)


def test_no_threshold_state_classifies_at_baseline(tmp_path):
    data = base()
    data["records"][0]["label"] = "b"
    code, output = run(tmp_path, data, "--max-error", "0.1")
    assert code == 1
    result = decisions(output)
    assert result["state"] == "no_threshold" and result["chosen_threshold"] is None
    assert result["review_threshold"] == 0
    headline = "No calibration threshold reaches error 0.10; records classified at baseline t=0"
    assert result["headline"] == headline
    page = check_filters(output, result)
    assert f"<h1>{headline}</h1>" in page and CHOSEN not in page


def test_no_heldout_answers_state_has_null_error(tmp_path):
    data = base()
    data["records"][5]["response"] = dist(a=0.85, c=0.15)
    code, output = run(tmp_path, data, "--max-error", "0")
    assert code == 1
    result = decisions(output)
    assert result["state"] == "no_heldout_answers" and result["chosen_threshold"] == 0.9
    assert result["review"]["held_out"]["selective_error"] is None
    assert result["review"]["held_out"]["answered"] == 0
    headline = "No held-out record reaches t=0.90; target 0 cannot be validated"
    assert result["headline"] == headline
    page = check_filters(output, result)
    assert f"<h1>{headline}</h1>" in page and CHOSEN in page


def test_artifacts_escaping_and_accessible_structure(tmp_path):
    data = base()
    data["records"][0]["id"] = "<script>alert(1)</script>"
    data["records"][4]["response"] = {"error": "<script>steal()</script>"}
    raw = json.dumps(data, indent=3).encode() + b"\n\n"
    code, output = run(tmp_path, None, "--max-error", "0.4", raw=raw)
    assert code == 1
    names = {path.name for path in output.iterdir()}
    assert names >= {"input.json", "input.json.sha256", "decisions.json", "index.html"}
    assert (output / "input.json").read_bytes() == raw
    digest = hashlib.sha256(raw).hexdigest()
    assert (output / "input.json.sha256").read_text() == f"{digest}  input.json\n"
    assert decisions(output)["source"]["sha256"] == digest
    page = (output / "index.html").read_text(encoding="utf-8")
    assert "<script>alert(1)" not in page and "<script>steal()" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "&lt;script&gt;steal()&lt;/script&gt;" in page
    for marker in (
        "<caption>Calibration chooses t; held-out reports it</caption>",
        'scope="colgroup"',
        'scope="col"',
        CHOSEN,
        '<button type="button" data-filter="wrong"',
        '<label for="search">',
        '<input id="search" type="search"',
        'role="status"',
        '<div class="table-scroll" tabindex="0"',
        ":focus-visible",
        "@media(max-width:480px)",
        "Synthetic data",
        "confidence is not calibration",
        "No provider accuracy is shown",
    ):
        assert marker in page


def test_large_sweep_renders_bounded_threshold_rows(tmp_path):
    data = base()
    records = []
    for index in range(60):
        p = round(0.6 + index * 0.005, 4)
        response = dist(a=p, b=round(1 - p, 4))
        records.append(rec(f"c{index:02d}", "grip", "calibration", "a", response))
    records.append(rec("h", "grip", "held_out", "a", dist(a=0.7, b=0.3)))
    data["records"] = records
    code, output = run(tmp_path, data)
    assert code == 0
    assert len(decisions(output)["sweep"]) == 61
    page = (output / "index.html").read_text(encoding="utf-8")
    rows = page.count("<tr data-threshold=")
    assert 20 <= rows <= 22
    assert f"Showing {rows} of 61 thresholds; full sweep in decisions.json" in page
    for threshold in ('"0.0"', '"0.6"', '"0.895"'):
        assert f"data-threshold={threshold}" in page


def test_help_lists_arguments_and_exit_codes(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["decision-coverage", "--help"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    for text in ("records", "--output", "--max-error", "exit codes", "  0  ", "  1  ", "  2  "):
        assert text in out


def test_bundled_synthetic_fixture_and_docs(tmp_path):
    fixture = ROOT / "docs/assets/decision-coverage-synthetic.json"
    raw = fixture.read_bytes()
    code, output = run(tmp_path, None, "--max-error", "0.2", name="fixture", raw=raw)
    result = decisions(output)
    assert code == (0 if result["state"] == "met" else 1)
    assert result["provenance"]["kind"] == "synthetic"
    assert by_id(result)["ho-06"]["outcome"] == "invalid"
    assert (output / "input.json").read_bytes() == fixture.read_bytes()
    check_filters(output, result)
    assert "decision-coverage" in (ROOT / "docs/decision-coverage.md").read_text(encoding="utf-8")
    assert "docs/decision-coverage.md" in (ROOT / "README.md").read_text(encoding="utf-8")

import json
import shutil
from pathlib import Path

import pytest

from evalarc.cli import main

ROOT = Path(__file__).resolve().parents[1]
INSPECT = ROOT / "examples/results-diff/inspect"
CLIMB = ROOT / "examples/hillclimb-review"


@pytest.fixture
def reports(tmp_path):
    out = {}
    out["diff"] = tmp_path / "diff"
    main(
        [
            "diff",
            str(INSPECT / "baseline.json"),
            str(INSPECT / "current.json"),
            "--held-out",
            str(INSPECT / "split.json"),
            "--harness",
            str(INSPECT / "harness"),
            "--max-cost-ratio",
            "2",
            "--cost-metric",
            "duration",
            "--output",
            str(out["diff"]),
        ]
    )
    out["health"] = tmp_path / "health"
    main(
        [
            "eval-health",
            str(INSPECT / "baseline.json"),
            str(INSPECT / "current.json"),
            "--cases",
            str(INSPECT / "cases.json"),
            "--min-effect",
            "0.05",
            "--ordered",
            "--plan-attempts",
            "4",
            "--output",
            str(out["health"]),
        ]
    )
    out["climb"] = tmp_path / "climb"
    steps = sorted((CLIMB / "results").glob("0*.json"))
    main(
        [
            "hillclimb-review",
            *map(str, steps),
            "--held-out",
            str(CLIMB / "split.json"),
            "--objective",
            "cost",
            "--harness",
            str(INSPECT / "harness"),
            "--output",
            str(out["climb"]),
        ]
    )
    return out


def error(capsys):
    return json.loads(capsys.readouterr().out)["error"]


def verify(path, *extra):
    return main(["verify", str(path), "--json", *extra])


@pytest.mark.parametrize(
    "name,kind,passed",
    [
        ("diff", "diff", False),
        ("health", "eval-health", False),
        ("climb", "hillclimb-review", True),
    ],
)
def test_saved_reports_verify(reports, capsys, name, kind, passed):
    capsys.readouterr()
    assert verify(reports[name]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["kind"] == kind and result["verified"] and result["passed"] is passed
    assert "params.json" in result["files"]
    assert verify(reports[name], "--require-accepted") == (0 if passed else 1)


def test_report_file_path_also_verifies(reports):
    assert verify(reports["climb"] / "hillclimb.json") == 0


def test_edited_decision_is_detected(reports, capsys):
    path = reports["climb"] / "hillclimb.json"
    document = json.loads(path.read_text())
    document["steps"][1]["decision"] = "keep"
    path.write_text(json.dumps(document))
    assert verify(reports["climb"]) == 2
    assert "differs from the recomputed" in error(capsys)


def test_edited_input_is_detected(reports, capsys):
    copy = reports["diff"] / "current.json"
    copy.write_text(copy.read_text().replace('"C"', '"I"', 1))
    assert verify(reports["diff"]) == 2
    assert "differs from the input the report recorded" in error(capsys)


def test_edited_harness_copy_is_detected(reports, capsys):
    (reports["diff"] / "harness/0000").write_text("clean prompt")
    assert verify(reports["diff"]) == 2
    assert "harness file that was scanned" in error(capsys)


def test_changed_option_is_detected(reports, capsys):
    params = reports["health"] / "params.json"
    document = json.loads(params.read_text())
    document["saturation"] = 0.5
    params.write_text(json.dumps(document))
    assert verify(reports["health"]) == 2


def test_folder_is_relocatable(reports, tmp_path):
    moved = tmp_path / "elsewhere"
    shutil.move(reports["climb"], moved)
    assert verify(moved) == 0


def test_hillclimb_run_folder_verifies(tmp_path):
    example = tmp_path / "example"
    shutil.copytree(ROOT / "examples/hillclimb-run", example)
    main(
        [
            "hillclimb-run",
            str(example / "hillclimb.toml"),
            "--output",
            str(tmp_path / "loop"),
            "--trust-local",
        ]
    )
    assert verify(tmp_path / "loop") == 0

import json
import subprocess
import sys

import pytest

from evalarc.cli import main
from evalarc.eval_health import health
from evalarc.results_diff import load_results


@pytest.fixture
def project(tmp_path):
    destination = tmp_path / "proj"
    assert main(["eval-init", str(destination)]) == 0
    return destination


def write_cases(project, cases):
    (project / "cases.jsonl").write_text("".join(json.dumps(c) + "\n" for c in cases))


def base_case(**overrides):
    case = {
        "id": "a",
        "input": "refund please",
        "expected": "billing",
        "check": "label",
        "labels": ["billing", "general"],
        "source": "production",
    }
    return case | overrides


def test_init_writes_a_runnable_project(project, tmp_path):
    assert sorted(p.name for p in project.iterdir()) == [
        "README.md",
        "app.py",
        "cases.jsonl",
        "cases.manifest.json",
        "evaluate.py",
        "grader.py",
        "hillclimb.toml",
        "prompt.md",
        "propose.py",
        "split.json",
    ]
    assert main(["eval-init", str(project)]) == 2
    log = tmp_path / "baseline.json"
    subprocess.run(
        [sys.executable, "evaluate.py", str(log), "--epochs", "2"], cwd=project, check=True
    )
    run = load_results(log)
    assert len(run["cases"]) == 9 and run["identity"]["epochs"] == 2
    manifest = json.loads((project / "cases.manifest.json").read_text())
    report = health(
        [run],
        cases_manifest=__import__("evalarc.provenance").provenance.load(
            project / "cases.manifest.json"
        ),
    )
    assert report["provenance"]["declared"] == 9 and manifest["cases"][0]["match"]


def test_review_inputs_derives_split_and_manifest(project, tmp_path, capsys):
    output = tmp_path / "review"
    split, manifest = tmp_path / "split.json", tmp_path / "manifest.json"
    code = main(
        [
            "review-inputs",
            str(project / "cases.jsonl"),
            "--output",
            str(output),
            "--write-split",
            str(split),
            "--write-manifest",
            str(manifest),
            "--require-clean",
        ]
    )
    assert code == 0
    assert "9 cases, 3 held out, 0 warning(s)" in capsys.readouterr().out
    assert json.loads(split.read_text())["held_out"] == [
        "holdout-outage",
        "holdout-refund",
        "holdout-shipping",
    ]
    assert json.loads(manifest.read_text()) == json.loads(
        (project / "cases.manifest.json").read_text()
    )
    page = (output / "index.html").read_text()
    assert "Review the inputs before running" in page and "holdout-refund" in page


def test_review_findings(project, capsys):
    write_cases(
        project,
        [
            base_case(id="a"),
            base_case(id="b"),
            base_case(id="c", input="something else", source="model_failure"),
            base_case(id="d", input="other", expected="general"),
            base_case(id="e", input="refund  PLEASE"),
        ],
    )
    code = main(["review-inputs", str(project / "cases.jsonl"), "--require-clean"])
    out = capsys.readouterr().out
    assert code == 1
    for finding in ("no_held_out", "duplicate_inputs", "adversarial_sampling", "dominant_answer"):
        assert finding in out
    assert main(["review-inputs", str(project / "cases.jsonl")]) == 0


@pytest.mark.parametrize(
    "case,message",
    [
        (base_case(check="regex"), "check must be one of"),
        (base_case(source="guess"), "source must be one of"),
        (base_case(expected="oncall"), "labels (2+) that include expected"),
        (base_case(check="json_keys", expected="x"), "list of key names"),
        (base_case(held_out="yes"), "held_out must be"),
        (base_case(notes="x"), "unknown fields"),
        ({"id": "a"}, "non-empty string input"),
    ],
)
def test_invalid_cases(project, capsys, case, message):
    write_cases(project, [case])
    assert main(["review-inputs", str(project / "cases.jsonl")]) == 2
    assert message in capsys.readouterr().err


def test_duplicate_ids_and_split_needs_both_sides(project, capsys, tmp_path):
    write_cases(project, [base_case(), base_case()])
    assert main(["review-inputs", str(project / "cases.jsonl")]) == 2
    assert "repeats case id" in capsys.readouterr().err
    write_cases(project, [base_case(held_out=True), base_case(id="b", held_out=True)])
    split = tmp_path / "s.json"
    assert main(["review-inputs", str(project / "cases.jsonl"), "--write-split", str(split)]) == 2
    assert "every case is held out" in capsys.readouterr().err


def test_grader_checks(project):
    sys.path.insert(0, str(project))
    try:
        import grader  # noqa: PLC0415
    finally:
        sys.path.remove(str(project))
    assert grader.grade({"check": "exact", "expected": "x"}, " x ")[0]
    assert grader.grade({"check": "contains", "expected": "Refund"}, "a refund")[0]
    assert not grader.grade({"check": "label", "expected": "a", "labels": ["a", "b"]}, "c")[0]
    assert grader.grade({"check": "json_keys", "expected": ["k"]}, '{"k": 1}')[0]
    assert not grader.grade({"check": "json_keys", "expected": ["k"]}, "[1]")[0]
    del sys.modules["grader"]


def test_hillclimb_on_the_scaffold_rejects_overfit_and_keeps_root_cause(project, tmp_path):
    # Iteration 1 adds a keyword that only fits the tuning outage ticket; iteration 2
    # covers outages in general, which also fixes the held-out outage ticket.
    (project / "propose.py").write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "prompt = Path('prompt.md')\n"
        "edits = {1: '- down -> oncall\\n', 2: '- down -> oncall\\n- stopped -> oncall\\n'}\n"
        "iteration = int(sys.argv[2])\n"
        "if iteration in edits:\n"
        "    prompt.write_text(prompt.read_text() + edits[iteration])\n"
    )
    config = project / "hillclimb.toml"
    config.write_text(
        config.read_text()
        .replace('"{failures}"]', '"{failures}", "{iteration}"]')
        .replace("max_iterations = 5", "max_iterations = 2")
    )
    main(["hillclimb-run", str(config), "--output", str(tmp_path / "climb"), "--trust-local"])
    state = json.loads((tmp_path / "climb/loop.json").read_text())
    assert [step["decision"] for step in state["steps"]] == ["rollback_overfit", "keep"]
    assert (project / "prompt.md").read_text().endswith("- down -> oncall\n- stopped -> oncall\n")


def test_random_split_is_stratified_and_recorded(project, tmp_path, capsys):
    cases = [base_case(id=f"p{i}", input=f"ticket {i}") for i in range(6)]
    cases += [base_case(id=f"s{i}", input=f"other {i}", source="synthetic") for i in range(3)]
    write_cases(project, cases)
    split = tmp_path / "split.json"
    args = [
        "review-inputs",
        str(project / "cases.jsonl"),
        "--random-split",
        "0.33",
        "--seed",
        "7",
        "--write-split",
        str(split),
    ]
    assert main(args) == 0
    recorded = [json.loads(line) for line in (project / "cases.jsonl").read_text().splitlines()]
    held = {c["id"] for c in recorded if c["held_out"]}
    assert held == set(json.loads(split.read_text())["held_out"])
    # Each source keeps both tuning and held-out cases.
    assert any(h.startswith("p") for h in held) and any(h.startswith("s") for h in held)
    assert len(held) == 3
    # The split is decided once: rerunning refuses to reshuffle.
    assert main(args) == 2
    assert "already declares held_out" in capsys.readouterr().err
    write_cases(project, cases)
    main(args)
    again = [json.loads(line) for line in (project / "cases.jsonl").read_text().splitlines()]
    assert {c["id"] for c in again if c["held_out"]} == held  # same seed, same split


def _grader(project):
    sys.path.insert(0, str(project))
    try:
        import grader  # noqa: PLC0415

        return grader
    finally:
        sys.path.remove(str(project))
        sys.modules.pop("grader", None)


def test_json_schema_and_command_checks(project, tmp_path):
    grader = _grader(project)
    schema = {
        "type": "object",
        "required": ["queue", "priority"],
        "properties": {
            "queue": {"enum": ["billing", "oncall"]},
            "priority": {"type": "integer", "minimum": 1, "maximum": 3},
        },
        "additionalProperties": False,
    }
    case = {"check": "json_schema", "expected": schema}
    assert grader.grade(case, '{"queue": "billing", "priority": 2}')[0]
    passed, why = grader.grade(case, '{"queue": "sales", "priority": 9, "x": 1}')
    assert not passed and "$.queue" in why and "$.priority > 3" in why
    assert not grader.grade(case, "not json")[0]
    test = tmp_path / "check.py"
    test.write_text("import sys\nsys.exit(0 if 'billing' in sys.stdin.read() else 1)\n")
    command = {"check": "command", "expected": [sys.executable, str(test)]}
    assert grader.grade(command, "queue: billing")[0]
    assert not grader.grade(command, "queue: general")[0]


@pytest.mark.parametrize(
    "case,message",
    [
        (base_case(check="json_schema", expected={"type": "tuple"}), "type must be one of"),
        (base_case(check="json_schema", expected={"pattern": "x"}), "unsupported keywords"),
        (base_case(check="json_schema", expected="x"), "non-empty JSON Schema"),
        (base_case(check="command", expected="pytest"), "argument array"),
    ],
)
def test_invalid_schema_and_command_cases(project, capsys, case, message):
    write_cases(project, [case])
    assert main(["review-inputs", str(project / "cases.jsonl")]) == 2
    assert message in capsys.readouterr().err

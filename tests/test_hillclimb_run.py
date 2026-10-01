import json
import shutil
from pathlib import Path

import pytest

from evalarc.cli import main
from evalarc.eval_health import health
from evalarc.generalization import load_split
from evalarc.hillclimb import review
from evalarc.results_diff import load_results

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/hillclimb-run"


@pytest.fixture
def example(tmp_path):
    copy = tmp_path / "example"
    shutil.copytree(EXAMPLE, copy)
    return copy


def run(example, tmp_path, name="climb", trust=True):
    args = ["hillclimb-run", str(example / "hillclimb.toml"), "--output", str(tmp_path / name)]
    return main([*args, "--trust-local"] if trust else args)


def loop(tmp_path, name="climb"):
    return json.loads((tmp_path / name / "loop.json").read_text())


def test_example_loop_decisions_and_final_workspace(example, tmp_path, capsys):
    original = (example / "workspace/rules.md").read_text()
    assert run(example, tmp_path) == 0
    printed = capsys.readouterr().out
    assert "Recommendation: merge" in printed
    state = loop(tmp_path)
    assert [step["decision"] for step in state["steps"]] == [
        "keep",
        "rollback_pasted_case",
        "rollback_overfit",
        "no_change",
        "keep",
    ]
    assert state["steps"][1]["hits"][0]["case_id"] == "t05"
    assert state["steps"][2]["stall"]["categories"] == {"never_passes": 4}
    rules = (example / "workspace/rules.md").read_text()
    assert rules == original + "route refund -> billing\nroute outage -> oncall\n"
    out = tmp_path / "climb"
    assert (out / "original/rules.md").read_text() == original
    assert "+route outage -> oncall" in (out / "final.diff").read_text()
    # The pasted-case patch and the empty proposal were never evaluated.
    assert sorted(p.name for p in (out / "results").iterdir()) == [
        "00-baseline.json",
        "01.json",
        "03.json",
        "05.json",
    ]
    final = json.loads((out / "hillclimb.json").read_text())
    assert final["recommendation"] == "merge"
    assert final["final"]["held_out"]["pass_rate"] == 1.0


def test_propose_never_sees_held_out_cases(example, tmp_path):
    assert run(example, tmp_path) == 0
    for failures in (tmp_path / "climb/steps").glob("*/tuning-failures.json"):
        text = failures.read_text()
        assert '"h0' not in text and "Ticket h0" not in text
        assert json.loads(text)["held_out_excluded"] is True


def test_review_replay_matches_loop(example, tmp_path):
    assert run(example, tmp_path) == 0
    out = tmp_path / "climb"
    runs = [load_results(p) for p in sorted((out / "results").iterdir())]
    replay = review(runs, load_split(out / "split.json"))
    assert [s["decision"] for s in replay["steps"]] == ["keep", "rollback_overfit", "keep"]
    assert (
        replay["recommendation"]
        == json.loads((out / "hillclimb.json").read_text())["recommendation"]
    )


def test_requires_trust_local(example, tmp_path, capsys):
    assert run(example, tmp_path, trust=False) == 2
    assert "--trust-local" in capsys.readouterr().err
    assert not (tmp_path / "climb").exists()


def test_changes_outside_allow_stop_the_loop(example, tmp_path, capsys):
    propose = example / "workspace/propose.py"
    propose.write_text(propose.read_text() + "\nPath('tickets.json').write_text('[]')\n")
    original = (example / "workspace/rules.md").read_text()
    assert run(example, tmp_path) == 2
    assert "outside allow" in capsys.readouterr().err
    state = loop(tmp_path)
    assert state["status"] == "failed"
    assert (example / "workspace/rules.md").read_text() == original


def test_symlinked_allowed_file_is_restored(example, tmp_path, capsys):
    propose = example / "workspace/propose.py"
    propose.write_text(
        "import os\nos.remove('rules.md')\nos.symlink('/etc/hostname', 'rules.md')\n"
    )
    original = (example / "workspace/rules.md").read_text()
    assert run(example, tmp_path) == 2
    assert "symlink" in capsys.readouterr().err
    rules = example / "workspace/rules.md"
    assert not rules.is_symlink() and rules.read_text() == original


def test_new_files_outside_allow_are_removed_and_git_is_watched(example, tmp_path, capsys):
    (example / "workspace/.git").mkdir()
    propose = example / "workspace/propose.py"
    propose.write_text("from pathlib import Path\nPath('.git/hook').write_text('x')\n")
    assert run(example, tmp_path) == 2
    err = capsys.readouterr().err
    assert ".git/hook" in err and "new files were removed" in err
    assert not (example / "workspace/.git/hook").exists()


def test_modified_files_outside_allow_are_reported(example, tmp_path, capsys):
    propose = example / "workspace/propose.py"
    propose.write_text("from pathlib import Path\nPath('tickets.json').write_text('[]')\n")
    assert run(example, tmp_path) == 2
    assert "must be restored by you" in capsys.readouterr().err


def test_held_out_text_in_a_patch_is_rolled_back(example, tmp_path):
    proposals = example / "workspace/proposals.json"
    items = json.loads(proposals.read_text())
    items[0]["append"] = "Ticket h03: login page shows a gateway timeout -> oncall"
    proposals.write_text(json.dumps(items))
    run(example, tmp_path)
    first = loop(tmp_path)["steps"][0]
    assert first["decision"] == "rollback_leakage"
    assert first["hits"][0]["case_id"] == "h03"


def test_failed_propose_is_recorded_and_restored(example, tmp_path):
    propose = example / "workspace/propose.py"
    propose.write_text(
        propose.read_text().replace(
            "print(json.dumps(", "sys.exit(3) if iteration == 1 else None\nprint(json.dumps("
        )
    )
    run(example, tmp_path)
    assert loop(tmp_path)["steps"][0]["decision"] == "propose_failed"


def test_stops_when_headroom_is_below_noise(example, tmp_path):
    config = example / "hillclimb.toml"
    config.write_text(config.read_text().replace("stall_after = 2", "stall_after = 1"))
    proposals = example / "workspace/proposals.json"
    items = json.loads(proposals.read_text())
    items[0]["append"] = None
    proposals.write_text(json.dumps(items))
    run(example, tmp_path)
    state = loop(tmp_path)
    assert state["status"] == "complete"
    assert state["status_reason"] in ("stopped_below_noise", "max_iterations")


@pytest.mark.parametrize(
    "edit,message",
    [
        (('allow = ["rules.md"]', 'allow = ["../outside.md"]'), "inside the workspace"),
        (('objective = "quality"', 'objective = "speed"'), "objective"),
        (("max_iterations = 5", "max_iterations = 0"), "max_iterations"),
        (("evaluate = [", 'evaluate = ["{nope}", '), "unknown placeholder"),
        (("timeout_seconds = 60", "timeout_seconds = 60\nshell = true"), "unknown keys"),
    ],
)
def test_invalid_configs(example, tmp_path, capsys, edit, message):
    config = example / "hillclimb.toml"
    config.write_text(config.read_text().replace(*edit))
    assert run(example, tmp_path) == 2
    assert message in capsys.readouterr().err


def test_output_inside_workspace_is_rejected(example, capsys):
    args = [
        "hillclimb-run",
        str(example / "hillclimb.toml"),
        "--output",
        str(example / "workspace/out"),
        "--trust-local",
    ]
    assert main(args) == 2
    assert "outside the workspace" in capsys.readouterr().err


# --- judge-run --------------------------------------------------------------------


def test_judge_run_end_to_end(example, tmp_path, capsys):
    assert run(example, tmp_path) == 0
    results = tmp_path / "climb/results"
    packet = tmp_path / "packet"
    assert (
        main(
            [
                "judge-packet",
                "pairwise",
                str(results / "00-baseline.json"),
                str(results / "05.json"),
                "--output",
                str(packet),
            ]
        )
        == 0
    )
    verdicts = tmp_path / "verdicts.json"
    args = ["judge-run", str(packet), "--config", str(example / "judge.toml"), "--output"]
    assert main([*args, str(verdicts)]) == 2  # no --trust-local
    assert main([*args, str(verdicts), "--trust-local"]) == 0
    recorded = json.loads(verdicts.read_text())
    assert recorded["judge"] == {
        "kind": "model",
        "model": "scripted/rule-judge",
        "description": "",
    }
    capsys.readouterr()
    assert main(["judge-score", str(packet), str(verdicts), "--require-current-preferred"]) == 0
    assert "current_preferred" in capsys.readouterr().out


def test_judge_run_rejects_bad_answers(example, tmp_path, capsys):
    run(example, tmp_path)
    packet = tmp_path / "packet"
    main(
        ["judge-packet", "grader", str(tmp_path / "climb/results/05.json"), "--output", str(packet)]
    )
    (example / "judge.py").write_text('print(\'{"verdict": "maybe"}\')\n')
    code = main(
        [
            "judge-run",
            str(packet),
            "--config",
            str(example / "judge.toml"),
            "--output",
            str(tmp_path / "v.json"),
            "--trust-local",
        ]
    )
    assert code == 2 and "answered 'maybe'" in capsys.readouterr().err
    assert not (tmp_path / "v.json").exists()


# --- programmatic grader suggestion ----------------------------------------------


def test_model_judge_replaceable_for_small_output_space(example, tmp_path):
    run(example, tmp_path)
    document = json.loads((tmp_path / "climb/results/05.json").read_text())
    document["eval"]["scorers"] = [{"name": "model_graded_qa", "options": {"model": "j/x"}}]
    for sample in document["samples"]:
        sample["scores"] = {"model_graded_qa": sample["scores"]["route"]}
    path = tmp_path / "graded.json"
    path.write_text(json.dumps(document))
    findings = {f["id"]: f for f in health([load_results(path)])["findings"]}
    assert "model_judge_replaceable" in findings
    assert findings["model_judge_replaceable"]["items"][0]["check"] == "model_graded_qa"
    # The deterministic `route` scorer is not model-graded, so no suggestion.
    plain = health([load_results(tmp_path / "climb/results/05.json")])
    assert "model_judge_replaceable" not in {f["id"] for f in plain["findings"]}


def test_judge_run_repeat_reports_consistency(example, tmp_path, capsys):
    run(example, tmp_path)
    packet = tmp_path / "packet"
    main(
        [
            "judge-packet",
            "grader",
            str(tmp_path / "climb/results/05.json"),
            "--sample",
            "6",
            "--output",
            str(packet),
        ]
    )
    # A judge that flips its answer for one item on the second round.
    judge = example / "judge.py"
    judge.write_text(
        "import json, sys, pathlib\n"
        "request = json.load(sys.stdin)\n"
        "marker = pathlib.Path(sys.argv[1]) / 'seen'\n"
        "first = request['item']['item_id'] == 'item-001'\n"
        "flip = first and marker.exists()\n"
        "if first: marker.write_text('x')\n"
        "print(json.dumps({'verdict': 'fail' if flip else 'pass'}))\n"
    )
    config = example / "judge.toml"
    config.write_text(
        config.read_text().replace(
            '"{config_dir}/judge.py"]', '"{config_dir}/judge.py", "{config_dir}"]'
        )
    )
    verdicts = tmp_path / "v.json"
    args = [
        "judge-run",
        str(packet),
        "--config",
        str(config),
        "--output",
        str(verdicts),
        "--repeat",
        "3",
        "--trust-local",
    ]
    assert main(args) == 0
    assert len(json.loads(verdicts.read_text())["repeats"]) == 3
    capsys.readouterr()
    assert main(["judge-score", str(packet), str(verdicts), "--json"]) == 0
    consistency = json.loads(capsys.readouterr().out)["judge_consistency"]
    assert consistency["rounds"] == 3 and consistency["changed_items"] == ["item-001"]
    assert consistency["stable_share"] == 5 / 6
    assert main([*args[:-3], "--repeat", "11", "--trust-local"]) == 2

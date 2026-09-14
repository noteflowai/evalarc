from pathlib import Path

import pytest

from evalarc.audit import asset, audit, write_candidate
from evalarc.cli import main
from evalarc.evaluate import evaluate
from evalarc.runner import CandidateError, Runtime, snapshot


def test_positive_and_behavioral_negative_controls():
    result = audit(Runtime(backend="local", timeout=2), [17])
    assert result["reference_passed"]
    assert result["passed"]
    assert result["killed"] == 8
    for mutant in result["mutants"]:
        assert mutant["failing_cases"], mutant["name"]


def test_a_perfect_mutation_score_still_reports_how_narrowly_it_was_earned():
    result = audit(Runtime(backend="local", timeout=2), [17])
    assert result["mutation_score"] == 1.0
    detection = result["detection"]
    # Every mutant reports how many cases caught it independently.
    for mutant in result["mutants"]:
        assert mutant["detection_margin"] == len(set(mutant["failing_cases"])), mutant["name"]
    assert detection["weakest_margin"] == min(m["detection_margin"] for m in result["mutants"])
    # This pack really does rest on single cases; a perfect score hides that.
    assert detection["single_case_detections"] == [
        "accept-nonstring-keys",
        "boolean-equals-one",
        "partial-batch",
    ]
    # Naming the sole detectors is what makes the fragility actionable: remove
    # one of these cases and its fault goes undetected at an unchanged score.
    assert detection["sole_detector_cases"] == [
        "cas-type-sensitivity",
        "reject-and-continue",
        "rollback-batch",
    ]
    assert set(detection["sole_detector_cases"]).isdisjoint(detection["single_case_detections"])


def test_margins_count_distinct_cases_so_adding_seeds_cannot_inflate_them():
    one = audit(Runtime(backend="local", timeout=4), [17])
    two = audit(Runtime(backend="local", timeout=4), [17, 41])
    # A case that fails under both seeds is still one case. Counting runs instead
    # would double every margin per added seed, so a suite would look twice as
    # robust for changing nothing.
    assert {m["name"]: m["detection_margin"] for m in one["mutants"]} == {
        m["name"]: m["detection_margin"] for m in two["mutants"]
    }
    mutant = next(m for m in two["mutants"] if m["name"] == "ack-without-work")
    runs = [
        case["case_id"]
        for case in mutant["evaluation"]["cases"]
        if case["checks"].get(mutant["target_dimension"]) is False
    ]
    # The premise of the test: the raw list really does repeat across seeds.
    assert len(runs) > len(set(runs))
    assert mutant["detection_margin"] == len(set(runs))


@pytest.mark.parametrize(
    "source,message",
    [
        ("import sys\nfor line in sys.stdin: print('NaN', flush=True)\n", "finite JSON"),
        ("import sys\nfor line in sys.stdin: print('1e999', flush=True)\n", "finite JSON"),
        ("import time\ntime.sleep(10)\n", "timeout"),
        ("print('x' * 65536, flush=True)\n", "output limit"),
        ("print('not JSON', flush=True)\n", "finite JSON"),
    ],
)
def test_protocol_failures_are_bounded(tmp_path, source, message):
    workspace = write_candidate(tmp_path / "candidate", source)
    state = tmp_path / "state"
    state.mkdir()
    runtime = Runtime(backend="local", timeout=0.2, output_limit=8192)
    with runtime.start(workspace, state) as process:
        with pytest.raises(CandidateError, match=message):
            process.request({"op": "get", "key": "x"})
    assert process.proc.poll() is not None


def test_stderr_flood_cannot_deadlock(tmp_path):
    source = (
        "import sys\n"
        "for line in sys.stdin:\n"
        "    sys.stderr.write('x' * 100000)\n"
        "    sys.stderr.flush()\n"
    )
    workspace = write_candidate(tmp_path / "candidate", source)
    state = tmp_path / "state"
    state.mkdir()
    with Runtime(backend="local", timeout=1, output_limit=4096).start(workspace, state) as process:
        with pytest.raises(CandidateError, match="output limit"):
            process.request({})


def test_extra_stdout_rejected_at_eof(tmp_path):
    source = (
        "import sys\n"
        "for line in sys.stdin: print('{\"ok\":true}', flush=True)\n"
        "print('{\"score\":1.0}', flush=True)\n"
    )
    workspace = write_candidate(tmp_path / "candidate", source)
    state = tmp_path / "state"
    state.mkdir()
    with Runtime(backend="local", timeout=1).start(workspace, state) as process:
        assert process.request({}) == {"ok": True}
        with pytest.raises(CandidateError, match="unsolicited"):
            process.finish("eof")


def test_snapshot_is_exact_and_rejects_symlinks(tmp_path):
    source = write_candidate(tmp_path / "source", asset("starter.py"))
    first = snapshot(source, tmp_path / "copy1")
    assert first == snapshot(source, tmp_path / "copy2")
    (source / "main.py").write_text("print('changed')\n")
    assert first != snapshot(source, tmp_path / "copy3")
    (source / "external").symlink_to(Path("/etc/passwd"))
    with pytest.raises(ValueError, match="symlinks"):
        snapshot(source, tmp_path / "copy4")


def test_self_reported_score_has_no_authority(tmp_path):
    workspace = write_candidate(
        tmp_path / "forgery",
        "import sys\nfor line in sys.stdin: print('{\"score\":1.0}', flush=True)\n",
    )
    result = evaluate(workspace, Runtime(backend="local", timeout=1), [41])
    assert result["score"] == 0
    assert not result["resolved"]
    assert result["agent_cost_usd"] is None


def test_local_execution_requires_explicit_trust(tmp_path):
    assert main(["audit", "--backend", "local", "--output", str(tmp_path)]) == 2


def test_init_never_overwrites_existing_workspace(tmp_path):
    assert main(["init", str(tmp_path / "candidate")]) == 0
    initial = (tmp_path / "candidate" / "main.py").read_text()
    assert main(["init", str(tmp_path / "candidate"), "--reference"]) == 2
    assert (tmp_path / "candidate" / "main.py").read_text() == initial


def test_duplicate_seeds_rejected(tmp_path):
    workspace = write_candidate(tmp_path / "candidate", asset("reference.py"))
    with pytest.raises(ValueError, match="repeat"):
        evaluate(workspace, Runtime(backend="local"), [17, 17])

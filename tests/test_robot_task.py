import copy
import hashlib
import json
from dataclasses import replace

import pytest

from evalarc.audit import audit, write_candidate
from evalarc.evaluate import evaluate, write_json
from evalarc.robot_task import expected, generate_cases, recordings, verify
from evalarc.runner import CandidateError, EnvironmentFailure, Runtime
from evalarc.templates import initialize
from evalarc.verify import verify as verify_saved


def test_preserved_recordings_and_known_experiment_errors():
    data = recordings()
    assert len(data["records"]) == 6
    known = {1: 0.32700288772800196, 4: 0.08173490053331378, 16: 0.02046407548115492}
    seen = set()
    for seed in range(40):
        case = generate_cases(seed)[0]
        name = case.request["recording"]["source"]["path"].split("/")[-1][:-5]
        entry = data["records"][name]
        assert hashlib.sha256(entry["raw_json"].encode()).hexdigest() == entry["sha256"]
        source = json.loads(entry["raw_json"])
        assert len(source["frames"]) == 61
        assert expected(case)["max_position_error_m"] == pytest.approx(
            known[source["substeps"]], abs=1e-12
        )
        assert source["source"]["device"] == "cuda:0"
        seen.add(name)
    assert seen == set(data["records"])


def test_variants_share_source_facts_without_inventing_observations():
    cases = generate_cases(41)
    assert len(cases) == 4
    assert len({case.source_sha256 for case in cases}) == 1
    assert cases[-1].missing == [8, 43]
    assert len(cases[-1].original) == 59
    for case in cases:
        report = expected(case)
        assert all(verify(case, report, True).values())
        assert report["frame"] == cases[0].query_frame
        assert report["position_m"] == expected(cases[0])["position_m"]
    # Millisecond timestamps and permuted sensor components are actually present.
    transformed = cases[1].request["recording"]
    assert min(row["tick"] for row in transformed["observations"]) == 1_000_000
    assert transformed["metadata"]["world_from_sensor"]["axes"] == [2, 0, 1]
    assert transformed["observations"] != cases[0].request["recording"]["observations"]


def test_python_reference_and_each_fault_are_exercised():
    result = audit(Runtime(backend="local", timeout=2), [17, 41], "robot-evidence-review")
    assert result["passed"] and result["valid"]
    assert result["total"] == result["killed"] == 6
    assert result["reference"]["resolved"]
    assert all(row["failing_cases"] for row in result["mutants"])
    incomplete = next(row for row in result["mutants"] if row["name"] == "assume-complete")
    assert incomplete["failing_cases"] == ["incomplete-recording"]
    assert incomplete["score"] > 0.9
    assert not incomplete["evaluation"]["resolved"]


@pytest.mark.parametrize("bad", [True, None, "0.5", float("nan"), float("inf"), 10**1000])
def test_invalid_numeric_claims_cannot_crash_or_pass_grader(bad):
    case = generate_cases(17)[0]
    result = expected(case)
    result["time_seconds"] = bad
    assert verify(case, result, True)["clock"] is False
    result["position_m"][0] = bad
    assert verify(case, result, True)["coordinates"] is False


def test_missing_frames_cannot_be_boolean_aliases_or_reordered():
    case = generate_cases(97)[3]
    result = expected(case)
    for bad in [[43, 8], [], [8, True], {"8": True}]:
        result["missing_frames"] = bad
        assert verify(case, result, True)["completeness"] is False


def test_report_protocol_and_source_are_separate_from_numeric_facts():
    case = generate_cases(17)[0]
    result = copy.deepcopy(expected(case))
    result["source_sha256"] = "0" * 64
    checks = verify(case, result, True)
    assert checks["provenance"] is False
    assert all(value for key, value in checks.items() if key != "provenance")
    result["score"] = 1.0
    assert verify(case, result, True)["protocol"] is False
    assert not any(verify(case, None, False).values())


def test_source_oracle_does_not_reuse_the_candidates_frame_conversion():
    case = generate_cases(17)[1]
    changed = copy.deepcopy(case.request)
    changed["recording"]["observations"][0]["position"] = [1e8, 1e8, 1e8]
    # Expected values remain anchored to the original measured states, not an
    # accidental reapplication of the same candidate-side transform.
    assert expected(replace(case, request=changed)) == expected(case)


def test_candidate_self_reported_success_is_not_evidence(tmp_path):
    candidate = write_candidate(
        tmp_path / "candidate",
        "import sys\nfor line in sys.stdin: print("
        '\'{"ok":true,"report":{"score":1,"resolved":true}}\', flush=True)\n',
    )
    result = evaluate(candidate, Runtime(backend="local"), [17], "robot-evidence-review")
    assert result["valid"] and result["score"] == 0 and not result["resolved"]


def test_new_task_reports_are_independently_readable_and_tamper_checked(tmp_path):
    candidate = tmp_path / "reference"
    initialize(candidate, "robot-evidence-review", reference=True)
    result = evaluate(candidate, Runtime(backend="local"), [41], "robot-evidence-review")
    report = tmp_path / "evaluation.json"
    write_json(report, result)
    checked = verify_saved(report)
    assert checked["verified"] and checked["records_valid"] and checked["fully_resolved"]
    result["score"] = 0.5
    write_json(report, result)
    with pytest.raises(ValueError):
        verify_saved(report)


def test_environment_failure_remains_unassessed(tmp_path, monkeypatch):
    def unavailable(*args, **kwargs):
        raise EnvironmentFailure("sandbox unavailable")

    candidate = tmp_path / "reference"
    initialize(candidate, "robot-evidence-review", reference=True)
    monkeypatch.setattr(Runtime, "start", unavailable)
    result = evaluate(candidate, Runtime(backend="local"), [17], "robot-evidence-review")
    assert result["valid"] is False and result["score"] is None
    assert all(row["status"] == "environment_error" for row in result["cases"])
    assert all(value is None for row in result["cases"] for value in row["checks"].values())


def test_large_review_input_obeys_the_task_bound_and_stdin_deadline(tmp_path):
    candidate = write_candidate(tmp_path / "candidate", "import time\ntime.sleep(30)\n")
    state = tmp_path / "state"
    state.mkdir()
    case = generate_cases(17)[1]
    assert 8192 < len(json.dumps(case.request).encode()) < 65_536
    with Runtime(backend="local", timeout=0.15, request_limit=65_536).start(
        candidate, state
    ) as process:
        with pytest.raises(CandidateError, match="timeout"):
            process.request({"data": "x" * 60_000})
    with Runtime(backend="local", timeout=1).start(candidate, state) as process:
        with pytest.raises(ValueError, match="8 KiB"):
            process.request(case.request)

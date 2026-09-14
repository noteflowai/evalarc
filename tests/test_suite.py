import copy
import hashlib
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from evalarc.audit import CONTROL_PACKS, asset, mutate, write_candidate
from evalarc.cli import main
from evalarc.junit import render_junit
from evalarc.repetition import summarize_attempts
from evalarc.suite import Gate, assess_gate, load_suite, run_suite
from evalarc.verify import verify


def job(identity, candidate, task="support-routing", *, extra="", backend="local", attempts=1):
    return (
        "\n[[jobs]]\n"
        f"id = {json.dumps(identity)}\ntask = {json.dumps(task)}\n"
        f"candidate = {json.dumps(str(candidate))}\nseeds = [17]\nattempts = {attempts}\n"
        f"[jobs.runtime]\nbackend = {json.dumps(backend)}\n" + extra
    )


def config(directory, entries, name="Acceptance suite"):
    path = directory / "suite.toml"
    path.write_text(
        f'schema_version = "evalarc.suite-config.v1"\nname = {json.dumps(name)}\n'
        + "".join(entries)
    )
    return path


@pytest.fixture
def reference(tmp_path):
    return write_candidate(tmp_path / "candidate", asset("support_reference.py"))


@pytest.fixture
def observations():
    audit = json.loads(
        (Path(__file__).resolve().parents[1] / "examples/support-audit/audit.json").read_text()
    )
    # Deliberately synthetic repetitions for gate arithmetic, not model evidence.
    good = audit["reference"]
    bad = next(row["evaluation"] for row in audit["mutants"] if row["name"] == "new-key-on-retry")
    bad["candidate_sha256"] = good["candidate_sha256"]
    return [good, bad]


def test_default_gate_never_accepts_best_attempt_only(observations):
    summary = summarize_attempts(observations)
    decision = assess_gate(summary, Gate())
    assert decision["valid"] and not decision["accepted"]
    assert [row["passed"] for row in decision["checks"]] == [False, False]
    assert decision["checks"][0]["observed"] == (1 + 0.9375) / 2


def test_partial_gate_is_explicit_and_required_dimensions_override_average(observations):
    summary = summarize_attempts(observations)
    assert assess_gate(summary, Gate(0.96, 0.5))["accepted"]
    assert not summary["all_attempts_resolved"]
    decision = assess_gate(summary, Gate(0.9, 0, ("notes",)))
    assert not decision["accepted"]
    assert decision["checks"][-1]["violations"][0]["case_id"] == "retry-after-commit"
    assert assess_gate(summary, Gate(0.9, 0, ("scope",)))["accepted"]


def test_incomplete_attempts_cannot_pass_even_zero_thresholds(observations):
    summary = summarize_attempts([observations[0]], requested_attempts=3)
    result = assess_gate(summary, Gate(0, 0))
    assert not result["valid"] and not result["accepted"]
    assert "1/3" in result["reasons"][0]


def test_manifest_defaults_are_strict_and_paths_are_relative_to_config(
    tmp_path, reference, monkeypatch
):
    path = config(tmp_path, [job("reference", "candidate")])
    monkeypatch.chdir("/")
    plan = load_suite(path)
    assert plan.jobs[0].candidate == reference
    assert plan.jobs[0].gate == Gate()
    assert plan.describe()["planned_case_executions"] == 4
    assert plan.describe()["manifest_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("identity", ["../escape", "same/name", "Upper", ".hidden", "", "a" * 65])
def test_invalid_job_names_cannot_become_output_paths(tmp_path, reference, identity):
    path = config(tmp_path, [job(identity, reference)])
    with pytest.raises(ValueError, match="unique lowercase slug"):
        load_suite(path)


def test_duplicate_ids_rejected_even_across_tasks(tmp_path, reference):
    path = config(tmp_path, [job("same", reference), job("same", reference, "durable-kv")])
    with pytest.raises(ValueError, match="unique"):
        load_suite(path)


@pytest.mark.parametrize(
    "before,after",
    [
        ('name = "Acceptance suite"', 'name = "Acceptance suite"\nunknown = true'),
        ('id = "policy"', 'id = "policy"\nunknown = 1'),
        ('task = "support-routing"', 'task = "nonexistent"'),
        ("seeds = [17]", "seeds = [17, 17]"),
        ("seeds = [17]", "seeds = [true]"),
        ("seeds = [17]", "seeds = []"),
        ("attempts = 1", "attempts = true"),
        ("attempts = 1", "attempts = 0"),
        ("attempts = 1", "attempts = 101"),
        ('backend = "local"', 'backend = "local"\ntrust_local = true'),
        ('backend = "local"', 'backend = "local"\ndocker_command = "custom-wrapper"'),
        ('backend = "local"', 'backend = "local"\ncase_timeout = nan'),
        ('backend = "local"', 'backend = "local"\ntimeout = true'),
        ('backend = "local"', 'backend = "local"\noutput_limit = 1.5'),
        ('backend = "local"', 'backend = "unknown"'),
        ('backend = "local"', 'backend = "local"\nimage = 42'),
    ],
)
def test_bad_config_rejected_before_execution(tmp_path, reference, before, after):
    path = config(tmp_path, [job("policy", reference)])
    path.write_text(path.read_text().replace(before, after))
    with pytest.raises(ValueError):
        load_suite(path)


@pytest.mark.parametrize(
    "rule",
    [
        "min_mean_score = nan",
        "min_mean_score = true",
        "min_resolution_rate = 1.1",
        "min_resolution_rate = -0.1",
        'required_dimensions = ["persistence"]',
        'required_dimensions = ["scope", "scope"]',
        'required_dimensions = "scope"',
        "min_score = 0.5",
    ],
)
def test_bad_gate_is_never_silently_ignored(tmp_path, reference, rule):
    path = config(tmp_path, [job("policy", reference, extra="[jobs.gate]\n" + rule)])
    with pytest.raises(ValueError):
        load_suite(path)


def test_suite_bounds_prevent_accidental_large_runs(tmp_path, reference):
    path = config(tmp_path, [job(f"job-{index}", reference, attempts=100) for index in range(11)])
    with pytest.raises(ValueError, match="1000 attempts"):
        load_suite(path)
    path.write_bytes(b"x" * 1_048_577)
    with pytest.raises(ValueError, match="1 MiB"):
        load_suite(path)


def test_dry_run_does_not_execute_or_contact_docker(tmp_path, reference, monkeypatch, capsys):
    import subprocess

    def forbidden(*args, **kwargs):
        pytest.fail("dry run must not start a process")

    path = config(tmp_path, [job("policy", reference, backend="docker", attempts=2)])
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    output = tmp_path / "dry-run"
    assert main(["suite", str(path), "--dry-run", "--output", str(output)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["planned_attempts"] == 2 and plan["planned_case_executions"] == 8
    assert not output.exists()


def test_planning_never_opens_candidate_files_and_preflight_rejects_fifo(
    tmp_path, reference, monkeypatch
):
    manifest = reference / "evalarc.toml"
    os.mkfifo(manifest)
    original_open = Path.open

    def guarded_open(self, *args, **kwargs):
        if self == manifest:
            pytest.fail("candidate FIFO must never be opened during planning")
        return original_open(self, *args, **kwargs)

    path = config(tmp_path, [job("policy", reference)])
    monkeypatch.setattr(Path, "open", guarded_open)
    plan = load_suite(path)
    assert plan.describe()["planned_case_executions"] == 4
    with pytest.raises(ValueError, match="non-regular"):
        run_suite(plan, tmp_path / "output", trust_local=True)
    assert not (tmp_path / "output").exists()


def test_local_suite_requires_explicit_cli_trust(tmp_path, reference):
    path = config(tmp_path, [job("policy", reference)])
    output = tmp_path / "output"
    assert main(["suite", str(path), "--output", str(output)]) == 2
    assert not output.exists()


def test_every_candidate_is_checked_before_any_execution(tmp_path, reference, monkeypatch):
    import evalarc.suite

    invalid = write_candidate(tmp_path / "invalid", asset("support_reference.py"))
    path = config(tmp_path, [job("first", reference), job("last", invalid)])
    plan = load_suite(path)
    # A config that changed after planning is checked again in its frozen copy.
    (invalid / "evalarc.toml").write_text("command = []\n")

    def forbidden(*args, **kwargs):
        pytest.fail("no candidate should execute before preflight finishes")

    monkeypatch.setattr(evalarc.suite, "repeat", forbidden)
    with pytest.raises(ValueError, match="command"):
        run_suite(plan, tmp_path / "output", trust_local=True)
    assert not (tmp_path / "output").exists()


def test_all_candidates_frozen_before_first_job_and_shared_input_is_reused(tmp_path, reference):
    later = write_candidate(tmp_path / "later", asset("support_reference.py"))
    path = config(
        tmp_path,
        [
            job("first", reference),
            job("second", later),
            job("same-source", later),
        ],
    )
    events = []

    def change_original(event):
        events.append(event)
        if event["event"] == "job_started" and event["job"] == "first":
            (later / "main.py").write_text("raise SystemExit(99)\n")
            path.write_text("manifest changed after loading\n")

    original = path.read_bytes()
    result = run_suite(
        load_suite(path),
        tmp_path / "output",
        trust_local=True,
        on_event=change_original,
    )
    assert result["accepted"] and result["fully_resolved_jobs"] == 3
    assert result["jobs"][1]["candidate_sha256"] == result["jobs"][2]["candidate_sha256"]
    assert (tmp_path / "output/suite.toml").read_bytes() == original
    prepared = [i for i, event in enumerate(events) if event["event"] == "job_prepared"]
    first_start = next(i for i, event in enumerate(events) if event["event"] == "job_started")
    assert len(prepared) == 3 and max(prepared) < first_start


def test_mixed_domain_suite_writes_complete_evidence_and_matching_progress(
    tmp_path, reference, capsys
):
    coding = write_candidate(tmp_path / "coding", asset("reference.py"))
    path = config(
        tmp_path,
        [
            job("coding", coding, "durable-kv"),
            job("support", reference, attempts=2),
        ],
    )
    output = tmp_path / "output"
    assert (
        main(
            [
                "suite",
                str(path),
                "--trust-local",
                "--progress",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    stream = capsys.readouterr().err
    assert stream == (output / "events.jsonl").read_text()
    events = [json.loads(line) for line in stream.splitlines()]
    assert events[-1]["event"] == "suite_completed"
    assert {e["job"] for e in events if e["event"] == "case_started"} == {"coding", "support"}
    data = json.loads((output / "suite.json").read_text())
    assert data["accepted_jobs"] == data["fully_resolved_jobs"] == 2
    assert "score" not in data and "mean_score" not in data
    assert (output / "jobs/support/attempts/0002/evaluation.json").exists()
    assert "jobs/coding/index.html" in (output / "index.html").read_text()
    xml = ET.parse(output / "junit.xml").getroot()
    assert xml.attrib["tests"] == "2" and xml.attrib["failures"] == xml.attrib["errors"] == "0"
    assert {case.attrib["classname"] for case in xml.findall(".//testcase")} == {
        "evalarc.durable-kv",
        "evalarc.support-routing",
    }
    assert verify(output)["accepted"]


def test_invalid_job_does_not_hide_later_jobs_and_junit_errors_are_distinct(tmp_path, reference):
    broken = tmp_path / "missing-runtime"
    broken.mkdir()
    (broken / "evalarc.toml").write_text('command = ["evalarc-no-such-runtime"]\n')
    failed = write_candidate(tmp_path / "failed", "raise SystemExit(7)\n")
    path = config(
        tmp_path,
        [
            job("invalid", broken, attempts=3),
            job("failed", failed),
            job("passing", reference),
        ],
    )
    output = tmp_path / "output"
    assert main(["suite", str(path), "--trust-local", "--output", str(output)]) == 2
    data = json.loads((output / "suite.json").read_text())
    assert data["accepted_jobs"] == data["invalid_jobs"] == 1
    assert [row["status"] for row in data["jobs"]] == ["environment_error", "failed", "passed"]
    assert data["jobs"][0]["observed"]["completed_attempts"] == 1
    xml = ET.parse(output / "junit.xml").getroot()
    assert xml.attrib["tests"] == "3" and xml.attrib["failures"] == xml.attrib["errors"] == "1"
    assert xml.find(".//testcase[@name='invalid']/error") is not None
    assert xml.find(".//testcase[@name='failed']/failure") is not None
    assert xml.find(".//testcase[@name='passing']/failure") is None
    checked = verify(output)
    assert checked["verified"] and not checked["records_valid"]
    assert main(["verify", str(output), "--require-accepted"]) == 2


def test_permissive_acceptance_still_exposes_unresolved_outcomes(tmp_path):
    old, new, _ = CONTROL_PACKS["support-routing"]["new-key-on-retry"]
    candidate = write_candidate(
        tmp_path / "candidate", mutate(asset("support_reference.py"), old, new)
    )
    gate = "[jobs.gate]\nmin_mean_score = 0.9\nmin_resolution_rate = 0\n"
    path = config(tmp_path, [job("policy", candidate, extra=gate)])
    output = tmp_path / "output"
    assert main(["suite", str(path), "--trust-local", "--output", str(output)]) == 0
    data = json.loads((output / "suite.json").read_text())
    assert data["accepted"] and data["fully_resolved_jobs"] == 0
    assert "Gate accepted with unresolved task outcomes" in (output / "index.html").read_text()
    assert ET.parse(output / "junit.xml").getroot().attrib["failures"] == "0"
    checked = verify(output)
    assert checked["accepted"] and not checked["fully_resolved"]
    assert main(["verify", str(output), "--require-accepted"]) == 0
    assert main(["verify", str(output), "--require-resolved"]) == 1
    path.write_text(path.read_text() + 'required_dimensions = ["notes"]\n')
    assert (
        main(
            [
                "suite",
                str(path),
                "--trust-local",
                "--output",
                str(tmp_path / "strict"),
            ]
        )
        == 1
    )


def test_output_cannot_contaminate_any_candidate_or_replace_old_runs(tmp_path, reference):
    second = write_candidate(tmp_path / "second", asset("support_reference.py"))
    path = config(tmp_path, [job("first", reference), job("second", second)])
    plan = load_suite(path)
    with pytest.raises(ValueError, match="outside"):
        run_suite(plan, second / "results", trust_local=True)
    output = tmp_path / "existing"
    output.mkdir()
    (output / "keep").write_text("preserve")
    with pytest.raises(ValueError, match="already exists"):
        run_suite(plan, output, trust_local=True)
    assert (output / "keep").read_text() == "preserve"


def test_suite_cancelled_during_job_is_not_published(tmp_path, reference, monkeypatch, capsys):
    import evalarc.suite

    path = config(tmp_path, [job("policy", reference)])

    def cancel(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(evalarc.suite, "repeat", cancel)
    output = tmp_path / "cancelled"
    assert (
        main(
            [
                "suite",
                str(path),
                "--trust-local",
                "--progress",
                "--output",
                str(output),
            ]
        )
        == 130
    )
    assert not output.exists()
    events = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    assert events[-1]["event"] == "run_cancelled"


def test_html_and_xml_escape_text_and_junit_removes_xml_control_characters(tmp_path, reference):
    path = config(tmp_path, [job("policy", reference)], name='<script>alert("suite")</script>')
    output = tmp_path / "output"
    data = run_suite(load_suite(path), output, trust_local=True)
    assert "<script>" not in (output / "index.html").read_text()
    assert "&lt;script&gt;" in (output / "index.html").read_text()
    changed = copy.deepcopy(data)
    changed["jobs"][0]["decision"].update(accepted=False, reasons=["broken\x00\x01 <message>"])
    render_junit(changed, tmp_path / "escaped.xml")
    root = ET.parse(tmp_path / "escaped.xml").getroot()
    assert root.find(".//failure").text == "broken\ufffd\ufffd <message>"

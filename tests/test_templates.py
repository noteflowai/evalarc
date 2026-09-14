import json
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from evalarc.audit import asset, audit
from evalarc.cli import main
from evalarc.evaluate import evaluate
from evalarc.runner import CandidateError, Runtime
from evalarc.suite import load_suite
from evalarc.tasks import TASKS, get_task
from evalarc.templates import CandidateTemplate, candidate_template, initialize


@pytest.fixture(scope="module")
def node():
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node.js 22+ required for JavaScript integration tests")
    version = subprocess.run(
        [executable, "-p", "process.versions.node"], capture_output=True, text=True, check=True
    ).stdout.strip()
    if int(version.split(".")[0]) < 22:
        pytest.skip("Node.js 22+ required for JSON numeric source text access")
    return str(Path(executable).resolve())


def javascript_workspace(path, node, task_id="durable-kv", *, reference=True):
    initialize(path, task_id, "javascript", reference=reference)
    manifest = path / "evalarc.toml"
    command = tomllib.loads(manifest.read_text())["command"]
    command[0] = node
    manifest.write_text(f"command = {json.dumps(command)}\n")
    return path


@pytest.mark.parametrize("task_id", TASKS)
@pytest.mark.parametrize("reference", [False, True])
def test_default_python_template_keeps_original_bytes(tmp_path, task_id, reference):
    destination = tmp_path / "python"
    initialize(destination, task_id, reference=reference)
    task = get_task(task_id)
    assert sorted(p.name for p in destination.iterdir()) == ["TASK.md", "main.py"]
    assert (destination / "main.py").read_text() == asset(
        task.reference_asset if reference else task.starter_asset
    )
    assert (destination / "TASK.md").read_text() == asset(task.contract_asset)


@pytest.mark.parametrize("task_id", TASKS)
def test_javascript_init_is_portable_and_needs_no_installed_runtime(tmp_path, monkeypatch, task_id):
    monkeypatch.setenv("PATH", "")
    destination = tmp_path / "js"
    assert main(["init", str(destination), "--task", task_id, "--language", "javascript"]) == 0
    assert (destination / "main.js").is_file()
    assert (destination / "TASK.md").read_text() == asset(get_task(task_id).contract_asset)
    assert (destination / "RUNTIME.md").is_file()
    command = tomllib.loads((destination / "evalarc.toml").read_text())["command"]
    assert command[:2] == ["node", "main.js"]
    assert command[2:] == (["{state}/store.json"] if task_id == "durable-kv" else [])


def test_failed_init_removes_partial_workspace(tmp_path, monkeypatch):
    def fail(self, path, **kwargs):
        (path / self.filename).write_text("partial")
        raise OSError("simulated disk failure")

    monkeypatch.setattr(CandidateTemplate, "write", fail)
    destination = tmp_path / "candidate"
    with pytest.raises(OSError, match="simulated"):
        initialize(destination, "durable-kv", "javascript")
    assert list(tmp_path.iterdir()) == []


def test_init_refuses_existing_directory_and_dangling_symlink(tmp_path):
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "keep.txt").write_text("user work")
    with pytest.raises(ValueError, match="already exists"):
        initialize(existing, "durable-kv", "javascript")
    assert list(existing.iterdir()) == [existing / "keep.txt"]
    dangling = tmp_path / "dangling"
    dangling.symlink_to(tmp_path / "absent")
    with pytest.raises(ValueError, match="already exists"):
        initialize(dangling, "durable-kv")
    assert dangling.is_symlink()
    assert not (tmp_path / "absent").exists()


def test_invalid_template_selection_does_not_create_workspace(tmp_path):
    for task, language in [("unknown", "python"), ("durable-kv", "rust")]:
        with pytest.raises(ValueError, match="unknown"):
            initialize(tmp_path / "candidate", task, language)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("task_id", TASKS)
def test_javascript_references_and_all_declared_faults(node, task_id):
    events = []
    result = audit(
        Runtime(backend="local", timeout=3),
        [17],
        task_id,
        language="javascript",
        on_event=events.append,
    )
    assert result["valid"] and result["passed"]
    assert result["killed"] == result["total"] == (8 if task_id == "durable-kv" else 7)
    assert all(row["failing_cases"] for row in result["mutants"])
    assert result["reference"]["runtime"]["command"][0] == node
    assert {event["control"] for event in events} == {
        "reference",
        *(row["name"] for row in result["mutants"]),
    }


@pytest.mark.parametrize("task_id", TASKS)
@pytest.mark.parametrize("reference", [False, True])
def test_generated_javascript_candidates_use_unchanged_grader(tmp_path, node, task_id, reference):
    candidate = javascript_workspace(tmp_path / "candidate", node, task_id, reference=reference)
    result = evaluate(candidate, Runtime(backend="local", timeout=3), [41, 97], task_id)
    assert result["valid"]
    assert result["resolved"] is reference
    assert all(case["passed"] is reference for case in result["cases"])


def test_missing_local_node_fails_before_any_audit_execution(monkeypatch):
    import evalarc.audit as module

    def unexpected(*args, **kwargs):
        pytest.fail("Missing Node must fail before control execution")

    monkeypatch.setattr(module.shutil, "which", lambda _: None)
    monkeypatch.setattr(module, "evaluate", unexpected)
    with pytest.raises(ValueError, match="Node.js 22"):
        audit(Runtime(backend="local"), [17], language="javascript")


@pytest.mark.parametrize(
    "stored,expected,matches",
    [
        (9007199254740993, 9007199254740992, False),
        (10**100 + 1, 10**100 + 1, True),
        (1, 1.0, False),
        (True, 1, False),
        (-0.0, 0.0, False),
        (-0.0, -0.0, True),
        (1e-300, 1e-300, True),
        ([{"b": [1, False], "a": 1.0}], [{"a": 1.0, "b": [1, False]}], True),
        ({"__proto__": 1, "constructor": [False]}, {"constructor": [0], "__proto__": 1}, False),
        (
            {"2": "two", "1": "one", "\U00010000": 1, "\ue000": 2},
            {"\ue000": 2, "\U00010000": 1, "1": "one", "2": "two"},
            True,
        ),
        (
            {"value": 42, "source": "9", "decimal": False},
            {"value": 42, "source": "9", "decimal": False},
            True,
        ),
    ],
)
def test_javascript_value_semantics_survive_sigkill(tmp_path, node, stored, expected, matches):
    candidate = javascript_workspace(tmp_path / "candidate", node)
    state = tmp_path / "state"
    state.mkdir()
    runtime = Runtime(backend="local", timeout=3).for_candidate(
        candidate, get_task("durable-kv").default_command
    )
    with runtime.start(candidate, state) as process:
        assert process.request({"op": "put", "key": "__proto__", "value": stored}) == {"ok": True}
        process.finish("kill")
    with runtime.start(candidate, state) as process:
        response = process.request({"op": "get", "key": "__proto__"})
        # Canonical Python serialization preserves both numeric category and sign.
        assert json.dumps(response["value"], sort_keys=True) == json.dumps(stored, sort_keys=True)
        assert process.request(
            {"op": "cas", "key": "__proto__", "expected": expected, "value": "replaced"}
        ) == {"ok": True, "swapped": matches}
        process.finish("kill")
    with runtime.start(candidate, state) as process:
        response = process.request({"op": "get", "key": "__proto__"})
        assert json.dumps(response["value"], sort_keys=True) == json.dumps(
            "replaced" if matches else stored, sort_keys=True
        )
        process.finish("eof")


def test_javascript_invalid_batch_and_special_keys_preserve_state(tmp_path, node):
    candidate = javascript_workspace(tmp_path / "candidate", node)
    state = tmp_path / "state"
    state.mkdir()
    runtime = Runtime(backend="local").for_candidate(
        candidate, get_task("durable-kv").default_command
    )
    keys = ["", "__proto__", "constructor", "toString", "hasOwnProperty", "键🔑", "\ud800"]
    with runtime.start(candidate, state) as process:
        assert process.request(
            {"op": "batch", "operations": [{"op": "put", "key": key, "value": key} for key in keys]}
        ) == {"ok": True}
        for invalid in [
            None,
            [],
            True,
            1,
            {"op": "put", "key": "__proto__"},
            {"op": "get", "key": False},
            {"op": "get", "key": []},
            {
                "op": "batch",
                "operations": [
                    {"op": "delete", "key": "__proto__"},
                    {"op": "batch", "operations": []},
                ],
            },
        ]:
            assert process.request(invalid) == {"ok": False, "error": "invalid_request"}
        process.finish("kill")
    with runtime.start(candidate, state) as process:
        for key in keys:
            assert process.request({"op": "get", "key": key}) == {
                "ok": True,
                "found": True,
                "value": key,
            }
        process.finish("eof")


def test_javascript_cannot_acknowledge_failed_persistence(tmp_path, node):
    candidate = javascript_workspace(tmp_path / "candidate", node)
    state = tmp_path / "state"
    state.mkdir()
    # A directory where the pending file must be written forces a deterministic
    # storage error even if the tests are running with elevated permissions.
    (state / "store.json.pending").mkdir()
    runtime = Runtime(backend="local").for_candidate(
        candidate, get_task("durable-kv").default_command
    )
    with runtime.start(candidate, state) as process:
        with pytest.raises(CandidateError, match="exited"):
            process.request({"op": "put", "key": "x", "value": "must not be acknowledged"})
    assert not (state / "store.json").exists()


def test_javascript_corrupt_snapshot_is_not_reset(tmp_path, node):
    candidate = javascript_workspace(tmp_path / "candidate", node)
    state = tmp_path / "state"
    state.mkdir()
    (state / "store.json").write_text('[["duplicate",1],["duplicate",2]]')
    runtime = Runtime(backend="local").for_candidate(
        candidate, get_task("durable-kv").default_command
    )
    with runtime.start(candidate, state) as process:
        with pytest.raises(CandidateError, match="exited"):
            process.request({"op": "get", "key": "duplicate"})
    assert (state / "store.json").read_text() == '[["duplicate",1],["duplicate",2]]'


def test_javascript_raw_numeric_lexemes_and_malformed_lines(tmp_path, node):
    candidate = javascript_workspace(tmp_path / "candidate", node)
    lines = [
        '{"op":"put","key":"x","value":1e0}',
        '{"op":"cas","key":"x","expected":1.00,"value":-0}',
        '{"op":"cas","key":"x","expected":0,"value":-1e-999}',
        '{"op":"cas","key":"x","expected":0.0,"value":"incorrect"}',
        '{"op":"cas","key":"x","expected":-0e99,"value":"correct"}',
        '{"op":"put","key":"x","value":1e999}',
        "not JSON",
        '{"op":"get","key":"x"}',
    ]
    result = subprocess.run(
        [node, str(candidate / "main.js"), str(tmp_path / "store.json")],
        input="\n".join(lines) + "\n",
        text=True,
        capture_output=True,
        timeout=10,
        check=True,
    )
    assert [json.loads(line) for line in result.stdout.splitlines()] == [
        {"ok": True},
        {"ok": True, "swapped": True},  # equivalent floating spellings
        {"ok": True, "swapped": True},  # integer negative zero equals zero
        {"ok": True, "swapped": False},  # negative underflow retains its sign
        {"ok": True, "swapped": True},  # equivalent negative floating zeros
        {"ok": False, "error": "invalid_request"},
        {"ok": False, "error": "invalid_request"},
        {"ok": True, "found": True, "value": "correct"},
    ]


def test_audit_image_is_explicit_and_python_default_is_unchanged():
    from evalarc.cli import parser

    args = parser().parse_args(["audit", "--language", "javascript"])
    assert args.image == "python:3.12-slim"
    assert candidate_template("durable-kv").command is None


def test_documented_multilanguage_suite_uses_each_jobs_runtime(tmp_path):
    source = Path(__file__).resolve().parents[1] / "examples/multilanguage/suite.toml"
    config = tmp_path / "examples/multilanguage/suite.toml"
    config.parent.mkdir(parents=True)
    shutil.copyfile(source, config)
    for name, task, language in [
        ("kv-python", "durable-kv", "python"),
        ("kv-javascript", "durable-kv", "javascript"),
        ("support-javascript", "support-routing", "javascript"),
    ]:
        initialize(tmp_path / "workspace" / name, task, language, reference=True)
    plan = load_suite(config)
    assert [job.runtime.image for job in plan.jobs] == [
        "python:3.12-slim",
        "node:22-slim",
        "node:22-slim",
    ]
    assert all(job.runtime.backend == "docker" for job in plan.jobs)
    assert plan.describe()["planned_case_executions"] == 34
    assert all(job.gate.min_resolution_rate == 1 for job in plan.jobs)

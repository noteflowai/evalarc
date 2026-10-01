"""Drive a hillclimbing loop with caller-supplied evaluate and propose commands.

Each iteration gives the propose command the tuning failures of the last kept result
(never held-out results), lets it edit only the declared files, checks the patch, reruns
the evaluate command, and keeps or rolls back with the same rules as
``evalarc hillclimb-review``. EvalArc does not call a model: proposing a change and
running the evaluation are the caller's commands, run on the host with ``--trust-local``.
"""

from __future__ import annotations

import difflib
import fnmatch
import hashlib
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from evalarc import trusted
from evalarc.evaluate import write_json
from evalarc.generalization import _normalize, load_split, partition, review_split
from evalarc.hillclimb import (
    OBJECTIVES,
    _cost,
    _decide,
    _noise,
    _rate,
    _stall,
    hillclimb_triage,
)
from evalarc.results_diff import FORMATS, diff, load_results

SCHEMA = "evalarc.hillclimb-run.v1"
KEYS = {
    "workspace",
    "allow",
    "evaluate",
    "propose",
    "held_out",
    "objective",
    "cost_metric",
    "max_cost_ratio",
    "max_iterations",
    "stall_after",
    "min_effect",
    "timeout_seconds",
    "result_suffix",
    "format",
    "threshold",
    "leak_min_chars",
    "paste_check",
}
REQUIRED = {"workspace", "allow", "evaluate", "propose", "held_out"}
# Never editable through allow. Caches are skipped by the outside-allow guard because
# evaluate commands legitimately write them; .git is monitored like any other file.
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
CACHE_DIRS = SKIP_DIRS - {".git"}
MAX_WORKSPACE_FILES = 20_000
MAX_ALLOWED_BYTES = 8 * 1024 * 1024
MAX_ITERATIONS = 50


class LoopError(RuntimeError):
    """The loop cannot continue safely."""


def load_config(path: Path) -> dict:
    raw = trusted.read_config(path, KEYS, REQUIRED)
    base = path.resolve().parent
    workspace = (base / str(raw["workspace"])).resolve()
    if not workspace.is_dir():
        raise ValueError(f"workspace {workspace} is not a directory")
    allow = raw["allow"]
    if (
        not isinstance(allow, list)
        or not allow
        or not all(isinstance(item, str) and item for item in allow)
    ):
        raise ValueError("allow must list relative file globs inside the workspace")
    for item in allow:
        pure = PurePosixPath(item)
        if pure.is_absolute() or ".." in pure.parts:
            raise ValueError(f"allow entry {item!r} must stay inside the workspace")
    objective = raw.get("objective", "quality")
    if objective not in OBJECTIVES:
        raise ValueError(f"objective must be one of {', '.join(OBJECTIVES)}")
    iterations = raw.get("max_iterations", 5)
    if (
        isinstance(iterations, bool)
        or not isinstance(iterations, int)
        or not 1 <= iterations <= MAX_ITERATIONS
    ):
        raise ValueError(f"max_iterations must be an integer 1–{MAX_ITERATIONS}")
    stall_after = raw.get("stall_after", 2)
    if isinstance(stall_after, bool) or not isinstance(stall_after, int) or stall_after < 1:
        raise ValueError("stall_after must be a positive integer")
    suffix = raw.get("result_suffix", ".json")
    if suffix not in (".json", ".xml", ".eval"):
        raise ValueError("result_suffix must be .json, .xml or .eval")
    fmt = raw.get("format", "auto")
    if fmt not in FORMATS:
        raise ValueError(f"format must be one of {', '.join(FORMATS)}")
    min_effect = raw.get("min_effect")
    if min_effect is not None and (
        isinstance(min_effect, bool)
        or not isinstance(min_effect, (int, float))
        or not 0 < min_effect < 1
    ):
        raise ValueError("min_effect must be in (0, 1)")
    split_path = (base / str(raw["held_out"])).resolve()
    return {
        "path": path,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "workspace": workspace,
        "allow": list(allow),
        "evaluate": trusted.command(raw["evaluate"], "evaluate", {"python", "workspace", "output"}),
        "propose": trusted.command(
            raw["propose"],
            "propose",
            {"python", "workspace", "failures", "allowed", "iteration"},
        ),
        "split_path": split_path,
        "split": load_split(split_path),
        "objective": objective,
        "cost_metric": raw.get("cost_metric", "auto"),
        "max_cost_ratio": float(raw.get("max_cost_ratio", 1.0)),
        "max_iterations": iterations,
        "stall_after": stall_after,
        "min_effect": min_effect,
        "timeout": trusted.timeout(raw.get("timeout_seconds"), 3600.0),
        "suffix": suffix,
        "format": fmt,
        "threshold": float(raw.get("threshold", 1.0)),
        "leak_min_chars": int(raw.get("leak_min_chars", 12)),
        "paste_check": bool(raw.get("paste_check", True)),
    }


# --- workspace snapshots ----------------------------------------------------------


def allowed_files(workspace: Path, allow: list[str]) -> list[str]:
    found = []
    for path in sorted(workspace.rglob("*")):
        relative = path.relative_to(workspace).as_posix()
        if any(part in SKIP_DIRS for part in path.relative_to(workspace).parts):
            continue
        if path.is_symlink():
            if any(fnmatch.fnmatchcase(relative, item) for item in allow):
                raise LoopError(f"allowed path {relative} is a symlink")
            continue
        if path.is_file() and any(fnmatch.fnmatchcase(relative, item) for item in allow):
            found.append(relative)
    return found


def snapshot(workspace: Path, allow: list[str]) -> dict[str, bytes]:
    files = {name: (workspace / name).read_bytes() for name in allowed_files(workspace, allow)}
    if sum(map(len, files.values())) > MAX_ALLOWED_BYTES:
        raise LoopError(f"allowed files exceed {MAX_ALLOWED_BYTES} bytes")
    return files


def restore(workspace: Path, allow: list[str], state: dict[str, bytes]) -> None:
    """Return allowed paths to `state`, replacing symlinks instead of writing through them."""
    for path in sorted(workspace.rglob("*"), reverse=True):
        parts = path.relative_to(workspace).parts
        if any(part in SKIP_DIRS for part in parts):
            continue
        relative = "/".join(parts)
        if relative in state or not any(fnmatch.fnmatchcase(relative, item) for item in allow):
            continue
        if path.is_symlink() or path.is_file():
            path.unlink()
    for name, data in state.items():
        target = workspace / name
        if target.is_symlink():
            target.unlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.read_bytes() != data:
            target.write_bytes(data)


def outside_digest(workspace: Path, allow: list[str]) -> dict[str, str]:
    """SHA-256 of every workspace file the propose command must not change.

    Covers .git (hooks, config) and new files; only cache folders are skipped.
    """
    digests, count = {}, 0
    for path in sorted(workspace.rglob("*")):
        parts = path.relative_to(workspace).parts
        if any(part in CACHE_DIRS for part in parts):
            continue
        relative = "/".join(parts)
        if ".git" not in parts and any(fnmatch.fnmatchcase(relative, item) for item in allow):
            continue
        if path.is_symlink():
            digests[relative] = "symlink:" + str(path.readlink())
            continue
        if not path.is_file():
            continue
        count += 1
        if count > MAX_WORKSPACE_FILES:
            raise LoopError(f"workspace has more than {MAX_WORKSPACE_FILES} files")
        digests[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def remove_new(workspace: Path, before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Delete files that appeared outside allow; report modified ones that cannot be undone."""
    modified = []
    for name in sorted(set(before) | set(after)):
        if before.get(name) == after.get(name):
            continue
        if name not in before:
            (workspace / name).unlink(missing_ok=True)
        else:
            modified.append(name)
    return modified


def patch_text(before: dict[str, bytes], after: dict[str, bytes]) -> str:
    out = []
    for name in sorted(set(before) | set(after)):
        old = before.get(name, b"").decode("utf-8", "replace").splitlines(keepends=True)
        new = after.get(name, b"").decode("utf-8", "replace").splitlines(keepends=True)
        out += difflib.unified_diff(
            old,
            new,
            fromfile=f"a/{name}" if name in before else "/dev/null",
            tofile=f"b/{name}" if name in after else "/dev/null",
        )
    return "".join(out)


def added_text(patch: str) -> str:
    return "\n".join(
        line[1:]
        for line in patch.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def copied_cases(text: str, runs: list[dict], members: set[str], min_chars: int) -> list[dict]:
    """Recorded inputs/expected answers of `members` that appear verbatim in `text`."""
    haystack = _normalize(text)
    hits, seen = [], set()
    for run in runs:
        for case_id, items in run["material"].items():
            if case_id not in members:
                continue
            for item in items:
                needle = _normalize(item["text"])
                key = (case_id, item["role"], needle)
                if len(needle) >= min_chars and needle in haystack and key not in seen:
                    seen.add(key)
                    hits.append(
                        {"case_id": case_id, "role": item["role"], "text": item["text"][:160]}
                    )
    return hits


# --- the loop ---------------------------------------------------------------------


def run_loop(config: dict, output: Path) -> dict:
    workspace, allow = config["workspace"], config["allow"]
    output_resolved = output.resolve()
    if output_resolved.is_relative_to(workspace):
        raise ValueError("output must be outside the workspace")
    output.mkdir(parents=True, exist_ok=False)
    (output / "results").mkdir()
    (output / "steps").mkdir()
    original = snapshot(workspace, allow)
    for name, data in original.items():
        target = output / "original" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    shutil.copyfile(config["split_path"], output / "split.json")
    shutil.copyfile(config["path"], output / "config.toml")
    state = {
        "schema_version": SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "config_sha256": config["sha256"],
        "workspace": str(workspace),
        "allow": allow,
        "objective": config["objective"],
        "steps": [],
    }

    def save() -> None:
        write_json(output / "loop.json", state)

    def evaluate(label: str) -> tuple[Path, dict]:
        target = output / "results" / f"{label}{config['suffix']}"
        trusted.run(
            config["evaluate"],
            {"workspace": str(workspace), "output": str(target.resolve())},
            workspace,
            config["timeout"],
            label=f"evaluate ({label})",
        )
        if not target.is_file():
            raise LoopError(f"evaluate ({label}) did not write {target}")
        return target, load_results(target, config["format"], config["threshold"])

    try:
        baseline_path, baseline = evaluate("00-baseline")
        cases = set(baseline["cases"])
        held_out = partition(config["split"], cases)
        tuning = cases - held_out
        evaluated = [(baseline_path, baseline)]
        start = {
            name: _rate(baseline, members)
            for name, members in (("tuning", tuning), ("held_out", held_out))
        }
        noise = {
            name: _noise(start[name], config["min_effect"])
            for name in start
            if start[name]["assessed"]
        }
        state["baseline"] = {"result": baseline_path.name, **start}
        state["noise"] = noise
        kept_index, kept_run, kept_files = 0, baseline, original
        kept_history = [baseline]
        streak = 0
        state["status_reason"] = "max_iterations"
        save()

        for iteration in range(1, config["max_iterations"] + 1):
            step_dir = output / "steps" / f"{iteration:02d}"
            step_dir.mkdir()
            failures = step_dir / "tuning-failures.json"
            write_json(failures, _failures(kept_run, tuning, kept_history, iteration))
            allowed_list = step_dir / "allowed.json"
            write_json(allowed_list, {"allow": allow, "files": sorted(kept_files)})
            guard = outside_digest(workspace, allow)
            step = {"iteration": iteration, "compared_with": evaluated[kept_index][0].name}
            try:
                trusted.run(
                    config["propose"],
                    {
                        "workspace": str(workspace),
                        "failures": str(failures.resolve()),
                        "allowed": str(allowed_list.resolve()),
                        "iteration": str(iteration),
                    },
                    workspace,
                    config["timeout"],
                    label=f"propose (iteration {iteration})",
                )
            except trusted.CommandFailure as error:
                restore(workspace, allow, kept_files)
                step |= {"decision": "propose_failed", "reason": str(error)}
            else:
                after = outside_digest(workspace, allow)
                changed_outside = _changed(guard, after)
                if changed_outside:
                    restore(workspace, allow, kept_files)
                    modified = remove_new(workspace, guard, after)
                    raise LoopError(
                        "propose changed files outside allow: "
                        + ", ".join(changed_outside[:10])
                        + (
                            "; new files were removed, but these existing files were "
                            "modified and must be restored by you (e.g. git checkout): "
                            + ", ".join(modified[:10])
                            if modified
                            else "; the new files were removed"
                        )
                    )
                try:
                    proposed = snapshot(workspace, allow)
                except LoopError:
                    restore(workspace, allow, kept_files)
                    raise
                patch = patch_text(kept_files, proposed)
                (step_dir / "patch.diff").write_text(patch, encoding="utf-8")
                runs = [run for _, run in evaluated]
                added = added_text(patch)
                leaked = copied_cases(added, runs, held_out, config["leak_min_chars"])
                pasted = (
                    copied_cases(added, runs, tuning, config["leak_min_chars"])
                    if config["paste_check"]
                    else []
                )
                if not patch:
                    step |= {
                        "decision": "no_change",
                        "reason": "the propose command changed nothing",
                    }
                elif leaked:
                    restore(workspace, allow, kept_files)
                    step |= {
                        "decision": "rollback_leakage",
                        "reason": "the patch adds held-out case text",
                        "hits": leaked,
                    }
                elif pasted:
                    restore(workspace, allow, kept_files)
                    step |= {
                        "decision": "rollback_pasted_case",
                        "reason": "the patch pastes tuning case text instead of fixing the cause",
                        "hits": pasted,
                    }
                else:
                    label = f"{iteration:02d}"
                    result_path, candidate = evaluate(label)
                    if set(candidate["cases"]) != cases:
                        raise LoopError(f"evaluate ({label}) recorded a different case set")
                    result = diff(kept_run, candidate)
                    parts = review_split(kept_run, candidate, result, config["split"])["partitions"]
                    cost = _cost(result, config["cost_metric"])
                    try:
                        decision, reason = _decide(config["objective"], parts, cost)
                    except ValueError as error:
                        raise LoopError(str(error)) from None
                    evaluated.append((result_path, candidate))
                    step |= {
                        "decision": decision,
                        "reason": reason,
                        "result": result_path.name,
                        "tuning_delta": parts["tuning"]["delta"],
                        "held_out_delta": parts["held_out"]["delta"],
                        "cost": cost,
                    }
                    if decision == "keep":
                        kept_index, kept_run, kept_files = len(evaluated) - 1, candidate, proposed
                        kept_history.append(candidate)
                    else:
                        restore(workspace, allow, kept_files)
            step["kept"] = evaluated[kept_index][0].name
            streak = 0 if step["decision"] == "keep" else streak + 1
            if streak and streak % config["stall_after"] == 0:
                stall = _stall(kept_run, step["kept"], iteration, tuning, noise, kept_history)
                step["stall"] = {k: v for k, v in stall.items() if k != "triage"}
                if stall["headroom_below_noise"]:
                    state["steps"].append(step)
                    state["status_reason"] = "stopped_below_noise"
                    save()
                    break
            state["steps"].append(step)
            save()

        restore(workspace, allow, kept_files)
        runs = [run for _, run in evaluated]
        from evalarc import evidence
        from evalarc.hillclimb import write_hillclimb_report

        params = {
            "format": config["format"],
            "threshold": config["threshold"],
            "objective": config["objective"],
            "cost_metric": config["cost_metric"],
            "max_cost_ratio": config["max_cost_ratio"],
            "stall_after": config["stall_after"],
            "min_effect": config["min_effect"],
            "labels": [path.name for path, _ in evaluated],
            "min_steps": 0,  # every proposal may have been rejected before evaluation
        }
        harness = (
            evidence.copy_harness([(workspace / name, name) for name in sorted(kept_files)], output)
            if kept_files
            else []
        )
        final = evidence.compute_hillclimb(
            runs, params, config["split"], [(output / e["file"], e["label"]) for e in harness]
        )
        evidence.write_params(
            output,
            "hillclimb-review",
            {
                **params,
                "inputs": [{"file": f"results/{path.name}"} for path, _ in evaluated],
                "split": "split.json",
                "harness": harness,
            },
        )
        write_hillclimb_report(output, final)
        (output / "final.diff").write_text(patch_text(original, kept_files), encoding="utf-8")
        state |= {
            "status": "complete",
            "kept": evaluated[kept_index][0].name,
            "recommendation": final["recommendation"],
            "merge_recommended": final["merge_recommended"],
        }
        save()
        return state
    except BaseException as error:
        state["status"] = "failed"
        state["error"] = str(error) or type(error).__name__
        try:
            restore(workspace, allow, kept_files if "kept_files" in locals() else original)
        finally:
            save()
        raise


def _changed(before: dict, after: dict) -> list[str]:
    return sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))


def _failures(run: dict, tuning: set[str], history: list[dict], iteration: int) -> dict:
    """What the propose command may read: tuning failures only, with likely causes."""
    from evalarc.eval_health import TRIAGE_NEXT

    tuning_run = {**run, "cases": {k: v for k, v in run["cases"].items() if k in tuning}}
    triage = {row["case_id"]: row["category"] for row in hillclimb_triage(tuning_run, history)}
    failures = []
    for case_id in sorted(tuning):
        failing = {
            check: [item for item in attempts if item["passed"] is not True]
            for check, attempts in run["cases"].get(case_id, {}).items()
        }
        failing = {check: items for check, items in failing.items() if items}
        if not failing:
            continue
        material = run["material"].get(case_id, [])
        category = triage.get(case_id, "consistent_failure")
        failures.append(
            {
                "case_id": case_id,
                "category": category,
                "next_step": TRIAGE_NEXT[category],
                "input": "\n".join(i["text"] for i in material if i["role"] == "input") or None,
                "expected": "\n".join(i["text"] for i in material if i["role"] == "expected")
                or None,
                "checks": {
                    check: sorted({item.get("evidence") or "" for item in items} - {""})
                    for check, items in failing.items()
                },
                "outputs": sorted(
                    {meta.get("output_text") for meta in run["samples"].get(case_id, [])} - {None}
                )[:5],
            }
        )
    return {
        "schema_version": "evalarc.tuning-failures.v1",
        "iteration": iteration,
        "held_out_excluded": True,
        "rules": [
            "Fix the root cause (a missing or wrong rule), not the wording.",
            "Do not paste these inputs or expected answers into the edited files; such "
            "patches are rolled back before evaluation.",
            "Skip pipeline, truncated and grader_inconsistent cases: they are not fixed by "
            "editing the prompt.",
        ],
        "failures": failures,
    }


def command(args) -> int:
    try:
        if not args.trust_local:
            raise ValueError(trusted.TRUST_MESSAGE)
        config = load_config(args.config)
        state = run_loop(config, args.output)
    except (OSError, ValueError, KeyError, TypeError, LoopError, trusted.CommandFailure) as error:
        print(f"evalarc: {error}", file=sys.stderr)
        return 2
    for step in state["steps"]:
        extra = ""
        if "tuning_delta" in step:
            extra = (
                f" (tuning {step['tuning_delta'] * 100:+.1f} pp, held out "
                f"{step['held_out_delta'] * 100:+.1f} pp)"
            )
        stall = " — stalled" if step.get("stall") else ""
        print(f"  {step['iteration']}. {step['decision']}{extra}{stall}")
    print(
        f"Stopped: {state['status_reason']} | Kept: {state['kept']} | "
        f"Recommendation: {state['recommendation']}\n"
        f"Workspace left at the kept version; originals in {args.output / 'original'}\n"
        f"Report: {args.output / 'index.html'}"
    )
    return 0 if state["merge_recommended"] else 1

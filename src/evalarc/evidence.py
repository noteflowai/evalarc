"""Self-contained evidence folders for diff, eval-health and hillclimb-review.

Each folder keeps byte copies of every input (result files, split, case manifest,
scanned harness files) and ``params.json`` with every option, so ``evalarc verify``
can rerun the same computation offline and confirm the saved report. The commands
and the verifier call the same ``compute_*`` functions, so they cannot drift.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath

from evalarc.results_diff import load_results

PARAMS_SCHEMA = "evalarc.report-params.v1"
MAX_HARNESS_COPY_BYTES = 16 * 1024 * 1024
IGNORED = {"created_at", "evalarc_version"}


# --- shared computations ----------------------------------------------------------


def compute_diff(runs: list[dict], params: dict, split: dict | None, harness) -> dict:
    from evalarc.generalization import generalization_passed, review_split, scan_harness
    from evalarc.results_diff import diff
    from evalarc.usage import cost_gate

    result = diff(*runs)
    held_out = None
    if split is not None:
        result["generalization"] = review_split(*runs, result, split)
        held_out = set(result["generalization"]["split"]["held_out_cases"])
    if harness:
        result["leakage"] = scan_harness(harness, runs, held_out, params["leak_min_chars"])
    if params["require_generalization"]:
        result["generalization_required"] = True
        result["generalization_passed"] = generalization_passed(result)
    if params["max_cost_ratio"] is not None:
        result["cost_gate"] = cost_gate(
            result["usage"], params["cost_metric"], params["max_cost_ratio"]
        )
    return result


def diff_passed(result: dict) -> bool:
    return bool(
        result["gate_passed"]
        and result.get("generalization_passed", True)
        and (result.get("cost_gate") or {}).get("passed", True)
    )


def compute_health(runs: list[dict], params: dict, manifest: dict | None) -> dict:
    from evalarc.eval_health import health, plan

    result = health(runs, params["saturation"], params["min_effect"], params["ordered"], manifest)
    if params["plan_attempts"] is not None or params["plan_configs"] is not None:
        size = result["size"]
        result["plan"] = plan(
            size,
            size["attempts_per_case"]
            if params["plan_attempts"] is None
            else params["plan_attempts"],
            size["configurations"] if params["plan_configs"] is None else params["plan_configs"],
        )
    return result


def compute_hillclimb(runs: list[dict], params: dict, split: dict, harness) -> dict:
    from evalarc.hillclimb import review

    return review(
        runs,
        split,
        params["objective"],
        params["cost_metric"],
        params["max_cost_ratio"],
        params["stall_after"],
        params["min_effect"],
        harness or None,
        labels=params["labels"],
        min_steps=params["min_steps"],
    )


# --- writing ----------------------------------------------------------------------


def copy_input(path: Path, expected_sha256: str, target: Path) -> None:
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError(f"{path} changed while it was being read")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def copy_harness(paths, output: Path) -> list[dict]:
    """Copy every scanned harness file to harness/NNNN, recording its scan label."""
    from evalarc.generalization import harness_files

    entries, total = [], 0
    for index, (path, label) in enumerate(harness_files(paths)):
        data = path.read_bytes()
        total += len(data)
        if total > MAX_HARNESS_COPY_BYTES:
            raise ValueError(f"harness files exceed {MAX_HARNESS_COPY_BYTES} bytes")
        name = f"harness/{index:04d}"
        (output / "harness").mkdir(exist_ok=True)
        (output / name).write_bytes(data)
        entries.append({"file": name, "label": label, "sha256": hashlib.sha256(data).hexdigest()})
    return entries


def write_params(output: Path, kind: str, params: dict) -> None:
    document = {"schema_version": PARAMS_SCHEMA, "kind": kind, **params}
    (output / "params.json").write_text(
        json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


# --- verifying --------------------------------------------------------------------

REPORT_FILES = {
    "diff": "diff.json",
    "eval-health": "health.json",
    "hillclimb-review": "hillclimb.json",
}
SCHEMAS = {
    "evalarc.results-diff.v1": "diff",
    "evalarc.eval-health.v1": "eval-health",
    "evalarc.hillclimb-review.v1": "hillclimb-review",
}
SCOPE = (
    "Reran the computation from the preserved input bytes and recorded options and "
    "compared it with the saved report. The source tools' grading is not rerun, inputs "
    "are not authenticated, and HTML and Markdown are not checked."
)


def detect(directory: Path) -> str | None:
    params = directory / "params.json"
    if not params.is_file():
        return None
    try:
        kind = json.loads(params.read_text(encoding="utf-8")).get("kind")
    except (ValueError, UnicodeDecodeError):
        return None
    return kind if kind in REPORT_FILES else None


def verify_report(directory: Path) -> dict:
    """Recompute a diff, eval-health or hillclimb-review folder and compare."""
    files: dict[str, dict] = {}

    def read(relative: str) -> bytes:
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts:
            raise ValueError(f"evidence path {relative!r} leaves the folder")
        path = directory / relative
        if any(item.is_symlink() for item in (path, *path.parents) if item != item.parent):
            raise ValueError("evidence contains a symlink")
        data = path.read_bytes()
        files[relative] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        return data

    def loaded(relative: str, expected: dict, fmt: str, threshold: float) -> dict:
        data = read(relative)
        if hashlib.sha256(data).hexdigest() != expected["sha256"]:
            raise ValueError(f"{relative} differs from the input the report recorded")
        run = load_results(directory / relative, fmt, threshold)
        # The report records the original file name; the copy may be renamed.
        run["source"] = dict(expected)
        return run

    params = json.loads(read("params.json"))
    if params.get("schema_version") != PARAMS_SCHEMA:
        raise ValueError("params.json is not an EvalArc report parameter file")
    kind = params.get("kind")
    if kind not in REPORT_FILES:
        raise ValueError(f"unknown report kind {kind!r}")
    recorded = json.loads(read(REPORT_FILES[kind]))
    if SCHEMAS.get(recorded.get("schema_version")) != kind:
        raise ValueError(f"{REPORT_FILES[kind]} does not hold a {kind} report")
    fmt, threshold = params["format"], params["threshold"]
    harness = [
        (directory / _checked(entry, read), entry["label"]) for entry in params.get("harness") or []
    ]

    if kind == "diff":
        runs = [
            loaded(item["file"], recorded[label]["source"], fmt, threshold)
            for label, item in zip(("baseline", "current"), params["inputs"])
        ]
        split = _split(params, read, directory, recorded.get("generalization"))
        computed = compute_diff(runs, params, split, harness)
        passed = diff_passed(computed)
        summary = {
            "gate_passed": computed["gate_passed"],
            "passed": passed,
            "blocking_changes": computed["blocking_changes"],
        }
    elif kind == "eval-health":
        runs = [
            loaded(item["file"], run["source"], fmt, threshold)
            for item, run in zip(params["inputs"], recorded["runs"])
        ]
        manifest = None
        if params.get("cases"):
            from evalarc.provenance import load as load_manifest

            read(params["cases"])
            manifest = load_manifest(directory / params["cases"])
            manifest["source"]["name"] = recorded["provenance"]["manifest"]["name"]
        computed = compute_health(runs, params, manifest)
        passed = computed["healthy"]
        summary = {"healthy": passed, "warnings": computed["warnings"]}
    else:
        runs = [
            loaded(item["file"], run["source"], fmt, threshold)
            for item, run in zip(params["inputs"], recorded["runs"])
        ]
        split = _split(params, read, directory, recorded)
        computed = compute_hillclimb(runs, params, split, harness)
        passed = computed["merge_recommended"]
        summary = {
            "recommendation": computed["recommendation"],
            "decisions": [step["decision"] for step in computed["steps"]],
        }
    if len(params["inputs"]) != len(runs):
        raise ValueError("params.json and the report list different inputs")
    if _strip(recorded) != _strip(computed):
        raise ValueError(f"{REPORT_FILES[kind]} differs from the recomputed {kind} report")
    return {
        "schema_version": "evalarc.verification.v1",
        "verified": True,
        "kind": kind,
        "passed": passed,
        **summary,
        "files": files,
        "scope": SCOPE,
    }


def _checked(entry: dict, read) -> str:
    data = read(entry["file"])
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise ValueError(f"{entry['file']} differs from the harness file that was scanned")
    return entry["file"]


def _split(params: dict, read, directory: Path, recorded: dict | None) -> dict | None:
    from evalarc.generalization import load_split

    if not params.get("split"):
        return None
    read(params["split"])
    split = load_split(directory / params["split"])
    if recorded and recorded.get("split"):
        split["source"]["name"] = recorded["split"]["source"]["name"]
    return split


def _strip(document: object) -> object:
    """Drop generation timestamps at every level and normalize through JSON."""

    def walk(value):
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items() if k not in IGNORED}
        if isinstance(value, list):
            return [walk(v) for v in value]
        return value

    return json.loads(json.dumps(walk(document), sort_keys=True, allow_nan=False))

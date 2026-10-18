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


def compute_diff(
    runs: list[dict], params: dict, split: dict | None, harness, manifest: dict | None = None
) -> dict:
    from evalarc.generalization import generalization_passed, review_split, scan_harness
    from evalarc.results_diff import diff
    from evalarc.usage import cost_gate

    # Absent from params.json written before suite roles reached diff.
    require_regression = params.get("require_regression_suite", False)
    if not isinstance(require_regression, bool):
        raise ValueError("params.json require_regression_suite must be true or false")
    if require_regression and manifest is None:
        raise ValueError("--require-regression-suite requires --cases")
    require_f2p = params.get("require_f2p", False)
    if not isinstance(require_f2p, bool):
        raise ValueError("params.json require_f2p must be true or false")
    if require_f2p and manifest is None:
        raise ValueError("--require-f2p requires --cases")
    transcripts = params.get("transcript_metrics", False)
    if not isinstance(transcripts, bool):
        raise ValueError("params.json transcript_metrics must be true or false")
    result = diff(*runs)
    if transcripts:
        from evalarc.usage import compare_usage

        result["usage"] = compare_usage(*runs, transcripts=True)
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
    if manifest is not None:
        _add_manifest(result, runs, manifest, require_regression, require_f2p)
    return result


def _add_manifest(
    result: dict, runs: list[dict], manifest: dict, required: bool, require_f2p: bool
) -> None:
    from evalarc import provenance

    case_ids = set(runs[0]["cases"]) | set(runs[1]["cases"])
    review = provenance.review(manifest, case_ids)
    if not review.get("suites") and not review.get("attributes"):
        raise ValueError(
            'the case manifest declares no suite and no case attributes; add "suite", '
            '"expect_action", "expect_change", "impact" or "owner" to its entries'
        )
    if required and "regression" not in (review.get("suites") or {}).values():
        # A required gate over an empty regression suite would pass without checking anything.
        raise ValueError(
            '--require-regression-suite needs at least one case with "suite": "regression"'
        )
    if review.get("suites"):
        _add_suites(result, runs, review, required)
    _add_attributes(result, runs, review, require_f2p)


def _add_attributes(result: dict, runs: list[dict], review: dict, require_f2p: bool) -> None:
    """Additive keys for diff --cases with expect_action, expect_change, impact, owner."""
    from evalarc import trials

    attributes = review.get("attributes") or {}
    changes = trials.expected_changes(runs[0], runs[1], attributes)
    if require_f2p and not (changes and changes["fail_to_pass"]["cases"]):
        raise ValueError(
            '--require-f2p needs at least one case with "expect_change": "fail_to_pass"'
        )
    if not attributes:
        return
    for row in result["changes"]:
        for name, value in (attributes.get(row["case_id"]) or {}).items():
            row[name] = value
    view: dict = {"manifest": review["manifest"]}
    sides = {
        label: trials.behavior_rates(run, attributes)
        for label, run in (("baseline", runs[0]), ("current", runs[1]))
    }
    if sides["baseline"] or sides["current"]:
        view["behavior"] = sides
    if changes:
        view["expected_changes"] = changes
    from evalarc.provenance import ATTRIBUTES
    from evalarc.results_diff import BLOCKING

    order = ATTRIBUTES["impact"]
    rank = {name: index for index, name in enumerate(order)}
    blocking = [
        {
            "case_id": row["case_id"],
            "check": row["check"],
            "kind": row["kind"],
            "impact": row.get("impact"),
            "owner": row.get("owner"),
        }
        for row in result["changes"]
        if row["kind"] in BLOCKING and (row.get("impact") or row.get("owner"))
    ]
    if blocking:
        blocking.sort(key=lambda item: (rank.get(item["impact"], len(order)), item["case_id"]))
        view["blocking_by_impact"] = blocking
    result["case_attributes"] = view
    if require_f2p:
        result["f2p_required"] = True
        result["f2p_passed"] = not (
            changes["fail_to_pass"]["unresolved"] or changes["pass_to_pass"]["broken"]
        )


def _add_suites(result: dict, runs: list[dict], review: dict, required: bool) -> None:
    """Additive keys for diff --cases: suite per changed row and per-suite trials."""
    from evalarc import trials

    if required and "regression" not in review["suites"].values():
        # A required gate over an empty regression suite would pass without checking anything.
        raise ValueError(
            '--require-regression-suite needs at least one case with "suite": "regression"'
        )
    comparison = trials.suite_comparison(runs[0], runs[1], review)
    for row in result["changes"]:
        role = review["suites"].get(row["case_id"])
        if role:
            row["suite"] = role
    result["suites"] = comparison
    if required:
        result["regression_suite_required"] = True
        result["regression_suite_passed"] = not comparison["regression_failures"]


def diff_passed(result: dict) -> bool:
    return bool(
        result["gate_passed"]
        and result.get("generalization_passed", True)
        and (result.get("cost_gate") or {}).get("passed", True)
        and result.get("regression_suite_passed", True)
        and result.get("f2p_passed", True)
    )


def compute_health(
    runs: list[dict], params: dict, manifest: dict | None, reference: dict | None = None
) -> dict:
    from evalarc.eval_health import health, plan

    # Absent from params.json written before trial metrics existed.
    trial_metrics = params.get("trial_metrics", False)
    if not isinstance(trial_metrics, bool):
        raise ValueError("params.json trial_metrics must be true or false")
    extra = {name: params.get(name, False) for name in ("transcript_metrics", "cluster_errors")}
    for name, value in extra.items():
        if not isinstance(value, bool):
            raise ValueError(f"params.json {name} must be true or false")
    result = health(
        runs,
        params["saturation"],
        params["min_effect"],
        params["ordered"],
        manifest,
        trial_metrics=trial_metrics,
        reference_run=reference,
        **extra,
    )
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


def compute_hillclimb(
    runs: list[dict], params: dict, split: dict, harness, manifest: dict | None = None
) -> dict:
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
        manifest=manifest,
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
        manifest = None
        if params.get("cases"):
            from evalarc.provenance import load as load_manifest

            read(params["cases"])
            manifest = load_manifest(directory / params["cases"])
            view = recorded.get("suites") or recorded.get("case_attributes")
            if not isinstance(view, dict):
                raise ValueError("diff.json lacks the suite view that params.json records")
            manifest["source"]["name"] = view["manifest"]["name"]
        computed = compute_diff(runs, params, split, harness, manifest)
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
        reference = None
        if params.get("reference"):
            if not isinstance(recorded.get("reference"), dict):
                raise ValueError("health.json lacks the reference that params.json records")
            reference = loaded(params["reference"], recorded["reference"]["source"], fmt, threshold)
        computed = compute_health(runs, params, manifest, reference)
        passed = computed["healthy"]
        summary = {"healthy": passed, "warnings": computed["warnings"]}
    else:
        runs = [
            loaded(item["file"], run["source"], fmt, threshold)
            for item, run in zip(params["inputs"], recorded["runs"])
        ]
        split = _split(params, read, directory, recorded)
        manifest = None
        if params.get("cases"):
            from evalarc.provenance import load as load_manifest

            read(params["cases"])
            manifest = load_manifest(directory / params["cases"])
            if not isinstance(recorded.get("suites"), dict):
                raise ValueError("hillclimb.json lacks the suite roles that params.json records")
            manifest["source"]["name"] = recorded["suites"]["manifest"]["name"]
        computed = compute_hillclimb(runs, params, split, harness, manifest)
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

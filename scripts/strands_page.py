"""Present the fixed, SDK-checked Strands example without browser dependencies."""

from __future__ import annotations

import hashlib
import html
import json
import shutil
import zipfile
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_rows(native: dict, source: dict, source_hash: str) -> dict:
    """Recheck this example's two exact-state rules against the original recording."""
    fields = ("cases", "scores", "test_passes", "reasons", "detailed_results")
    if any(len(native[field]) != 8 for field in fields):
        raise ValueError("Expected eight native case/rule rows")
    original = {f"{row['case_id']}@{row['seed']}": row for row in source["cases"]}
    expected_keys = {
        (name, f"ticket.{field}") for name in original for field in ("notes", "status")
    }
    rows = {}
    for case, score, passed, reason, details in zip(*(native[f] for f in fields), strict=True):
        key = case["name"], case["evaluator"]
        if key not in expected_keys or key in rows:
            raise ValueError("Missing, duplicate or unknown native case/rule identity")
        recorded = original[key[0]]
        target = next(name for name in recorded["initial_state"] if name.startswith("T-"))
        initial = recorded["initial_state"][target]
        expected = {
            "notes": [*initial["notes"], f"Reviewed request {target}."],
            "status": "closed" if initial["resolved"] else "open",
        }
        actual = recorded["final_state"][target]
        field = key[1].split(".")[1]
        correct = actual[field] == expected[field]
        expected_reason = f"{key[1]}: {'matches' if correct else 'differs from'} expected"
        if (
            case["metadata"]["source_sha256"] != source_hash
            or case["actual_environment_state"] != [{"name": "ticket", "state": actual}]
            or case["expected_environment_state"] != [{"name": "ticket", "state": expected}]
            or type(passed) is not bool
            or passed != correct
            or type(score) not in (int, float)
            or score != float(correct)
            or reason != expected_reason
            or details != [{"score": score, "test_pass": passed, "reason": reason, "label": None}]
        ):
            raise ValueError("Native state, score or verdict differs from the fixed rule")
        rows[key] = {"passed": passed, "actual": actual[field], "expected": expected[field]}
    if rows.keys() != expected_keys or native["overall_score"] != sum(native["scores"]) / 8:
        raise ValueError("Native inventory or overall score disagrees")
    return rows


def review_data(recorded: Path, original: Path) -> tuple[dict, dict, dict]:
    comparison = json.loads((recorded / "comparison.json").read_bytes())
    reports, rows = {}, {}
    for name in ("baseline", "current"):
        source_path = original / f"{name}.json"
        if digest(source_path) != comparison["source_sha256"][name]:
            raise ValueError("Original recording fingerprint differs")
        source = json.loads(source_path.read_bytes())
        if source["score"] != comparison["original_evalarc_scores"][name]:
            raise ValueError("Original weighted score differs")
        reports[name] = json.loads((recorded / f"{name}-native.json").read_bytes())
        rows[name] = verified_rows(reports[name], source, digest(source_path))
        passed = [row["passed"] for row in rows[name].values()]
        if comparison[name] != {
            "native_mean_score": reports[name]["overall_score"],
            "passed_rows": sum(passed),
            "rows": len(passed),
            "all_rows_pass": all(passed),
        }:
            raise ValueError("Comparison summary disagrees with native rows")
    for label, before, after in (("regressions", True, False), ("improvements", False, True)):
        computed = {
            key
            for key in rows["baseline"]
            if rows["baseline"][key]["passed"] == before and rows["current"][key]["passed"] == after
        }
        recorded_keys = [tuple(key) for key in comparison[label]]
        if len(recorded_keys) != len(set(recorded_keys)) or set(recorded_keys) != computed:
            raise ValueError("Comparison changes disagree with native rows")
    if comparison["regression_gate_passes"] is not (not comparison["regressions"]):
        raise ValueError("Regression gate disagrees with native rows")
    return comparison, rows["baseline"], rows["current"]


def render_rows(before: dict, after: dict, identity: str) -> str:
    result = []
    for key, old in before.items():
        new = after[key]
        change = (
            "regression"
            if old["passed"] and not new["passed"]
            else "improvement"
            if not old["passed"] and new["passed"]
            else "unchanged"
        )
        row_id = "check-" + hashlib.sha256(json.dumps([identity, *key]).encode()).hexdigest()[:20]
        values = []
        for label, value, verdict in (
            ("Expected in both revisions", old["expected"], None),
            ("Baseline", old["actual"], old["passed"]),
            ("Current", new["actual"], new["passed"]),
        ):
            if old["expected"] != new["expected"]:
                raise ValueError("Expected state changed between revisions")
            badge = (
                ""
                if verdict is None
                else (
                    f'<span class="badge {"pass" if verdict else "fail"}">'
                    f"{'PASS' if verdict else 'FAIL'}</span>"
                )
            )
            values.append(
                f'<div><h3>{label} {badge}</h3><pre tabindex="0">'
                f"{html.escape(json.dumps(value, indent=2))}</pre></div>"
            )
        opened = " open" if change == "regression" else ""
        result.append(
            f'<details class="check" id="{row_id}" data-change="{change}"{opened}>'
            f"<summary><span><strong>{html.escape(key[0])}</strong>"
            f"<code>{html.escape(key[1])}</code></span>"
            f'<span class="badge {change}">{change.upper()}</span></summary>'
            f'<div class="states">{"".join(values)}</div>'
            f'<p class="check-link"><a href="#{row_id}">Link to this check</a></p></details>'
        )
    return "\n".join(result)


def build_strands(root: Path, destination: Path) -> None:
    recorded = root / "examples/strands-state-review/recorded"
    comparison, before, after = review_data(recorded, root / "examples/comparison")
    destination.mkdir()
    for path in recorded.glob("*.json"):
        shutil.copyfile(path, destination / path.name)
    for name in ("baseline", "current"):
        shutil.copyfile(
            root / f"examples/comparison/{name}.json", destination / f"{name}-evalarc.json"
        )
    for name in ("review.css", "review.js"):
        shutil.copyfile(root / "site/strands" / name, destination / name)
    native_hashes = {
        name: digest(recorded / f"{name}-native.json") for name in ("baseline", "current")
    }
    replacements = {
        "__ROWS__": render_rows(before, after, json.dumps(native_hashes, sort_keys=True)),
        "__BASELINE_MEAN__": f"{comparison['baseline']['native_mean_score']:.0%}",
        "__CURRENT_MEAN__": f"{comparison['current']['native_mean_score']:.1%}",
        "__REGRESSIONS__": str(len(comparison["regressions"])),
        "__IMPROVEMENTS__": str(len(comparison["improvements"])),
        "__ROW_COUNT__": str(len(before)),
        "__SDK_VERSION__": html.escape(comparison["sdk_versions"]["strands-agents-evals"]),
        "__SOURCE_HASHES__": html.escape(json.dumps(native_hashes, indent=2)),
    }
    page = (root / "site/strands/index.html").read_text()
    for marker, value in replacements.items():
        page = page.replace(marker, value)
    (destination / "index.html").write_text(page)
    shutil.copyfile(root / "LICENSE", destination / "LICENSE")
    (destination / "manifest.json").write_text(
        json.dumps(
            {
                "schema": "evalarc.strands-example.v1",
                "scope": comparison["scope"],
                "files": {p.name: digest(p) for p in sorted(destination.iterdir()) if p.is_file()},
            },
            indent=2,
        )
        + "\n"
    )
    with zipfile.ZipFile(destination.parent / "strands-review.zip", "x") as archive:
        for source in sorted(destination.iterdir()):
            member = zipfile.ZipInfo(f"strands-review/{source.name}", (2020, 1, 1, 0, 0, 0))
            member.compress_type = zipfile.ZIP_DEFLATED
            member.create_system = 3
            member.external_attr = 0o100644 << 16
            archive.writestr(member, source.read_bytes())

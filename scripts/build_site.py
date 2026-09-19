"""Build a static evidence explorer from the committed development audits."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://github.com/noteflowai/evalarc"
MANIFEST = "manifest.json"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))


def write_suite_bundle(destination: Path) -> None:
    """Package only verified input bytes, with stable ZIP metadata."""
    from evalarc.verify import verify as verify_evidence

    source = ROOT / "examples" / "suite"
    receipt = verify_evidence(source)
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, identity in sorted(receipt["files"].items()):
            content = (source / name).read_bytes()
            if hashlib.sha256(content).hexdigest() != identity["sha256"]:
                raise ValueError("Suite evidence changed while packaging")
            member = zipfile.ZipInfo(f"suite-evidence/{name}", date_time=(2020, 1, 1, 0, 0, 0))
            member.compress_type = zipfile.ZIP_DEFLATED
            member.create_system = 3
            member.external_attr = 0o100644 << 16
            archive.writestr(member, content)


def verify_comparison() -> None:
    from evalarc.compare import compare
    from evalarc.records import read_evaluation

    folder = ROOT / "examples" / "comparison"
    computed = compare(
        read_evaluation(folder / "baseline.json"), read_evaluation(folder / "current.json")
    )
    recorded = json.loads((folder / "comparison.json").read_text())
    computed.pop("created_at")
    recorded.pop("created_at")
    if computed != recorded:
        raise ValueError("Recorded comparison disagrees with its input evaluations")
    if (
        recorded["baseline"]["score"] != 0.9
        or recorded["current"]["score"] != 0.9375
        or recorded["score_delta"] != 0.0375
        or recorded["regressions"]
        != [{"seed": 17, "case_id": "retry-after-commit", "check": "notes"}]
        or len(recorded["improvements"]) != 2
    ):
        raise ValueError("Comparison no longer supports the featured regression")
    individual = read_evaluation(ROOT / "examples" / "evaluation" / "evaluation.json")
    if individual != read_evaluation(folder / "current.json"):
        raise ValueError("Individual example differs from the current comparison evidence")


def verified_repetition(folder: Path) -> dict:
    from evalarc.records import read_evaluation
    from evalarc.repetition import summarize_attempts

    recorded = json.loads((folder / "repetition.json").read_text())
    attempts = sorted((folder / "attempts").glob("*/evaluation.json"))
    reports = [read_evaluation(path) for path in attempts]
    computed = summarize_attempts(reports, recorded["requested_attempts"])
    for field in ("created_at", "evalarc_version"):
        computed.pop(field)
    expected = {
        key: value
        for key, value in recorded.items()
        if key not in ("created_at", "evalarc_version")
    }
    expected_paths = [
        folder / "attempts" / f"{index:04d}" / "evaluation.json"
        for index in range(1, recorded["completed_attempts"] + 1)
    ]
    if (
        computed != expected
        or attempts != expected_paths
        or any(not path.with_name("index.html").is_file() for path in attempts)
    ):
        raise ValueError("Recorded repetition disagrees with its attempt evaluations or reports")
    return recorded


def verify_repetitions() -> None:
    summaries = []
    for directory, resolved, score in (
        ("repetition", 3, 1.0),
        ("repetition-faulty", 0, 0.9375),
    ):
        folder = ROOT / "examples" / directory
        recorded = verified_repetition(folder)
        if (
            recorded["completed_attempts"] != 3
            or not recorded["valid"]
            or recorded["requested_attempts"] != 3
            or recorded["resolved_attempts"] != resolved
            or recorded["mean_score"] != score
            or recorded["variable_checks"] != 0
            or recorded["runtime"]["backend"] != "docker"
            or recorded["task"]["id"] != "support-routing"
        ):
            raise ValueError("Repetition no longer supports the featured outcomes")
        summaries.append(recorded)
    for field in ("task", "grader_sha256", "cases_sha256", "runtime", "seeds"):
        if summaries[0][field] != summaries[1][field]:
            raise ValueError("Featured repetition controls use different evaluation conditions")


def verify_suite() -> None:
    from evalarc.junit import render_junit
    from evalarc.suite import Gate, assess_gate

    folder = ROOT / "examples" / "suite"
    record = json.loads((folder / "suite.json").read_text())
    plan = json.loads((folder / "plan.json").read_text())
    config = tomllib.loads((folder / "suite.toml").read_text())
    identities = ["coding-reference", "support-partial", "support-protected"]
    digest = sha256(folder / "suite.toml")
    if (
        record["manifest_sha256"] != digest
        or plan["manifest_sha256"] != digest
        or any(
            [job["id"] for job in source["jobs"]] != identities for source in (record, plan, config)
        )
    ):
        raise ValueError("Suite provenance or job inventory differs from its configuration")
    for job, raw in zip(record["jobs"], config["jobs"], strict=True):
        summary = verified_repetition(folder / "jobs" / job["id"])
        gate = Gate(**raw.get("gate", {}))
        normalized_gate = json.loads(
            json.dumps(
                {
                    "min_mean_score": gate.min_mean_score,
                    "min_resolution_rate": gate.min_resolution_rate,
                    "required_dimensions": gate.required_dimensions,
                }
            )
        )
        decision = assess_gate(summary, gate)
        observed_keys = (
            "requested_attempts",
            "completed_attempts",
            "assessed_attempts",
            "invalid_attempts",
            "resolved_attempts",
            "mean_score",
            "assessed_resolution_rate",
            "variable_cases",
            "variable_checks",
        )
        if (
            job["gate"] != normalized_gate
            or job["decision"] != decision
            or job["fully_resolved"] != summary["all_attempts_resolved"]
            or job["observed"] != {key: summary[key] for key in observed_keys}
            or any(
                job[key] != summary[key]
                for key in (
                    "task",
                    "candidate_sha256",
                    "grader_sha256",
                    "cases_sha256",
                    "runtime",
                    "seeds",
                )
            )
            or summary["requested_attempts"] != raw.get("attempts", 1)
            or summary["seeds"] != raw.get("seeds", [17, 41, 97])
        ):
            raise ValueError("Recorded suite gate disagrees with its configuration or attempts")
    reference, partial, protected = record["jobs"]
    if (
        not reference["fully_resolved"]
        or not partial["decision"]["accepted"]
        or protected["decision"]["accepted"]
        or partial["fully_resolved"]
        or protected["fully_resolved"]
        or any(
            partial[key] != protected[key]
            for key in (
                "candidate_sha256",
                "grader_sha256",
                "cases_sha256",
                "runtime",
                "seeds",
                "observed",
            )
        )
        or partial["observed"]["mean_score"] != 0.9375
        or partial["observed"]["completed_attempts"] != 2
        or record["total_jobs"] != 3
        or record["accepted_jobs"] != 2
        or record["fully_resolved_jobs"] != 1
        or record["invalid_jobs"] != 0
        or not record["valid"]
        or record["accepted"]
        or record["status"] != "failed"
        or plan["planned_attempts"] != 5
        or plan["planned_case_executions"] != 31
    ):
        raise ValueError("Suite no longer supports the featured acceptance comparison")
    with tempfile.TemporaryDirectory(prefix="evalarc-site-junit-") as temporary:
        expected = Path(temporary) / "junit.xml"
        render_junit(record, expected)
        if expected.read_bytes() != (folder / "junit.xml").read_bytes():
            raise ValueError("Recorded JUnit disagrees with suite gate decisions")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def explicit_lab_navigation(folder: Path, commit: str) -> None:
    """Update copied presentation links, preserving every original experiment byte."""
    page = folder / "index.html"
    original = page.read_bytes()
    updated = (
        original.replace(b'href="../"', b'href="../index.html"')
        .replace(b'href="../skill-impact/"', b'href="../skill-impact/index.html"')
        .replace(b'href="research-records.zip"', b'href="research-records.zip?download=true"')
    )
    if updated == original:
        return
    page.write_bytes(updated)
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["presentation"] = {
        "source_commit": commit,
        "original_index_sha256": hashlib.sha256(original).hexdigest(),
        "change": "Explicit HTML navigation and attachment downloads for static hosting",
    }
    manifest["files"]["index.html"] = {
        "sha256": hashlib.sha256(updated).hexdigest(),
        "bytes": len(updated),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


def verify(folder: Path) -> dict:
    record = json.loads((folder / MANIFEST).read_text())
    if record["source_repository"] != SOURCE or not re.fullmatch(
        r"[a-f0-9]{40}", record["source_commit"]
    ):
        raise ValueError("Unexpected source provenance")
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    if actual != set(record["files"]) | {MANIFEST}:
        raise ValueError("Bundle file inventory differs from manifest")
    for name, digest in record["files"].items():
        path = folder / name
        if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
            raise ValueError(f"Invalid bundle path: {name}")
        if sha256(path) != digest:
            raise ValueError(f"Bundle file changed: {name}")
    return record


def coverage_cards(audits: dict) -> str:
    cards = []
    for name, audit in audits.items():
        fragile = [
            (i, row)
            for i, row in enumerate(audit["mutants"])
            if row["valid"] and row["killed"] and len(set(row["failing_cases"])) == 1
        ]
        links = "".join(
            f'<li><a href="{name}/index.html#fault-{index}">'
            f"{html.escape(row['name'])}"
            f"</a><span> Sole case: {html.escape(row['failing_cases'][0])}</span></li>"
            for index, row in fragile
        )
        cards.append(
            '<article class="coverage-card">'
            f"<h3>{html.escape(audit['reference']['task']['id'])}</h3>"
            f"<p><strong>{audit['killed']}/{audit['total']}</strong> declared faults detected</p>"
            f'<p class="coverage-fragile">{len(fragile)} single-case dependencies</p>'
            f'<ul>{links}</ul><a href="{name}/index.html">'
            "Inspect all controls &#8599;</a></article>"
        )
    return "".join(cards)


def build(destination: Path) -> dict:
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Output already exists; choose a fresh build directory")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(
        subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    )
    # Headline claims must remain tied to the saved evidence.
    specifications = [
        ("coding", "audit", "durable-kv", 8, "boolean-equals-one", 0.925),
        ("support", "support-audit", "support-routing", 7, "new-key-on-retry", 0.9375),
    ]
    specifications.append(
        (
            "robot",
            "research/robot-audit-python",
            "robot-evidence-review",
            6,
            "invent-source",
            0.9,
        )
    )
    audits = {}
    for name, directory, task, count, spotlight, score in specifications:
        audit = json.loads((ROOT / "examples" / directory / "audit.json").read_text())
        audits[name] = audit
        if (
            not audit["valid"]
            or not audit["reference_passed"]
            or not audit["reference"]["resolved"]
            or audit["reference"]["task"]["id"] != task
            or audit["total"] != count
            or audit["killed"] != count
            or len(audit["mutants"]) != count
            or any(not row["valid"] or not row["killed"] for row in audit["mutants"])
        ):
            raise ValueError(f"Recorded audit no longer supports the showcase: {task}")
        highlighted = next(row for row in audit["mutants"] if row["name"] == spotlight)
        if highlighted["score"] != score or highlighted["evaluation"]["resolved"]:
            raise ValueError(f"Spotlight outcome changed: {spotlight}")
        for row in audit["mutants"]:
            observed = sorted(
                {
                    case["case_id"]
                    for case in row["evaluation"]["cases"]
                    if case["checks"].get(row["target_dimension"]) is False
                }
            )
            if observed != sorted(set(row["failing_cases"])):
                raise ValueError(f"Audit detection evidence disagrees: {row['name']}")
    verify_comparison()
    verify_repetitions()
    verify_suite()
    destination.mkdir(parents=True)
    for path in (ROOT / "site").iterdir():
        if path.is_file():
            if path.name == "index.html":
                version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
                (destination / path.name).write_text(
                    path.read_text()
                    .replace("__EVALARC_VERSION__", version)
                    .replace("__AUDIT_COVERAGE__", coverage_cards(audits))
                    .replace("__TASK_PACK_COUNT__", str(len(audits)))
                    .replace("__FAULT_COUNT__", str(sum(a["total"] for a in audits.values())))
                )
            else:
                shutil.copyfile(path, destination / path.name)
    from scripts.strands_page import build_strands

    build_strands(ROOT, destination / "strands")
    for suffix in ("png", "gif", "mp4", "vtt"):
        name = f"first-review.{suffix}"
        shutil.copyfile(ROOT / "docs" / "assets" / name, destination / name)
    shutil.copyfile(
        ROOT / "docs/assets/first-review-media.json", destination / "first-review-media.json"
    )
    for name, directory, *_ in specifications:
        target = destination / name
        target.mkdir()
        # Render current, accessible UI from unchanged recorded evidence.
        from evalarc.report import render_audit

        shutil.copyfile(ROOT / "examples" / directory / "audit.json", target / "audit.json")
        render_audit(audits[name], target / "index.html")
        page = target / "index.html"
        page.write_bytes(page.read_text().encode("ascii", errors="xmlcharrefreplace"))
    for directory, filenames in (
        ("comparison", ("index.html", "comparison.json", "baseline.json", "current.json")),
        ("evaluation", ("index.html", "evaluation.json")),
    ):
        target = destination / directory
        target.mkdir()
        for filename in filenames:
            source = ROOT / "examples" / directory / filename
            if filename.endswith(".html"):
                (target / filename).write_bytes(
                    source.read_text().encode("ascii", errors="xmlcharrefreplace")
                )
            else:
                shutil.copyfile(source, target / filename)
    for name, directory in (("reference", "repetition"), ("faulty", "repetition-faulty")):
        source_root = ROOT / "examples" / directory
        for source in sorted(source_root.rglob("*")):
            if not source.is_file() or source.suffix not in (".html", ".json", ".jsonl"):
                continue
            target = destination / "repeat" / name / source.relative_to(source_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix == ".html":
                target.write_bytes(source.read_text().encode("ascii", errors="xmlcharrefreplace"))
            else:
                shutil.copyfile(source, target)
    source_root = ROOT / "examples" / "suite"
    for source in sorted(source_root.rglob("*")):
        if not source.is_file() or source.suffix not in (
            ".html",
            ".json",
            ".jsonl",
            ".xml",
            ".toml",
        ):
            continue
        target = destination / "suite" / source.relative_to(source_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix == ".html":
            target.write_bytes(source.read_text().encode("ascii", errors="xmlcharrefreplace"))
        else:
            shutil.copyfile(source, target)
    write_suite_bundle(destination / "suite-evidence.zip")
    from scripts.verify_research import verify_lab, verify_records

    verify_lab(ROOT / "examples/skill-impact")
    verify_records(ROOT / "examples/research")
    shutil.copytree(ROOT / "examples/skill-impact", destination / "skill-impact")
    shutil.copytree(ROOT / "examples/research", destination / "research")
    for lab in ("skill-impact", "research"):
        explicit_lab_navigation(destination / lab, commit)
    verify_lab(destination / "skill-impact")
    verify_records(destination / "research")
    from scripts.build_harbor_controls import verify_bundle as verify_harbor_controls

    verify_harbor_controls(ROOT / "examples/harbor-controls")
    shutil.copytree(ROOT / "examples/harbor-controls", destination / "harbor-controls")
    verify_harbor_controls(destination / "harbor-controls")
    from scripts.build_context_collection import verify as verify_context_controls

    verify_context_controls(ROOT / "examples/context-controls")
    shutil.copytree(ROOT / "examples/context-controls", destination / "context-controls")
    verify_context_controls(destination / "context-controls")
    from scripts.build_handoff_mcp import verify_bundle as verify_handoff

    verify_handoff(ROOT / "examples/funes-handoff")
    shutil.copytree(ROOT / "examples/funes-handoff", destination / "funes-handoff")
    verify_handoff(destination / "funes-handoff")
    from scripts.build_skill_handoff import verify_bundle as verify_skill_handoff

    verify_skill_handoff(ROOT / "examples/skill-handoff")
    shutil.copytree(ROOT / "examples/skill-handoff", destination / "skill-handoff")
    verify_skill_handoff(destination / "skill-handoff")
    from scripts.build_behavior_site import build as build_behavior

    build_behavior(ROOT / "examples/behavior-audit", destination / "behavior-audit")
    from evalarc.trace_review import import_trace

    trace_examples = ROOT / "examples/trace-workbench"
    import_trace(
        trace_examples / "current.json",
        destination / "trace-workbench",
        trace_examples / "baseline.json",
    )
    import_trace(trace_examples / "mcp-recorded.json", destination / "trace-mcp")
    from evalarc.judge_stability import import_judgments, verify_judgments

    judge_folder = destination / "judge-stability"
    judge = import_judgments(
        [ROOT / f"examples/judge-stability/judge-{index}.json" for index in (1, 2, 3)],
        judge_folder,
    )
    verify_judgments(judge_folder)
    with zipfile.ZipFile(
        destination / "judge-stability-evidence.zip", "x", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for source in sorted(judge_folder.rglob("*")):
            if source.is_file():
                name = "judge-stability/" + source.relative_to(judge_folder).as_posix()
                member = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
                member.compress_type = zipfile.ZIP_DEFLATED
                member.create_system = 3
                member.external_attr = 0o100644 << 16
                archive.writestr(member, source.read_bytes())
    preview = []
    for case in judge["cases"]:
        row = case["targets"][0]
        cells = []
        for observation in row["observations"]:
            assessed = observation["status"] == "assessed"
            state = ("pass" if observation["accepted"] else "fail") if assessed else "unknown"
            value = observation["value"] if assessed else observation["status"]
            cells.append(f'<td><span class="badge {state}">{html.escape(str(value))}</span></td>')
        preview.append(
            f'<tr><th scope="row">{html.escape(case["case_id"])}</th>{"".join(cells)}</tr>'
        )
    page = destination / "index.html"
    page.write_text(page.read_text().replace("__JUDGE_PREVIEW__", "".join(preview)))
    shutil.copyfile(ROOT / "LICENSE", destination / "LICENSE")
    shutil.copyfile(ROOT / "huggingface" / "README.md", destination / "README.md")
    (destination / ".nojekyll").touch()
    record = {
        "schema": "evalarc.site.v1",
        "source_repository": SOURCE,
        "source_commit": commit,
        "source_dirty": dirty,
        "evidence": (
            "Scripted grader controls and separately labeled recorded GPU model pilots; "
            "no live inference."
        ),
        "files": {
            path.relative_to(destination).as_posix(): sha256(path)
            for path in sorted(destination.rglob("*"))
            if path.is_file()
        },
    }
    (destination / MANIFEST).write_text(json.dumps(record, indent=2) + "\n")
    return verify(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))

"""Publish explicitly selected public development records, never agent history."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import zipfile
from pathlib import Path

from evalarc.artifact_review import review

FOLDERS = (
    "skill-composition-pilot",
    "handoff-continuation",
    "harbor-import-oracle",
    "harbor-import-oracle-retry",
    "skill-impact-matched",
    "skill-impact-contract-inline",
    "skill-impact-catalog-fallback",
)
SECRET = re.compile(
    rb"(?:hf_[A-Za-z0-9]{25,}|gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{25,})"
)


def build(source: Path, output: Path):
    output.mkdir(parents=True, exist_ok=False)
    for folder in FOLDERS:
        for path in sorted((source / folder).rglob("*")):
            if path.is_symlink():
                raise ValueError("public records must not contain symlinks")
            if not path.is_file():
                continue
            if path.suffix not in (".json", ".jsonl", ".py", ".js", ".mjs", ".txt", ".md"):
                raise ValueError(f"unexpected public record type: {path.name}")
            raw = path.read_bytes()
            if len(raw) > 16 * 1024 * 1024 or SECRET.search(raw):
                raise ValueError("oversized record or credential-shaped content")
            target = output / folder / path.relative_to(source / folder)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
    composition = json.loads((output / "skill-composition-pilot/summary.json").read_text())
    handoff = json.loads((output / "handoff-continuation/summary.json").read_text())
    if len(composition["trials"]) != 12 or len(handoff["trials"]) != 6:
        raise ValueError("retain every preselected trial")
    for path in (output / "skill-composition-pilot").glob("*/trial.json"):
        trial = json.loads(path.read_text())
        if review(path.parent / "candidate") != trial["independent_review"]:
            raise ValueError("composition outcome differs from retained artifacts")
    for row in handoff["trials"]:
        path = output / "handoff-continuation" / row["path"]
        grade = json.loads((path / "evaluation.json").read_text())
        if row["evaluation"] != {k: grade[k] for k in ("valid", "resolved", "score", "status")}:
            raise ValueError("handoff summary differs from independent evaluation")
    funes = output / "funes"
    funes.mkdir()
    for name in ("prior-session.parquet", "recall.txt"):
        shutil.copyfile(source / "handoff-pilot" / name, funes / name)
    (funes / "README.md").write_text(
        "Funes 1.3.0 indexed one explicitly selected public Qwen3-8B session into 31 chunks. "
        "Recall returned four hits, k=4, neighbors=0, half-life=0. "
        "The Parquet contains session_id and a list of serialized messages. Funes imports "
        "these as text; dedicated tool-result blocks are not reconstructed. "
        "No personal coding-agent history was read or published.\n"
    )
    for name in ("robot-oracle-fixed", "robot-nop-retry", "robot-oracle", "robot-nop"):
        target = output / "harbor-native" / name
        target.mkdir(parents=True)
        for path in (source / "harbor-jobs" / name).rglob("result.json"):
            rel = path.relative_to(source / "harbor-jobs" / name)
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
    for name in ("robot-audit-python", "robot-audit-javascript"):
        target = output / name
        target.mkdir()
        shutil.copyfile(source / name / "audit.json", target / "audit.json")
    rows = []
    for row in composition["trials"]:
        rows.append(
            f"<tr><td>{html.escape(row['condition'])}</td><td>{row['seed']}</td>"
            f"<td>{'Accepted' if row['accepted'] else 'Wrong output'}</td>"
            f"<td>{len(row['independent_review']['canary_in_public_files'])}</td></tr>"
        )
    continued = []
    for row in handoff["trials"]:
        continued.append(
            f"<tr><td>{html.escape(row['handoff_condition'])}</td><td>{row['seed']}</td>"
            f"<td>{row['evaluation']['score']:.1%}</td><td>"
            f"<a href='handoff-continuation/{row['path']}/trial.json'>Trial</a> · "
            f"<a href='handoff-continuation/{row['path']}/evaluation.json'>Grade</a></td></tr>"
        )
    (output / "index.html").write_text(
        PAGE.replace("__COMPOSITION__", "".join(rows)).replace("__HANDOFF__", "".join(continued))
    )
    for name in ("LICENSE",):
        shutil.copyfile(Path(__file__).parents[1] / name, output / name)
    shutil.copyfile(
        Path(__file__).parents[1] / "src/evalarc/assets/ROBOT_DATA_NOTICE.md",
        output / "ROBOT_DATA_NOTICE.md",
    )
    shutil.copyfile(
        Path(__file__).parents[1] / "src/evalarc/assets/ROBOT_DATA_LICENSE.txt",
        output / "ROBOT_DATA_LICENSE.txt",
    )
    with zipfile.ZipFile(output / "research-records.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob("*")):
            if path.is_file() and path.name != "research-records.zip":
                archive.writestr(path.relative_to(output).as_posix(), path.read_bytes())
    files = {
        p.relative_to(output).as_posix(): {
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "bytes": p.stat().st_size,
        }
        for p in sorted(output.rglob("*"))
        if p.is_file()
    }
    (output / "manifest.json").write_text(
        json.dumps({"schema": "evalarc.research-records.v1", "files": files}, indent=2) + "\n"
    )
    return {"files": len(files), "composition_trials": 12, "handoff_trials": 6}


PAGE = (Path(__file__).parents[1] / "site/labs/research.html").read_text()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output)))

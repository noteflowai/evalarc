"""Package recorded Harbor controls with linked raw evidence and an offline report."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from evalarc.interop import inspect_atif
from evalarc.robot_task import DIMENSIONS, generate_cases
from evalarc.robot_task import verify as check_answer
from evalarc.runner import snapshot
from evalarc.verify import verify as verify_evaluation

CONTROLS = ("reference", "clock-fault", "detached-answers")
SECRET = re.compile(
    rb"(?:hf_[A-Za-z0-9]{25,}|gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{25,})"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def document(path: Path) -> dict:
    return json.loads(path.read_text())


def checked_rows(root: Path) -> list[dict]:
    plan = document(root / "plan.json")
    summary = document(root / "summary.json")
    if (
        plan["schema"] != "evalarc.harbor-controls-plan.v1"
        or plan["harbor_version"] != "0.23.0"
        or plan["task_version"] != "0.2.0"
        or plan["evaluation_seeds"] != [41, 97]
        or plan["controls"] != list(CONTROLS)
        or summary["schema"] != "evalarc.harbor-controls.v1"
        or [r["control"] for r in summary["runs"]] != list(CONTROLS)
    ):
        raise ValueError("unexpected control plan or missing run")
    for name, expected in plan["harness_files"].items():
        if Path(name).name != name or digest(root / "harness" / name) != expected:
            raise ValueError("recorded harness identity differs")
    cases = [case for seed in plan["evaluation_seeds"] for case in generate_cases(seed)]
    for row in summary["runs"]:
        trial_rel = Path(row["trial_path"])
        import_rel = Path(row["import_path"])
        if any(p.is_absolute() or ".." in p.parts for p in (trial_rel, import_rel)):
            raise ValueError("unsafe evidence path")
        trial, imported = root / trial_rel, root / import_rel
        native = document(trial / "result.json")
        report = document(imported / "harbor-import.json")
        evaluation = document(imported / "evaluation.json")
        verify_evaluation(imported / "evaluation.json")
        with tempfile.TemporaryDirectory(prefix="evalarc-harbor-review-") as temporary:
            candidate_hash = snapshot(trial / "artifacts/candidate", Path(temporary) / "candidate")
        if candidate_hash != evaluation["candidate_sha256"]:
            raise ValueError("independent evaluation belongs to a different collected program")
        trajectory = document(trial / "agent/trajectory.json")
        inspect_atif(trajectory)
        if (
            row["return_code"] != 0
            or native["exception_info"] is not None
            or native["finished_at"] is None
            or native["config"]["environment"]["type"] != "docker"
            or native["verifier_environment_mode"] != "separate"
            or trajectory["agent"]["extra"]["control"] != row["control"]
            or trajectory["agent"]["extra"]["model_inference"] is not False
        ):
            raise ValueError("missing completed native control")
        for source, copied, expected in (
            (trial / "result.json", imported / "source-result.json", row["source_result_sha256"]),
            (
                trial / "agent/trajectory.json",
                imported / "source-trajectory.json",
                row["source_trajectory_sha256"],
            ),
        ):
            if digest(source) != expected or source.read_bytes() != copied.read_bytes():
                raise ValueError("raw source identity differs")
        outputs = [
            json.loads(step["observation"]["results"][0]["content"])
            for step in trajectory["steps"][1:]
        ]
        if any(output["return_code"] != 0 for output in outputs):
            raise ValueError("recorded command failed")
        if json.loads(outputs[0]["stdout"])["uid"] == 0:
            raise ValueError("control ran as root")
        final = json.loads(outputs[-1]["stdout"])
        if (
            digest(trial / "artifacts/candidate/main.py") != row["candidate_file_sha256"]
            or final["main.py"] != row["candidate_file_sha256"]
            or digest(trial / "artifacts/answers.jsonl") != row["answers_sha256"]
            or final["answers.jsonl"] != row["answers_sha256"]
        ):
            raise ValueError("collected files differ from executed container evidence")
        answers = [
            json.loads(line)
            for line in (trial / "artifacts/answers.jsonl").read_text().splitlines()
        ]
        if len(answers) != len(cases):
            raise ValueError("answer count differs")
        score = 0.0
        for case, answer in zip(cases, answers, strict=True):
            envelope = (
                isinstance(answer, dict)
                and set(answer) == {"ok", "report"}
                and answer["ok"] is True
            )
            checks = check_answer(case, answer.get("report"), envelope)
            score += sum(DIMENSIONS[key] for key, ok in checks.items() if ok) / len(cases)
        if (
            row["upstream_rewards"] != native["verifier_result"]["rewards"]
            or row["upstream_rewards"] != report["upstream"]["rewards"]
            or not math.isclose(row["upstream_rewards"]["reward"], score, abs_tol=1e-12)
        ):
            raise ValueError("upstream reward differs from original answers")
        if (
            row["independent"] != report["independent"]
            or any(
                row["independent"][key] != evaluation[key]
                for key in ("valid", "resolved", "score", "status", "candidate_sha256")
            )
            or row["acceptance"] != report["acceptance"]
            or report["acceptance"]["minimum_independent_score"] != 1.0
            or report["acceptance"]["accepted"]
            != (evaluation["valid"] and evaluation["score"] >= 1)
        ):
            raise ValueError("independent headline differs from evaluation")
    return summary["runs"]


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Harbor reward and program acceptance · EvalArc</title>
<style>
:root{color-scheme:dark}body{font:17px/1.65 system-ui,sans-serif;background:#101725;color:#e6ecf5;
max-width:1040px;margin:auto;padding:32px 20px}a{color:#8ee1dc}
a:focus-visible{outline:3px solid #ffc87d}
h1{font-size:clamp(30px,5vw,48px);line-height:1.2}h2{font-size:23px}p{max-width:80ch}
table{border-collapse:collapse;width:100%;min-width:620px}
th,td{text-align:left;padding:14px;border-bottom:1px solid #3c4961}
th{color:#b1c4dd}.table{overflow-x:auto}code{overflow-wrap:anywhere}strong{color:#ffc87d}
.note{padding:16px 20px;background:#1c293c;border-left:4px solid #8ee1dc}li{margin:10px 0}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
</style></head><body>
<nav><a href="../">EvalArc</a> ·
<a href="harbor-controls.zip" download>Complete offline evidence</a></nav>
<h1>Correct answers. Incorrect delivered program.</h1>
<p>Harbor checks the saved answer file. EvalArc separately runs the delivered program.
These three scripted controls show why the two results need distinct meanings.</p>
<p class="note"><strong>Declared controls, actual container executions.</strong>
Harbor 0.23.0; non-root agent; separate verifier container; eight public requests.
No model inference, hidden test, or model capability ranking.</p>
<div class="table" role="region" aria-label="Recorded control outcomes" tabindex="0">
<table><caption>Answer-file reward and independent program results</caption>
<thead><tr><th scope="col">Control</th><th scope="col">Harbor reward</th>
<th scope="col">Program score</th><th scope="col">All checks pass</th><th scope="col">Accepted</th>
<th scope="col">Evidence</th></tr></thead><tbody>__ROWS__</tbody></table></div>
<h2>What changes between controls</h2>
<ol><li><b>Reference:</b> the correct program generates its own answer file.</li>
<li><b>Clock fault:</b> the program treats raw sensor ticks as seconds.
World-clock cases pass; offset-clock cases fail time and derived error checks.</li>
<li><b>Detached answers:</b> the correct program writes the answers, then the fixture
replaces the delivered program with the clock-fault version. The recorded commands
and final hashes show exactly when the files diverge.</li></ol>
<p>Partial credit uses the task's six published dimension weights. Version 0.2.0
introduces weighted answer scoring; the earlier 0.1.0 task retains its all-or-nothing reward.
Independent acceptance here requires a valid program evaluation with score 1.0.</p>
<h2>Inspect and reproduce</h2>
<p><a href="summary.json">Summary</a> · <a href="plan.json">Preselected plan</a> ·
<a href="manifest.json">File identities</a> · <a href="task/instruction.md">Task contract</a> ·
<a href="task/task.toml">Harbor task</a> · <a href="README.md">Commands and scope</a></p>
<p>The full upstream ATIF schema was checked in the recorded runtime. The offline
packager checks source identity, tool linkage, recorded commands, answer scoring
and evaluation consistency. It does not re-execute a program just by opening this page.</p>
<p>This demonstrates the stated task's answer-only verification boundary.
It is not an exploit of Harbor isolation or evidence about unseen reward hacking.</p>
</body></html>
"""


def build(source: Path, output: Path) -> dict:
    rows = checked_rows(source)
    output.mkdir(parents=True, exist_ok=False)
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError("symlinks are not public evidence")
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        data = path.read_bytes()
        if len(data) > 16 * 1024 * 1024 or SECRET.search(data):
            raise ValueError("oversized file or credential-shaped text")
        target = output / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    rendered = []
    for row in rows:
        trial, imported = row["trial_path"], row["import_path"]
        links = (
            f'<a href="{trial}/agent/trajectory.json">ATIF</a> · '
            f'<a href="{trial}/artifacts/candidate/main.py">Program</a> · '
            f'<a href="{trial}/artifacts/answers.jsonl">Answers</a> · '
            f'<a href="{imported}/harbor-import.json">Import</a> · '
            f'<a href="{imported}/evaluation.json">Grade</a>'
        )
        rendered.append(
            f'<tr><th scope="row">{html.escape(row["control"])}</th>'
            f"<td>{row['upstream_rewards']['reward']:.0%}</td>"
            f"<td>{row['independent']['score']:.0%}</td>"
            f"<td>{'Yes' if row['independent']['resolved'] else 'No'}</td>"
            f"<td>{'Yes' if row['acceptance']['accepted'] else 'No'}</td><td>{links}</td></tr>"
        )
    (output / "index.html").write_text(PAGE.replace("__ROWS__", "".join(rendered)))
    root = Path(__file__).resolve().parents[1]
    for name in ("LICENSE",):
        shutil.copyfile(root / name, output / name)
    for name in ("ROBOT_DATA_LICENSE.txt", "ROBOT_DATA_NOTICE.md"):
        shutil.copyfile(root / "src/evalarc/assets" / name, output / name)
    with zipfile.ZipFile(output / "harbor-controls.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob("*")):
            if path.is_file() and path.name != "harbor-controls.zip":
                info = zipfile.ZipInfo(path.relative_to(output).as_posix(), (2026, 9, 19, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (0o755 if path.suffix == ".sh" else 0o644) << 16
                archive.writestr(info, path.read_bytes())
    manifest = {
        "schema": "evalarc.harbor-controls-bundle.v1",
        "files": {
            p.relative_to(output).as_posix(): {"sha256": digest(p), "bytes": p.stat().st_size}
            for p in sorted(output.rglob("*"))
            if p.is_file()
        },
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    verify_bundle(output)
    return {"controls": len(rows), "files": len(manifest["files"])}


def verify_bundle(root: Path) -> dict:
    manifest = document(root / "manifest.json")
    if manifest["schema"] != "evalarc.harbor-controls-bundle.v1":
        raise ValueError("unknown Harbor control bundle")
    files = manifest["files"]
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != set(files) | {"manifest.json"} or any(p.is_symlink() for p in root.rglob("*")):
        raise ValueError("control bundle inventory differs")
    for name, identity in files.items():
        path = root / name
        if identity != {"sha256": digest(path), "bytes": path.stat().st_size}:
            raise ValueError(f"control bundle file differs: {name}")
    with zipfile.ZipFile(root / "harbor-controls.zip") as archive:
        names = archive.namelist()
        expected = set(files) - {"harbor-controls.zip"}
        if len(names) != len(set(names)) or set(names) != expected:
            raise ValueError("offline archive inventory differs")
        for name in names:
            if archive.read(name) != (root / name).read_bytes():
                raise ValueError("offline archive differs from public evidence")
    return {"controls": len(checked_rows(root)), "files": len(files)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(verify_bundle(args.output) if args.verify else build(args.source, args.output))
    )

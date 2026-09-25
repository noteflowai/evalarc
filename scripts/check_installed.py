"""Exercise the installed verifier outside the checkout, with no tools on PATH."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from importlib.metadata import version
from pathlib import Path


def check(source: Path) -> dict:
    import evalarc

    source = source.resolve()
    module = Path(evalarc.__file__).resolve()
    if module.is_relative_to(source) or Path.cwd().is_relative_to(source):
        raise ValueError("use a non-editable wheel installation outside the checkout")
    expected = tomllib.loads((source / "pyproject.toml").read_text())["project"]["version"]
    if version("evalarc") != expected:
        raise ValueError("installed version differs from the source")
    if evalarc.__version__ != expected:
        raise ValueError("runtime version differs from installed metadata")
    results = {}
    with tempfile.TemporaryDirectory(prefix="evalarc-handoff-") as temporary:
        folder = Path(temporary)
        environment = {**os.environ, "PATH": "", "PYTHONPATH": "", "PYTHONNOUSERSITE": "1"}
        entry = str(Path(sys.executable).with_name("evalarc"))
        model_reports = source / "examples/model-upgrade/reports"
        expected_diff = json.loads((model_reports / "comparison.json").read_text())
        diff_output = folder / "model-diff"
        model_diff = subprocess.run(
            [
                entry,
                "diff",
                str(model_reports / "baseline.xml"),
                str(model_reports / "current.xml"),
                "--output",
                str(diff_output),
            ],
            cwd=folder,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if model_diff.returncode != (0 if expected_diff["gate_passed"] else 1):
            raise ValueError("Installed model diff returned the wrong gate result")
        actual_diff = json.loads((diff_output / "diff.json").read_text())
        if actual_diff["counts"] != expected_diff["counts"]:
            raise ValueError("Installed model diff changed the recorded check counts")
        results["model_configuration_diff"] = {
            "counts": actual_diff["counts"],
            "gate_passed": actual_diff["gate_passed"],
        }

        def run(path: Path, code: int, *extra: str) -> dict:
            process = subprocess.run(
                [entry, "verify", str(path), "--json", *extra],
                cwd=folder,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if process.returncode != code:
                raise ValueError(f"unexpected verifier exit: {process.stdout} {process.stderr}")
            return json.loads(process.stdout)

        def hashes() -> dict:
            return {
                p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.rglob("*")
                if p.is_file()
            }

        for name in ("evaluation", "repetition", "repetition-faulty", "comparison", "suite"):
            target = folder / name
            shutil.copytree(source / "examples" / name, target)
            before = hashes()
            result = run(target, 0)
            if not result["verified"] or hashes() != before:
                raise ValueError("verification failed or changed evidence")
            results[name] = result
        trace = folder / "trace-review"
        process = subprocess.run(
            [
                entry,
                "trace-import",
                str(source / "examples/trace-workbench/current.json"),
                "--output",
                str(trace),
            ],
            cwd=folder,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if process.returncode != 0:
            raise ValueError(f"installed trace import failed: {process.stderr}")
        process = subprocess.run(
            [entry, "trace-verify", str(trace)],
            cwd=folder,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if process.returncode != 0 or not json.loads(process.stdout)["verified"]:
            raise ValueError("installed trace verifier failed")
        results["trace"] = json.loads(process.stdout)
        judge = folder / "judge-stability"
        process = subprocess.run(
            [
                entry,
                "trace-stability",
                *[str(source / f"examples/judge-stability/judge-{i}.json") for i in (1, 2, 3)],
                "--output",
                str(judge),
                "--require-consistent-gates",
            ],
            cwd=folder,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if process.returncode != 2:
            raise ValueError("installed judge review lost its incomplete assessment gate")
        process = subprocess.run(
            [entry, "trace-stability-verify", str(judge)],
            cwd=folder,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if process.returncode != 0 or not json.loads(process.stdout)["verified"]:
            raise ValueError("installed judge verifier failed")
        results["judge_stability"] = json.loads(process.stdout)
        for name, expected_code, flags in (
            ("controls/reference", 0, []),
            ("controls/write-then-delete", 1, ["--require-accepted"]),
            ("pilot/07-composed-41", 2, []),
        ):
            target = folder / "behavior" / name
            shutil.copytree(source / "examples/behavior-audit" / name, target)
            before = hashes()
            process = subprocess.run(
                [entry, "behavior-review", str(target), "--json", *flags],
                cwd=folder,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if process.returncode != expected_code or hashes() != before:
                raise ValueError("installed behavior review failed or changed evidence")
            results["behavior/" + name] = json.loads(process.stdout)
        for language in ("python", "javascript"):
            target = folder / f"robot-{language}"
            subprocess.run(
                [
                    entry,
                    "init",
                    str(target),
                    "--task",
                    "robot-evidence-review",
                    "--reference",
                    "--language",
                    language,
                ],
                cwd=folder,
                env=environment,
                check=True,
                capture_output=True,
                timeout=30,
            )
            suffix = "py" if language == "python" else "js"
            expected_bytes = (source / f"src/evalarc/assets/robot_reference.{suffix}").read_bytes()
            if (target / f"main.{suffix}").read_bytes() != expected_bytes:
                raise ValueError("installed robot task reference differs from source")
        run(folder / "repetition", 0, "--require-resolved")
        run(folder / "repetition-faulty", 1, "--require-resolved")
        suite = run(folder / "suite", 1, "--require-accepted")
        if suite["accepted_jobs"] != 2 or suite["fully_resolved_jobs"] != 1:
            raise ValueError("suite acceptance and resolution were conflated")
        junit = folder / "suite" / "junit.xml"
        junit.write_text(
            junit.read_text().replace("<failure", "<error").replace("</failure", "</error")
        )
        if run(folder / "suite", 2)["verified"]:
            raise ValueError("changed JUnit was accepted")
        changed = folder / "comparison" / "comparison.json"
        data = json.loads(changed.read_text())
        data["score_delta"] = 0.123
        changed.write_text(json.dumps(data))
        if run(changed, 2)["verified"]:
            raise ValueError("changed summary was accepted")
    return {"version": expected, "module": str(module), "path_empty": True, "verified": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    print(json.dumps(check(parser.parse_args().source), indent=2))

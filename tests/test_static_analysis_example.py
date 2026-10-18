"""The documented static-analysis recipe: stable analyzer checks gate with evalarc diff."""

import os
import subprocess
import sys
from pathlib import Path

from evalarc.cli import main
from evalarc.results_diff import load_results

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/static-analysis/test_static_analysis.py"


def report(tmp_path, name, source):
    target = tmp_path / name
    target.mkdir()
    (target / "app.py").write_text(source)
    xml = tmp_path / f"{name}.xml"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            str(EXAMPLE),
            "--target",
            str(target),
            f"--junitxml={xml}",
            "--rootdir",
            str(EXAMPLE.parent),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=EXAMPLE.parent,
        # Keep bytecode out of the source tree; everything else is written under tmp_path.
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return xml


def test_a_new_lint_violation_fails_the_diff_gate(tmp_path, capsys):
    clean = 'def route(ticket):\n    return "billing" if "refund" in ticket else "general"\n'
    dirty = "import os\n\n\n" + clean
    baseline = report(tmp_path, "baseline", clean)
    current = report(tmp_path, "current", dirty)
    checks = {case: next(iter(c.values())) for case, c in load_results(current)["cases"].items()}
    lint = next(case for case in checks if case.endswith("::test_ruff_lint"))
    assert checks[lint][0]["passed"] is False
    assert main(["diff", str(baseline), str(current)]) == 1
    assert "regressed:" in capsys.readouterr().out
    assert main(["diff", str(baseline), str(report(tmp_path, "same", clean))]) == 0

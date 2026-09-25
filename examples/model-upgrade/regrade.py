"""Produce real pytest JUnit files and an EvalArc diff from preserved generations."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

from evalarc.results_diff import diff, load_results, render_html, render_markdown


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-native-output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    args.output.mkdir(parents=True, exist_ok=False)
    if args.private_native_output:
        args.private_native_output.mkdir(parents=True, exist_ok=False)
    redactions = {
        "scope": [
            'Native JUnit hostname attributes replaced with "redacted".',
            "Absolute report directory in pytest stdout replaced with [report-directory].",
            "Model answers and named check outcomes are unchanged.",
        ],
        "files": {},
    }

    def publish_native(name: str, original: bytes, published: bytes) -> None:
        if args.private_native_output:
            (args.private_native_output / name).write_bytes(original)
        (args.output / name).write_bytes(published)
        redactions["files"][name] = {
            "native_sha256": hashlib.sha256(original).hexdigest(),
            "published_sha256": hashlib.sha256(published).hexdigest(),
        }

    protocol = json.loads((root / "protocol.json").read_text())
    for label in ("baseline", "current"):
        suites = ET.Element("testsuites")
        for seed in protocol["seeds"]:
            output = (args.output / f"{label}-{seed}.xml").resolve()
            env = {
                **os.environ,
                "MODEL_RECORD": str(root / "recorded" / label),
                "MODEL_SEED": str(seed),
            }
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    "-c",
                    "/dev/null",
                    "--rootdir=.",
                    "model_checks.py",
                    f"--junitxml={output}",
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
            )
            if completed.returncode not in (0, 1):
                raise RuntimeError(completed.stdout + completed.stderr)
            text = completed.stdout + completed.stderr
            publish_native(
                f"{label}-{seed}.txt",
                text.encode(),
                text.replace(str(output.parent), "[report-directory]").encode(),
            )
            xml = output.read_bytes()
            publish_native(
                output.name,
                xml,
                re.sub(rb' hostname="[^"]*"', b' hostname="redacted"', xml),
            )
            # Only host metadata is redacted. The combined file concatenates
            # native suites; repeated names become repeated attempts in EvalArc.
            for suite in ET.parse(output).getroot():
                suites.append(suite)
        ET.ElementTree(suites).write(
            args.output / f"{label}.xml", encoding="utf-8", xml_declaration=True
        )
    (args.output / "redactions.json").write_text(json.dumps(redactions, indent=2) + "\n")
    result = diff(
        load_results(args.output / "baseline.xml"), load_results(args.output / "current.xml")
    )
    (args.output / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    (args.output / "comparison.md").write_text(render_markdown(result))
    render_html(result, args.output / "index.html")
    print(render_markdown(result))


if __name__ == "__main__":
    main()

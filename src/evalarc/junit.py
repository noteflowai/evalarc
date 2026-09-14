"""JUnit XML for suite acceptance gates, with environment errors kept distinct."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path


def _xml_text(value: str) -> str:
    return "".join(
        char
        if (
            char in "\t\n\r"
            or 0x20 <= ord(char) <= 0xD7FF
            or 0xE000 <= ord(char) <= 0xFFFD
            or 0x10000 <= ord(char) <= 0x10FFFF
        )
        else "\ufffd"
        for char in value
    )


def render_junit(data: dict, destination: Path) -> None:
    jobs = data["jobs"]
    failures = sum(row["decision"]["valid"] and not row["decision"]["accepted"] for row in jobs)
    errors = sum(not row["decision"]["valid"] for row in jobs)
    attributes = {
        "name": _xml_text(data["name"]),
        "tests": str(len(jobs)),
        "failures": str(failures),
        "errors": str(errors),
        "skipped": "0",
        "time": f"{sum(row['duration_seconds'] for row in jobs):.6f}",
    }
    root = ET.Element("testsuites", attributes)
    suite = ET.SubElement(root, "testsuite", attributes)
    for row in jobs:
        case = ET.SubElement(
            suite,
            "testcase",
            {
                "classname": f"evalarc.{row['task']['id']}",
                "name": row["id"],
                "time": f"{row['duration_seconds']:.6f}",
            },
        )
        if not row["decision"]["accepted"]:
            kind = "failure" if row["decision"]["valid"] else "error"
            message = _xml_text("\n".join(row["decision"]["reasons"]))
            node = ET.SubElement(
                case,
                kind,
                {
                    "message": message,
                    "type": "AcceptanceGate" if kind == "failure" else "EnvironmentFailure",
                },
            )
            node.text = message
        output = ET.SubElement(case, "system-out")
        output.text = _xml_text(
            json.dumps(
                {
                    "fully_resolved": row["fully_resolved"],
                    "observed": row["observed"],
                    "gate": row["gate"],
                    "evidence": f"jobs/{row['id']}/index.html",
                },
                ensure_ascii=True,
                allow_nan=False,
            )
        )
    ET.indent(root, space="  ")
    destination.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(destination, encoding="utf-8", xml_declaration=True)

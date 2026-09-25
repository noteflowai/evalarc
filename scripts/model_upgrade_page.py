"""Build a browsable, offline model configuration comparison from preserved outputs."""

from __future__ import annotations

import hashlib
import json
import runpy
import shutil
import zipfile
from pathlib import Path

from evalarc.results_diff import diff, load_results


def evidence(root: Path) -> dict:
    source = root / "examples/model-upgrade"
    protocol = json.loads((source / "protocol.json").read_text())
    declared = runpy.run_path(str(source / "protocol.py"))
    if declared["PROTOCOL"] != protocol:
        raise ValueError("Frozen protocol changed")
    saved = json.loads((source / "reports/comparison.json").read_text())
    actual = diff(
        load_results(source / "reports/baseline.xml"), load_results(source / "reports/current.xml")
    )
    for result in (saved, actual):
        result.pop("created_at", None)
    if saved != actual:
        raise ValueError("Saved comparison differs from native result files")
    records, identities, totals = {}, {}, {}
    expected_files = {
        f"{case['id']}-{seed}.json" for case in protocol["cases"] for seed in protocol["seeds"]
    }
    digest = hashlib.sha256((source / "protocol.json").read_bytes()).hexdigest()
    for label in ("baseline", "current"):
        folder = source / "recorded" / label
        found = {p.name for p in folder.glob("*.json")} - {"identity.json", "protocol.json"}
        if (
            found != expected_files
            or (folder / "protocol.json").read_bytes() != (source / "protocol.json").read_bytes()
        ):
            raise ValueError("Output inventory or protocol differs")
        identities[label] = json.loads((folder / "identity.json").read_text())
        records[label], totals[label] = {}, 0
        for case, expected in zip(protocol["cases"], declared["EXPECTED"]):
            for seed in protocol["seeds"]:
                name = f"{case['id']}-{seed}"
                record = json.loads((folder / f"{name}.json").read_text())
                if (
                    record["protocol_sha256"] != digest
                    or record["seed"] != seed
                    or record["case_id"] != case["id"]
                ):
                    raise ValueError("Generation identity differs")
                try:
                    passed = json.loads(record["text"]) == {"actions": expected}
                except (ValueError, TypeError):
                    passed = False
                totals[label] += int(passed)
                records[label][name] = {"record": record, "complete_plan": passed}
    return {
        "schema": "evalarc-model-upgrade-page-1",
        "protocol": protocol,
        "records": records,
        "identities": identities,
        "complete_plans": totals,
        "comparison": saved,
    }


def build_model_upgrade(root: Path, destination: Path) -> None:
    source = root / "examples/model-upgrade"
    data = evidence(root)
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    payload = json.dumps(data, ensure_ascii=True).replace("<", "\\u003c")
    (destination / "index.html").write_text(
        (root / "scripts/model_upgrade.html").read_text().replace("__MODEL_DATA__", payload)
    )
    (destination / "review.json").write_text(json.dumps(data, indent=2) + "\n")
    with zipfile.ZipFile(
        destination / "review.zip", "x", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for path in sorted(destination.rglob("*")):
            if path.is_file() and path.name != "review.zip":
                info = zipfile.ZipInfo(
                    path.relative_to(destination).as_posix(), (2020, 1, 1, 0, 0, 0)
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())

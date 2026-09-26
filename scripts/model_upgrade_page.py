"""Build a browsable, offline model configuration comparison from preserved outputs."""

from __future__ import annotations

import hashlib
import html
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


def homepage_proof(root: Path) -> str:
    """Render the entry point from the same verified records as the full review."""
    data = evidence(root)
    seeds = data["protocol"]["seeds"]
    total = len(data["protocol"]["cases"]) * len(seeds)
    before, after = (data["complete_plans"][label] for label in ("baseline", "current"))
    first = f"already-closed-{seeds[0]}"
    outputs = {
        str(seed): {
            label: data["records"][label][f"already-closed-{seed}"]["record"]["text"]
            for label in ("baseline", "current")
        }
        for seed in seeds
    }
    payload = json.dumps(
        {
            "before": before,
            "after": after,
            "total": total,
            "blocking": data["comparison"]["blocking_changes"],
            "outputs": outputs,
        },
        ensure_ascii=True,
    ).replace("<", "\\u003c")
    buttons = "".join(
        f'<button type="button" data-model-seed="{seed}" '
        f'aria-pressed="{str(index == 0).lower()}">{seed}</button>'
        for index, seed in enumerate(seeds)
    )
    baseline = html.escape(data["records"]["baseline"][first]["record"]["text"])
    current = html.escape(data["records"]["current"][first]["record"]["text"])
    return f"""
<div class="model-proof" aria-labelledby="proof-title">
  <div class="proof-top">
<span id="proof-title">QWEN / RECORDED MODEL UPGRADE</span>
<span class="badge fail">GATE FAILED</span>
</div>
  <div class="model-scores">
<div>
<span>Qwen3-8B · BF16</span>
<strong>{before}<small>/{total}</small>
</strong>
</div>
<span class="model-arrow" aria-hidden="true">→</span>
<div>
<span>Qwen3.8-27B · FP8</span>
<strong>{after}<small>/{total}</small>
</strong>
</div>
</div>
  <p class="caption">Complete plans matching the contract · 8 cases × 3 generations</p>
  <div class="model-blockers">
<strong>{data["comparison"]["blocking_changes"]}</strong>
<span>named checks lost passes or coverage<br>Two shared format/schema failure causes</span>
</div>
  <div class="model-case">
<div class="model-case-heading">
<span>CASE / already-closed</span>
<div role="group" aria-label="Recorded generation seed">
<span>Seed</span>{buttons}</div>
</div>
    <div class="model-output">
<div>
<span>Before</span>
<pre id="proof-before">{baseline}</pre>
</div>
<div>
<span>After</span>
<pre id="proof-after">{current}</pre>
</div>
</div>
    <p id="proof-caption" class="caption" aria-live="polite">Seed {seeds[0]} ·
The required actions field is missing.</p>
  </div>
  <div class="model-proof-actions">
<a id="proof-open"
 href="model-upgrade/index.html#case=already-closed&amp;seed={seeds[0]}">Inspect this output →</a>
<button id="proof-image" type="button" hidden>Save result image</button>
</div>
  <p class="caption model-scope">Selected public cases; plans not executed.
Model size and quantization differ.</p>
  <p id="proof-image-status" class="caption" role="status">
</p>
</div>
<script id="model-proof-data" type="application/json">{payload}</script>"""

"""Export an explicitly selected public pilot trial to Funes' Parquet trace contract.

Requires pyarrow. This reads one named trial; it does not discover agent histories,
index local memories, or publish a dataset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.suffix != ".parquet":
        parser.error("choose a new .parquet output")
    if args.trial.is_symlink() or args.trial.stat().st_size > 16 * 1024 * 1024:
        parser.error("trial must be a bounded regular file")
    raw = args.trial.read_bytes()
    trial = json.loads(raw)
    if trial.get("schema_version") != "evalarc.skill-impact-trial.v1":
        parser.error("expected the public skill-impact pilot trial schema")
    json.dumps(trial, allow_nan=False)
    source_sha = hashlib.sha256(raw).hexdigest()
    messages = trial["messages"]
    if not isinstance(messages, list) or not 2 <= len(messages) <= 1000:
        parser.error("expected bounded chat messages")
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in (
            "system",
            "user",
            "assistant",
            "tool",
        ):
            parser.error("unsupported chat message")
    import pyarrow as pa
    import pyarrow.parquet as pq

    schema = pa.schema(
        [
            ("session_id", pa.string()),
            ("messages", pa.list_(pa.string())),
            ("sent_at", pa.string()),
            ("harness", pa.string()),
            ("file_path", pa.string()),
            ("metadata", pa.string()),
        ]
    )
    row = {
        "session_id": "evalarc-public-" + source_sha[:24],
        "messages": [json.dumps(message, ensure_ascii=False) for message in messages],
        "sent_at": trial["created_at"],
        "harness": "evalarc_local_model_pilot",
        "file_path": f"public-pilot/{trial['condition']}-{trial['model_seed']}/trial.json",
        "metadata": json.dumps(
            {
                "cwd": "/public-demo/robot-recording-review",
                "source_sha256": source_sha,
                "model": trial["model"],
                "independent_evaluation": trial["independent_evaluation"],
                "provenance": (
                    "A generated public development experiment, not a private user session."
                ),
            }
        ),
    }
    pq.write_table(pa.Table.from_pylist([row], schema=schema), args.output)
    # Validate exact nested Arrow types and the lossless message round trip.
    loaded = pq.read_table(args.output)
    if loaded.schema != schema or loaded.to_pylist() != [row]:
        raise ValueError("Parquet round trip changed the trace")
    manifest = {
        "schema": "evalarc.funes-export.v1",
        "source_sha256": source_sha,
        "session_id": row["session_id"],
        "messages": len(messages),
        "parquet_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "pyarrow_version": pa.__version__,
        "contract": "Funes session_id Utf8 + messages List<Utf8>, optional string provenance",
        "limits": (
            "Funes currently represents string tool-message content as text; its Parquet "
            "importer does not reconstruct dedicated tool_result blocks. No native named-agent "
            "integration or publication is implied by this export."
        ),
    }
    args.output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()

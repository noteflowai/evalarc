import json

import pytest

from scripts.swe_dataset import build, check, digest


def test_resealed_dataset_cannot_change_an_outcome(tmp_path):
    folder = tmp_path / "dataset"
    build(folder)
    data = folder / "data/attempts.jsonl"
    rows = [json.loads(line) for line in data.read_text().splitlines()]
    rows[0]["disposition"] = "accepted"
    data.write_text("".join(json.dumps(row) + "\n" for row in rows))
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["data/attempts.jsonl"] = digest(data.read_bytes())
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="projections differ"):
        check(folder)

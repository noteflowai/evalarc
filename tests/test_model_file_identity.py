import hashlib
import json

import pytest

from scripts.local_model_server import verify_model_files


def test_load_identity_rejects_changed_bytes_extra_files_and_revision(tmp_path):
    directory = tmp_path / "model"
    directory.mkdir()
    weights = b"test-only model bytes"
    (directory / "model.safetensors").write_bytes(weights)
    proof = tmp_path / "proof.json"
    proof.write_text(
        json.dumps(
            {
                "model": "test-only",
                "revision": "a" * 40,
                "files": {
                    "model.safetensors": {
                        "sha256": hashlib.sha256(weights).hexdigest(),
                        "bytes": len(weights),
                    }
                },
            }
        )
    )
    assert (
        verify_model_files(directory, proof, "test-only", "a" * 40)
        == hashlib.sha256(proof.read_bytes()).hexdigest()
    )
    with pytest.raises(ValueError, match="identity differs"):
        verify_model_files(directory, proof, "test-only", "b" * 40)
    (directory / "adapter_config.json").write_text("{}")
    with pytest.raises(ValueError, match="inventory differs"):
        verify_model_files(directory, proof, "test-only", "a" * 40)
    (directory / "adapter_config.json").unlink()
    (directory / "model.safetensors").write_bytes(b"changed")
    with pytest.raises(ValueError, match="model file differs"):
        verify_model_files(directory, proof, "test-only", "a" * 40)

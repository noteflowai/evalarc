"""Publication succeeds only after every anonymous, revision-pinned read matches."""

import sys
import threading
from types import SimpleNamespace

import pytest

from scripts.hf_readback import verify_public_files

REVISION = "a" * 40


def test_all_files_are_checked_with_bounded_concurrency(tmp_path, monkeypatch, capsys):
    names = ["manifest.json", "README.md"] + [f"data/{i}.json" for i in range(10)]
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.write_text(name)
    barrier = threading.Barrier(4, timeout=10)
    lock = threading.Lock()
    calls = []
    active = peak = 0

    def download(repo_id, name, **kwargs):
        nonlocal active, peak
        with lock:
            calls.append((repo_id, name, kwargs))
            active += 1
            peak = max(peak, active)
            first_group = len(calls) <= 4
        try:
            if first_group:
                barrier.wait()
            return str(tmp_path / name)
        finally:
            with lock:
                active -= 1

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(hf_hub_download=download))
    count = verify_public_files(tmp_path, "owner/space", "space", REVISION, names)
    assert count == len(names)
    assert {name for _, name, _ in calls} == set(names)
    assert len(calls) == len(names)
    assert peak == 4
    assert all(
        repo == "owner/space"
        and options == {"repo_type": "space", "revision": REVISION, "token": False}
        for repo, _, options in calls
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "verified 12/12 files" in captured.err


@pytest.mark.parametrize("failure", ["corrupt", "missing", "network"])
def test_one_failed_file_prevents_publication_success(tmp_path, monkeypatch, capsys, failure):
    (tmp_path / "manifest.json").write_text("expected bytes")
    remote = tmp_path / "received.json"
    remote.write_text("changed bytes" if failure == "corrupt" else "expected bytes")

    def download(repo_id, name, **kwargs):
        assert kwargs == {"repo_type": "dataset", "revision": REVISION, "token": False}
        if failure == "missing":
            return str(tmp_path / "missing.json")
        if failure == "network":
            raise ConnectionError("download interrupted")
        return str(remote)

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(hf_hub_download=download))
    with pytest.raises(RuntimeError, match="manifest.json") as raised:
        verify_public_files(tmp_path, "owner/data", "dataset", REVISION, ["manifest.json"])
    expected = {
        "corrupt": ValueError,
        "missing": FileNotFoundError,
        "network": ConnectionError,
    }
    assert isinstance(raised.value.__cause__, expected[failure])
    assert "verified 1/1" not in capsys.readouterr().err


@pytest.mark.parametrize(
    ("revision", "names"),
    [
        ("main", ["manifest.json"]),
        ("a" * 7, ["manifest.json"]),
        (REVISION, []),
        (REVISION, ["../outside"]),
        (REVISION, ["/outside"]),
        (REVISION, ["..\\outside"]),
    ],
)
def test_invalid_revision_or_inventory_is_rejected_before_download(
    tmp_path, monkeypatch, revision, names
):
    def download(*args, **kwargs):
        pytest.fail("Invalid publication must not perform a download")

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(hf_hub_download=download))
    with pytest.raises(ValueError):
        verify_public_files(tmp_path, "owner/data", "dataset", revision, names)

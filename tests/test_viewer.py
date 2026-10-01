import http.client
import json
import threading
from pathlib import Path

import pytest

from evalarc.cli import main
from evalarc.report import CSP, ENHANCE, SCRIPT_HASH
from evalarc.viewer import discover, serve

ROOT = Path(__file__).resolve().parents[1]
INSPECT = ROOT / "examples/results-diff/inspect"


@pytest.fixture
def runs(tmp_path):
    runs = tmp_path / "runs"
    main(
        [
            "diff",
            str(INSPECT / "baseline.json"),
            str(INSPECT / "current.json"),
            "--output",
            str(runs / "diff"),
        ]
    )
    main(
        [
            "eval-health",
            str(INSPECT / "baseline.json"),
            str(INSPECT / "current.json"),
            "--output",
            str(runs / "nested/health"),
        ]
    )
    (runs / "notes").mkdir()
    (runs / "notes/index.html").write_text("<p>not a report</p>")
    return runs


@pytest.fixture
def server(runs):
    instance = serve(runs, 0, open_browser=False)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield instance.server_address[1]
    instance.shutdown()
    instance.server_close()


def get(port, path, host=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    connection.putrequest("GET", path, skip_host=True)
    connection.putheader("Host", host or f"127.0.0.1:{port}")
    connection.endheaders()
    response = connection.getresponse()
    return response.status, response.read().decode("utf-8", "replace"), dict(response.headers)


def test_discover_lists_reports_with_their_verdict(runs):
    reports = {row["path"]: row for row in discover(runs)}
    assert set(reports) == {"diff", "nested/health"}
    assert reports["diff"]["state"] == "fail" and "Gate failed" in reports["diff"]["title"]
    assert reports["nested/health"]["kind"] == "Eval health"


def test_index_and_reports_are_served_locally(server):
    status, page, headers = get(server, "/")
    assert status == 200 and "2 report(s)" in page and 'href="/diff/index.html"' in page
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    status, page, _ = get(server, "/diff/index.html")
    assert status == 200 and "Gate failed" in page
    assert get(server, "/diff/diff.json")[0] == 200


@pytest.mark.parametrize(
    "path,host,status",
    [
        ("/", "evil.example", 421),  # DNS rebinding: only loopback Host names are served
        ("/../../../etc/passwd", None, 404),
        ("/diff/", None, 200),  # folder with index.html
        ("/nested/", None, 404),  # no directory listings
        ("/missing.html", None, 404),
    ],
)
def test_server_boundaries(server, path, host, status):
    assert get(server, path, host)[0] == status


def test_write_index_uses_relative_links(runs, tmp_path, capsys):
    target = tmp_path / "site/index.html"
    target.parent.mkdir()
    assert main(["view", str(runs), "--write-index", str(target)]) == 0
    page = target.read_text()
    assert 'href="../runs/diff/index.html"' in page
    assert main(["view", str(tmp_path / "missing")]) == 2


def test_reports_allow_only_the_packaged_script(runs):
    page = (runs / "diff/index.html").read_text()
    assert f"'sha256-{SCRIPT_HASH}'" in CSP and CSP in page
    assert page.count('<script data-evalarc="enhance">') == 1 and ENHANCE in page
    assert "connect-src" not in CSP and "default-src 'none'" in CSP
    assert json.loads((runs / "diff/diff.json").read_text())["gate_passed"] is False

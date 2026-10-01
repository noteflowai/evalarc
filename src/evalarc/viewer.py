"""Browse every EvalArc report under a folder in the browser: ``evalarc view``.

The mainstream pattern for evaluation tools (``inspect view``, ``promptfoo view``,
``mlflow ui``) is a read-only local web server plus the user's browser, not a desktop
application. This viewer follows it with the standard library only: it binds to
127.0.0.1, serves files under one root, rejects other Host headers, and lists each
report folder with the verdict its page already states. ``--write-index`` writes the
same list as a static page for CI artifacts or GitHub Pages.
"""

from __future__ import annotations

import html
import http.server
import os
import re
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from evalarc.report import _esc, _page, _table

# Report JSON next to index.html identifies the report kind.
KINDS = {
    "diff.json": "Results diff",
    "health.json": "Eval health",
    "hillclimb.json": "Hillclimb review",
    "score.json": "Judge score",
    "review.json": "Input review",
    "evaluation.json": "Evaluation",
    "comparison.json": "Comparison",
    "repetition.json": "Repeatability",
    "suite.json": "Suite",
    "audit.json": "Grader audit",
    "decisions.json": "Decision coverage",
}
MAX_REPORTS = 5000
MAX_DEPTH = 6
VERDICT = re.compile(
    r'<section class="verdict (pass|fail|warn)"[^>]*><h2>(.*?)</h2>(?:<p>(.*?)</p>)?', re.S
)
DEFAULT_PORT = 7576


def discover(root: Path) -> list[dict]:
    """Report folders under root: index.html plus a known report JSON."""
    root = root.resolve()
    found = []
    for directory, subdirs, names in os.walk(root):
        path = Path(directory)
        depth = len(path.relative_to(root).parts)
        subdirs[:] = sorted(
            d for d in subdirs if not d.startswith(".") and d not in ("node_modules", "share")
        )
        if depth >= MAX_DEPTH:
            subdirs[:] = []
        if "index.html" not in names:
            continue
        kind = next((KINDS[name] for name in KINDS if name in names), None)
        if kind is None:
            continue
        page = path / "index.html"
        text = page.read_text(encoding="utf-8", errors="replace")[:200_000]
        match = VERDICT.search(text)
        state, title, detail = match.groups() if match else ("unknown", "", "")
        found.append(
            {
                "path": path.relative_to(root).as_posix() or ".",
                "kind": kind,
                "state": state,
                "title": _plain(title),
                "detail": _plain(detail or ""),
                "modified": page.stat().st_mtime,
            }
        )
        if len(found) >= MAX_REPORTS:
            break
    return sorted(found, key=lambda row: row["modified"], reverse=True)


def index_html(reports: list[dict], root_label: str, link_prefix: str = "") -> str:
    """The index page: one row per report, newest first, with its verdict."""
    import tempfile

    tone = {"pass": ("ok", "✓ pass"), "fail": ("bad", "✗ fail"), "warn": ("warn", "! check")}
    rows = []
    for row in reports:
        cls, label = tone.get(row["state"], ("info", "· no verdict"))
        href = quote(f"{link_prefix}{row['path']}/index.html".replace("./index.html", "index.html"))
        rows.append(
            [
                f'<span class="tone {cls}">{_esc(label)}</span>',
                f'<a href="{href}">{_esc(row["path"])}</a>',
                _esc(row["kind"]),
                _esc(row["title"])
                + (f"<br><small>{_esc(row['detail'])}</small>" if row["detail"] else ""),
            ]
        )
    failing = sum(row["state"] == "fail" for row in reports)
    summary = (
        f"<p>{len(reports)} report(s) under <code>{_esc(root_label)}</code>, newest first. "
        f"{failing} with a failing verdict.</p>"
    )
    body = summary + (
        _table("Reports", ["Verdict", "Report", "Kind", "Summary"], rows)
        if rows
        else "<p>No EvalArc reports found. Run a command with <code>--output</code> first.</p>"
    )
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / "index.html"
        _page("Reports", "Every report in one place.", body, target)
        return target.read_text(encoding="utf-8")


class _Handler(http.server.SimpleHTTPRequestHandler):
    root: Path
    allowed_hosts: set[str]
    label: str

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self.root), **kwargs)

    def log_message(self, *_):  # quiet by default; the URL is printed once
        pass

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def _allowed(self) -> bool:
        if self.headers.get("Host", "") not in self.allowed_hosts:
            self.send_error(421, "Unrecognized Host")
            return False
        path = Path(self.translate_path(urlsplit(self.path).path)).resolve()
        if not path.is_relative_to(self.root):
            self.send_error(404)
            return False
        return True

    def do_GET(self):
        if not self._allowed():
            return
        route = unquote(urlsplit(self.path).path)
        if route in ("/", "/index.html"):
            page = index_html(discover(self.root), self.label, "/").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
            return
        if (
            Path(self.translate_path(route)).is_dir()
            and not (Path(self.translate_path(route)) / "index.html").is_file()
        ):
            self.send_error(404)  # no directory listings
            return
        super().do_GET()

    def do_HEAD(self):
        if self._allowed():
            super().do_HEAD()

    def list_directory(self, path):  # never list folders
        self.send_error(404)
        return None


def serve(root: Path, port: int, open_browser: bool) -> http.server.ThreadingHTTPServer:
    root = root.resolve()
    handler = type(
        "Handler",
        (_Handler,),
        {
            "root": root,
            "label": str(root),
            "allowed_hosts": {f"127.0.0.1:{port}", f"localhost:{port}"},
        },
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    if port == 0:  # tests: learn the chosen port and allow it
        actual = server.server_address[1]
        handler.allowed_hosts = {f"127.0.0.1:{actual}", f"localhost:{actual}"}
    if open_browser:
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    return server


def command(args) -> int:
    root = args.directory
    if not root.is_dir():
        print(f"evalarc: {root} is not a directory", file=sys.stderr)
        return 2
    if args.write_index:
        target = args.write_index
        prefix = os.path.relpath(root.resolve(), target.resolve().parent).replace(os.sep, "/")
        prefix = "" if prefix == "." else prefix + "/"
        reports = discover(root)
        target.write_text(index_html(reports, str(root), prefix), encoding="utf-8")
        print(f"Wrote {target} listing {len(reports)} report(s)")
        return 0
    try:
        server = serve(root, args.port, not args.no_browser)
    except OSError as error:
        print(f"evalarc: cannot listen on 127.0.0.1:{args.port}: {error}", file=sys.stderr)
        return 2
    port = server.server_address[1]
    print(
        f"EvalArc reports at http://127.0.0.1:{port}/ (local only; Ctrl+C to stop)\n"
        f"For a remote machine: ssh -L {port}:127.0.0.1:{port} HOST",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _plain(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()

# Browse reports

Every EvalArc command that takes `--output` writes a self-contained HTML report.
`evalarc view` lists all of them under a folder with their verdicts and opens it
in your browser. [中文](viewer.zh-CN.md).

```bash
evalarc view runs            # http://127.0.0.1:7576/, opens a browser
evalarc view runs --port 8000 --no-browser
evalarc view runs --write-index site/index.html   # static index for CI artifacts or Pages
```

The index shows each report folder (newest first) with its verdict (✓ pass,
✗ fail, ! check), kind and summary, read from the verdict banner the report
already contains. It sorts and filters like every report table.

## Why a local viewer, not a desktop app

Evaluation tools converge on the same pattern: a read-only local web server plus
the browser you already have (`inspect view`, `promptfoo view`, `mlflow ui`),
with an IDE extension where tighter integration is needed (Inspect's VS Code
extension), and a static bundle for sharing (`inspect view bundle`,
`promptfoo eval -o report.html`). A desktop shell (Electron, Tauri) would add a
100 MB+ runtime or a Rust toolchain for no capability the browser lacks, and
would break EvalArc's no-runtime-dependency install. `evalarc view` uses the
Python standard library only.

## Security

The viewer binds to `127.0.0.1` only and serves files inside the given folder:
it rejects requests whose `Host` is not `127.0.0.1:PORT` or `localhost:PORT`
(DNS-rebinding protection), path traversal, symlinks leaving the folder and
directory listings. It is read-only and has no API. To view reports on a remote
machine, forward the port over SSH instead of exposing it:

```bash
ssh -L 7576:127.0.0.1:7576 user@remote   # then run evalarc view there
```

## Report pages

Reports open with the decision (verdict, reason, next step) and work in light
and dark mode, on phones, at 400% zoom, in print and without JavaScript. With
JavaScript, table headers become sort buttons (WAI-ARIA APG sortable-table
pattern) and tables with eight or more rows get a labelled filter. The script is
inlined and allowed by a SHA-256 hash in each page's Content-Security-Policy; no
other script, network request or remote asset is permitted.
`scripts/check_reports_browser.cjs` checks every report kind and the viewer with
axe-core (WCAG 2.2 A/AA) and end-to-end reviewer tasks in CI. Automated checks
do not replace testing with a screen reader.

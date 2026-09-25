# Publication and maintenance

The canonical source is [noteflowai/evalarc](https://github.com/noteflowai/evalarc).
The evidence explorer is published to
[GitHub Pages](https://noteflowai.github.io/evalarc/) and the
[Hugging Face Space](https://huggingface.co/spaces/glayguo/evalarc).

## Reproduce the website

```bash
python3 scripts/build_site.py --output dist/site
npm ci
npx playwright install chromium
npm run test:site
python3 -m http.server 8000 --directory dist/site
```

Choose a fresh output directory for each build. `SITE_DIR` changes the browser
test's local directory; `SITE_URL` tests an already served site. `SITE_HUB=1`
tests the app inside the actual Hugging Face iframe. `SITE_SCREENSHOTS` saves
desktop and mobile screenshots.

The builder checks the evidence supporting the headline outcomes, copies the
original audit JSON without modification, and writes `manifest.json` with the
source commit, dirty status and SHA-256 for every file. HTML is encoded as ASCII
with character references for compatibility with static Space hosting.
The v0.3 comparison is recomputed from its baseline and current JSON before
building. The builder rejects inconsistent summaries or changed headline claims.

The browser check visits all 17 implementations and 167 cases at desktop and
mobile widths. It checks the ambiguous write and duplicate note, the reference's
idempotent retry, the coding mismatch, and horizontal overflow. These are saved
scripted controls, not model runs.
It also checks all three changed cases in the v0.3 comparison, follows the
standalone comparison report, and expands the individual evaluation evidence.

## Automatic deployment

CI runs Python 3.11–3.13 tests, Docker audits for both tasks, and browser checks.
Only successful main-branch checks in the canonical repository deploy the
tested `evidence-site` artifact. Pull requests and forks cannot publish it.

GitHub Pages uses the Actions build mode. Hugging Face deployment uses the
repository's `HF_TOKEN` Actions secret; credentials never belong in source or
the browser. A public static Space needs no GPU allocation.

The publisher rejects dirty builds, mismatched source commits, or an existing
Space with a different source manifest, SDK or visibility. It only replaces
files owned by the previous manifest and preserves unrelated remote files.
Every uploaded file is read back from the immutable Hub revision without
authentication and compared with the tested artifact.

## Python distributions

EvalArc **0.14.0** is available from
[PyPI](https://pypi.org/project/evalarc/0.14.0/) and
[GitHub Releases](https://github.com/noteflowai/evalarc/releases/tag/v0.14.0):

```bash
python -m pip install evalarc==0.14.0
```

Both channels serve the same wheel and source archive. Their public files were
downloaded and checked against the GitHub release SHA-256 digests after the
first PyPI publication on September 25, 2026. A fresh Python 3.12 environment
installed the public package, passed `pip check`, and verified the recorded
evaluation example.

For an installation that pins the wheel's checksum explicitly:

```bash
python -m pip install "https://github.com/noteflowai/evalarc/releases/download/v0.14.0/evalarc-0.14.0-py3-none-any.whl#sha256=d1000d2d258f0bef968c3e043ec03b792aebcf7110011820b779ba44a0bdd259"
```

The `publish-pypi.yml` workflow publishes an existing GitHub release using the
PyPI trusted publisher for owner `noteflowai`, repository `evalarc` and
environment `pypi`. It downloads the release distributions, checks their hashes,
metadata, source archive and installed wheel, then uploads those same files.
Run it from `main` with the intended release tag:

```bash
gh workflow run publish-pypi.yml --repo noteflowai/evalarc --ref main \
  -f tag=vX.Y.Z -f repository=pypi
```

Recorded evidence bundles remain separate GitHub release downloads. Their
versions and checksums can stay fixed while the reviewer receives updates.

## Outreach

Use [the launch materials](outreach/launch.md) for project descriptions.
Record public receipts in [the publication log](outreach/status.md).
Maintainer announcements and editorial submissions are distinct from
third-party acceptance. Update existing submissions when appropriate instead
of opening duplicates.

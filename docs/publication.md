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

GitHub releases distribute the Python wheel and source archive. A GitHub
release does not mean a package has been published to PyPI.

## Outreach

Use [the launch materials](outreach/launch.md) for project descriptions.
Record public receipts in [the publication log](outreach/status.md).
Maintainer announcements and editorial submissions are distinct from
third-party acceptance. Update existing submissions when appropriate instead
of opening duplicates.

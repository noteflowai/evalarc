# Validation record · v0.3.0 · 2026-09-14

Validation ran locally on Linux with Python 3.12.3 and Node.js v22.23.2.
This record covers the new evaluation workflow. The
[v0.2 audit record](validation.md) retains the original scripted-control evidence.

| Check | Observed result |
| --- | --- |
| Python test suite | 77 passed |
| Ruff on `src/evalarc` and `tests` | Lint and formatting passed |
| Docker readiness check | Host and pinned local image inspection passed |
| Coding reference, Docker, seed 17 | All 15 cases resolved |
| Support reference, Docker, seed 17 | All 4 cases resolved |
| Two faulty support policies, Docker, seed 17 | Assessed failures, scores 0.9 and 0.9375 |
| Compare those policies | Score increased 0.0375; one regressed note check; exit code 1 |
| HTML browser checks at 1280 px and 390 px | No document overflow or page errors; evidence expansion works |
| Wheel installed in a separate fresh virtual environment | Version, readiness check, task initialization, and 12 support episodes passed outside the checkout |
| Installed-wheel comparison | Preserved the 0.0375 score increase and one regression; exit code 1 |
| Isolated-source documentation checks | JSON/SVG parsed; 69 local links resolved |

The browser check used local Chrome through Playwright. The comparison uses
cards on narrow screens so that changed checks remain readable. The evaluation
tables scroll within their containers; the entire page does not overflow.
Screenshots were inspected locally.

The functional checks used an isolated Git tree. Publication integration
subsequently combined that workflow with the existing verified site tooling.

The [individual report](../examples/evaluation/index.html) and
[comparison](../examples/comparison/index.html) contain fresh v0.3 execution
evidence. No LLM or external inference service was called.

Grading source and generated-case fingerprints for both positive controls match
their v0.2 Docker records. The common evaluator, task contracts, generators, and
scoring rules were not changed by this release.

The tests include higher-score regressions, inconsistent JSON claims, duplicate
keys/cases, nonfinite numbers, invalid-run handling, runtime mismatches, HTML
escaping, output collision prevention, publication after complete generation,
cleanup after exceptions, and non-executing candidate inspection.

The readiness command does not run candidate code or verify arbitrary executables
inside a Docker image. Comparison establishes consistency of recorded outcomes,
not report authenticity, statistical significance, or cross-domain ranking.
Abrupt worker termination may leave unpublished temporary files.

## Integrated publication checks

- 80 tests passed after combining the functional update with site artifact
  checks; lint and formatting passed across the complete repository.
- The site builder recomputed the saved comparison from validated baseline and
  current JSON. A test confirms that an inconsistent comparison is rejected.
- Chromium checks at 1440 px and 390 px covered the existing 17 implementations
  and 167 cases, all three changed comparison cases, and both standalone reports.
  The duplicate note, closure improvements, evidence expansion and absence of
  document overflow were checked.
- The public workflow runs the Python 3.11–3.13 matrix, both Docker audits,
  package builds and browser checks before deploying the tested artifact.
  Publication receipts are kept in [the outreach log](outreach/status.md).
- [PR #1](https://github.com/noteflowai/evalarc/pull/1) and
  [main CI run 34801187828](https://github.com/noteflowai/evalarc/actions/runs/34801187828)
  passed all configured checks. The actual public Hugging Face iframe and
  GitHub Pages site then passed the same desktop/mobile checks, including
  comparison-to-report navigation and expanded evaluation evidence.
- All 18 Space bundle files were read back anonymously. The release wheel,
  source archive and checksum file also matched anonymous downloads.

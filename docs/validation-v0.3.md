# Validation record · v0.3.0 · 2026-09-14

Validation ran locally on Linux with Python 3.12.3 and Node.js v22.23.2.
This record covers the new evaluation workflow; the previous
[v0.2 audit record](validation.md) remains unchanged apart from its navigation.

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

The package was built from an isolated Git tree containing the functional update.
Concurrent, uncommitted promotion files were excluded from that build.

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

Existing CI jobs were not executed remotely by this functional update. The
readiness command does not run candidate code or verify arbitrary executables
inside a Docker image. Comparison establishes consistency of recorded outcomes,
not report authenticity, statistical significance, or cross-domain ranking.
Abrupt worker termination may leave unpublished temporary files.

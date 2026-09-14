# Changelog

## 0.3.0 · 2026-09-14 · Research preview

- `evalarc doctor` checks runtime readiness and candidate configuration without
  executing a candidate.
- Every evaluation now includes a standalone HTML report and its complete JSON.
- `evalarc compare` validates matching records and reports each regressed check,
  including when improvements elsewhere raise the aggregate score.
- CLI outputs use fresh directories and staged publication to preserve earlier
  evidence.
- The evidence lab adds a comparison from 90% to 93.75% with one regressed note
  check and two improved closure checks, plus the downloadable input records.

The task contracts and grading fingerprints are unchanged. Comparisons check
recorded consistency and matched conditions; they do not authenticate the
producer, establish statistical significance, or imply full task resolution.

## 0.2.0 · 2026-09-14 · Research preview

First public EvalArc release.

- Two executable task packs: `durable-kv` for coding artifacts and
  `support-routing` for simulated tool policies.
- Fifteen declared negative controls, known-good references, and recorded
  Docker audits with reproduction metadata.
- Configurable candidate commands, including an independent JavaScript
  support policy using the same host verifier.
- Interactive evidence explorer on GitHub Pages and Hugging Face: compare
  implementations, inspect failures, and step through tool state changes.
- Python 3.11–3.13 CI, Docker audits, desktop/mobile browser checks, and
  verification of the published Hugging Face bundle.

The recorded examples are scripted controls and public development tasks.
No frontier-model ranking, arbitrary reward-hack resistance, human time
horizon or RL training gain is established.

## Local prototype history

The initial GradeRail prototype supplied the durable key-value task. It was
renamed to EvalArc before public release. Support routing and configurable
commands were added during the local 0.2 development cycle. Earlier local
archives are not separate public releases.

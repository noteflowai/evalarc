# Changelog

## 0.5.0 · 2026-09-14 · Research preview

- `evalarc suite` executes versioned TOML plans across multiple candidates and
  built-in tasks, with per-job seeds, repetitions, runtime limits, and gates.
- `--dry-run` validates configuration and previews workload without starting
  candidates or contacting Docker.
- Every candidate is snapshotted and preflighted before the first job runs.
  Candidate paths resolve relative to the configuration file.
- Gates default to full resolution. Optional score/rate thresholds and required
  dimensions expose partial acceptance without hiding unresolved outcomes.
- Reports preserve individual attempts and task scores, with no cross-domain
  average. JUnit exports one test per gate, separating failures from environment
  errors; other jobs still run after a recorded invalid evaluation.
- Local execution still needs explicit CLI trust. Existing outputs remain
  protected; JSONL progress includes job identity.

Task contracts, scoring code, runtime enforcement, and evaluation/repetition
schemas are unchanged from v0.4. Matching v0.4/v0.5 evaluations remain comparable.
No new model-provider or browser-agent integration is claimed.

## 0.4.0 · 2026-09-14 · Research preview

- `evalarc repeat` freezes one candidate across fresh attempts, preserves every
  evaluation, and reports case/check pass rates and varying outcomes.
- Invalid attempts and incomplete runs remain explicit; repetition stops after
  the first invalid evaluation. No best-attempt selection or statistical
  population estimate is provided.
- A 60-second default case budget spans protocol exchanges and process restarts,
  alongside the existing per-response timeout.
- Evaluations, audits, and repetitions save host-generated `events.jsonl`;
  `--progress` streams those events to stderr.
- Case evidence includes bounded process diagnostics. Cleanup exceptions still
  release local processes and pipes where possible, and preserve cancellation.
- Bilingual guidance, fresh Docker audits, and a three-attempt scripted
  repetition example accompany the release.

Both task contracts remain v0.1.0 and evaluation schema v2 remains readable.
Runtime metadata and grading fingerprints change: re-run candidates under
matching v0.4 conditions before comparing them. The existing public evidence
explorer continues to use its historical v0.3 showcase.

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

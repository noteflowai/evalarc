# Changelog

## 0.12.0 — 2026-09-16

- Add offline `trace-stability` and `trace-stability-verify` for repeated saved judgments of one fixed recording. Reject changed execution/configuration/rubrics and duplicate repetition IDs.
- Keep score variation, observed pass/reject disagreement, missing assessments and not-applicable skill targets distinct. Agreement gates do not require task acceptance; all-reject results remain visible.
- Add an interactive homepage matrix, standalone filtered report, preserved-input downloads and deterministic evidence ZIP. Five synthetic controls cover three judgment sets; no new model or AWS evaluation is claimed.
- Extend installed-wheel and desktop/mobile/offline checks. Correct stale casebook counts to the existing 251 audit rows; original research and audit records are unchanged.

## 0.11.1 — 2026-09-15

- Use explicit HTML filenames for published lab navigation. Hugging Face redirects bare directory paths to Hub routes rather than serving each directory index. Cover homepage entries and research/skill-lab return links.
- Reseal only the published lab presentation files; recorded trials, raw JSON and original research archives stay byte-identical. Test navigation with a static server that rejects implicit directory indexes.

## 0.11.0 — 2026-09-15

- Add offline AgentCore Evaluate import, golden-case/rubric comparison and recomputable trace review with responsive standalone reports.
- Keep valid zero, skipped/error, missing results, missed skills and changed bundle identities distinct.
- Publish five synthetic controls and one actual local stdio MCP delivery with no evaluator scores. Imported judgments and caller-declared coverage are separate from independent task verification.
- Update stale Harbor/architecture descriptions and derive homepage task/fault counts from the saved audits.

## 0.10.2 — 2026-09-15

- Bind evidence explorer links to SHA-256 of the actual loaded audit bytes. A changed recording with the same case coordinates no longer reports the original evidence as restored. Display the loaded fingerprint and distinguish content identity from authorship.
- Keep legacy links readable with an explicit missing-identity notice; reject duplicate parameters and preserve report/download access when browser hashing is unavailable. Test changed bytes under an unchanged manifest, fresh links, retry, mobile layouts and clipboard fallback.
- Task contracts, metric calculations and historical audit records are unchanged.

## 0.10.1 — 2026-09-15

- Add a reduced-suite regression that removes `cas-type-sensitivity` from `durable-kv` at seed 17: `boolean-equals-one` survives, the recomputed audit reports 7 of 8 at 0.875, and the weakest margin is 0. The published 0.10.0 wheel already produces these values and includes surviving valid controls in the weakest margin. This release adds the regression and clarifies the explanation; it does not change the metric calculation.
- Correct the explanation of what a margin means, in the code comments, the methodology, both READMEs and the outreach record. Removing a sole detector does not preserve a mutation score of 1.0: a recomputed audit exposes the regression, and only a stale report would still say 1.0. What a perfect score hides is the fragility before a change, not the regression after one.

## 0.10.0 — 2026-09-14

- Add a three-task audit coverage section with direct links from single-case dependencies to recorded fault evidence. Re-render all three reports from unchanged saved JSON, with accessible disclosures and layouts for narrow screens.
- Include assessed surviving faults as zero in the weakest detection margin; environment failures remain unassessed.
- Extend the Hugging Face casebook to all three task packs: 251 case rows, with the parent control's distinct-case detection margin. Preserve the original source records and distinguish reference controls with a null margin.

- Report detection margins beside the mutation score: how many cases caught each declared fault, the weakest margin in the pack, the faults caught by exactly one case, and the cases that are the sole detector of some fault. All three packs score 1.0, and six of their 21 declared faults rest on a single case each; that fragility was previously invisible.
- Count margins over distinct cases rather than case runs, so adding a seed cannot inflate them. Measured margins are identical under the Python and JavaScript references.
- State the relation to the hack-verifiable environments methodology and record both papers as verified primary sources. HVE plants a hack in the environment to measure whether an agent exploits it; an audit here plants a fault in the submission to measure whether the checks catch it. Opposite directions, no equivalence claimed.
- Correct the task-pack count and table in both READMEs: robot-evidence-review shipped in 0.9.0 but was described as if only two packs existed, and the JavaScript reference was said to cover 15 faults rather than 21.

## 0.9.0 — 2026-09-14

- Add the robot-evidence-review task: attributed CUDA source data, coordinate/clock transformations, missing observations, Python/JavaScript references and six independent fault controls.
- Separate trusted Docker startup readiness from candidate response timing. Keep startup and total-case bounds and distinguish environment failure from candidate failure.
- Import Harbor results while independently grading candidate code; export recorded trials to ATIF 1.8. Native Harbor oracle/NOP checks and upstream ATIF validation accompany the examples.
- Publish 27 actual Qwen3-8B trials with every candidate, MCP receipt and independent outcome. Add controlled skill-composition/output auditing and a Funes cross-model handoff pilot. These public development pilots do not establish skill or memory efficacy.
- Add a non-networked, non-root agent workspace and bounded file/tool operations for reproducible model pilots.


## 0.8.0 · 2026-09-14 · Research preview

- Verify whole suite handoffs from the original TOML, plan, every repetition and
  attempt, recomputed custom gates and JUnit failure/error records.
- Add `--require-accepted` for configured suite gates, distinct from record
  consistency and full task resolution. Original candidate paths and timings
  remain reported metadata; no candidate or grader is executed.
- Download the featured suite as a deterministic ZIP from the evidence lab.
  Preserve all 12 original input files and verify the extracted archive offline.
- Check received suites from the installed wheel outside the checkout with an
  empty PATH, including rejection of a modified JUnit record.

Task contracts, scoring rules and historical evidence bytes are unchanged.


## 0.7.1 · 2026-09-14 · Research preview

- Share and restore a specific task pack, control, seed, case and trace step in
  the evidence explorer, including a selectable link when clipboard access is
  denied. Out-of-range links show an explicit fallback.
- Retry failed suite, repetition, comparison or task-pack requests independently.
  Bound network waits and keep a successfully loaded task pack usable when the
  other fails; retrying can restore the originally linked evidence.
- Add section navigation, case-detail focus and return controls, keyboard-readable
  JSON panels, larger buttons and readable mobile evidence text.
- Render the site's preview version from package metadata.

Original reports, task contracts, scoring and CLI behavior are unchanged.

## 0.7.0 · 2026-09-14 · Research preview

- Add `evalarc verify` for received evaluation, repetition and comparison
  records. Recompute summaries and source identities without candidate
  execution, a source checkout, Docker or the original interpreter.
- Return machine-readable results and hashes of every checked JSON input.
  Separate consistency success from `--require-resolved` acceptance.
- Bound input sizes and attempt inventory; reject duplicate keys, non-finite
  numbers, symlinks and special files. Keep historical evidence readable.
- Document unsupported aggregate formats and the distinction between record
  consistency, independent grader execution and producer authentication.

Task contracts, runtime enforcement and scoring rules are unchanged. This
release verifies existing evidence; it does not add new model trials.


## 0.6.0 · 2026-09-14 · Research preview

- `init --language python|javascript` supplies starters and references for both
  tasks. JavaScript workspaces include a portable command manifest, the complete
  task contract, and runtime guidance; Python remains the default.
- An independent Node.js durable service preserves numeric source text, integer
  precision, float/integer distinctions, signed floating zero, nested values,
  and unordered object equality. A complete snapshot precedes write acknowledgement.
- `audit --language javascript` exercises the same eight coding and seven
  simulated-ticket fault models. Local audits resolve Node from the host PATH;
  Docker image selection remains explicit.
- Workspace initialization stages complete files before publishing and removes
  partial output after failures. Existing files and directories remain protected.
- Protocol tests cover values beyond the public task cases, SIGKILL recovery,
  invalid batches, special keys, failed persistence, and corrupt snapshots.
- Docker CI audits now cover both languages and both tasks. The Python package
  includes all JavaScript templates without adding a Python runtime dependency.

Task contracts, grading/runtime source files, and evidence schemas are unchanged.
Comparisons still require matching recorded commands, runtime, grader, and cases;
different-language executions do not become a matched comparison automatically.
No TypeScript SDK, Rust worker, or model-provider adapter is introduced.

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
- The browser compares permissive and notes-protecting gates applied to the
  same frozen faulty policy. The three-job, five-attempt Docker suite includes
  original TOML, JUnit and every report. Site builds recompute gate decisions
  from the configuration and attempt evidence and verify the JUnit export.

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
- The browser now exposes six actual Docker attempts across the reference and
  duplicate-write control, per-check counts, every attempt report, and progress
  downloads. Site builds recompute repetition summaries from all attempt records.

Both task contracts remain v0.1.0 and evaluation schema v2 remains readable.
Runtime metadata and grading fingerprints change: re-run candidates under
matching v0.4 conditions before comparing them. The earlier comparison and audit
explorers retain their historical records alongside the new v0.4 repetitions.

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

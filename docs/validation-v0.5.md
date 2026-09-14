# Validation record · v0.5.0 · 2026-09-14

Checks ran locally on Linux with Python 3.12.3. The release coordinates
existing task evaluators and applies separate suite acceptance rules.

| Check | Observed result |
| --- | --- |
| Python tests | 168 passed, including existing evaluator and site tests |
| Repository Ruff lint and formatting | Passed |
| Reference suite in Docker | 2/2 gates accepted; 23 case executions; exit 0 |
| Partial-progress suite in Docker | 2/3 gates accepted; 31 case executions; exit 1 |
| Same faulty support input under two gates | Both mean scores 0.9375 and 0/2 resolved; notes requirement rejects only the stricter gate |
| JUnit XML from both Docker suites | Test/failure/error counters match job decisions; unique task/job identities |
| Matching v0.4/v0.5 reference evaluations, both tasks | Identical grading/cases/runtime metadata; score delta 0; no regression |
| Chrome/Playwright, 1280px and 390px | No document overflow or page errors; gate details, job navigation, and attempt evidence work |
| Wheel installed in a fresh environment outside the checkout | Python coding/support and independent JavaScript jobs passed together; 23 case executions |
| Installed-wheel gate/error paths | Protected notes reject the 0.9375 policy; missing runtime invalidates one job while the next job passes |
| Real SIGINT during an installed-wheel suite | A prior job completed, then cancellation returned 130, reaped the active candidate, and removed the unpublished suite |
| Packaging | Wheel sources/assets match the exercised installation; all 29 suite configuration/evidence files, including XML and JSONL, retained in the source distribution |
| Local documentation and new report links | 94 resolved |

The [archived suite](../examples/suite/index.html) preserves the intentionally
failing example, all five attempts, and progress streams. The two real Docker
suites executed 54 cases in total. They use the existing local immutable image
`sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea`.

Tests cover unknown/misspelled configuration keys, invalid limits, unsupported
dimensions, duplicate and unsafe IDs, relative paths, bounded plans, non-executing
previews, explicit local trust, preflight of all candidates, freezing later
inputs before the first job, cancellation, output collisions, and distinct
invalid-job handling. A missing runtime invalidates its job while later jobs
still complete. Lowering both numeric thresholds cannot accept an invalid or
incomplete evaluation.

Planning does not open candidate files. A FIFO command manifest is left
unopened during preview and rejected as a non-regular file by execution
preflight, before any candidate process starts.

Gate arithmetic also uses explicitly marked synthetic repeated observations.
Required dimensions detect a check failure that would otherwise pass a
permissive mean-score threshold. HTML escaping and replacement of XML-invalid
control characters are tested. JUnit uses one testcase per job gate.

The [v0.4 audit record](validation-v0.4.md) retains the full 15-control Docker
evidence. Grading/runtime source files did not change in v0.5, and the new
reference executions reproduce their fingerprints. The suite coordinator and
gate configuration do not alter task scoring.

Browser screenshots were inspected locally. Existing promotion pages and
historical example records were preserved. No model-provider integration,
browser-agent environment, or end-to-end hosted CI importer run was performed.

Tests and builds used an isolated Git worktree containing the functional
changes. The installed-wheel checks ran outside that worktree and the development
checkout. The active runtime has no third-party Python dependencies.

## Publication integration

The isolated publication checkout merges the completed suite update with the
published v0.4 repeatability explorer. It passed **172 Python tests**, Ruff lint
and formatting. Fresh Docker suite runs accepted both reference jobs (23 cases,
exit 0) and rejected the protected-notes job in the partial-progress suite
(31 cases, exit 1); the expected rejection is an assessed failure, not an
infrastructure error.

The browser now shows the same 93.75% policy under two explicit gates, with
0/2 resolved attempts visible in both. Desktop (1440 px) and mobile (390 px)
checks cover both decisions, the shared candidate, JUnit with three job tests
and one failure, suite/job/attempt report navigation, and every existing
regression and repetition showcase. No page errors or horizontal overflow
were observed. The bundle contains 61 files, including its manifest.

Before building, each job summary is recomputed from its complete attempt
records; gate decisions are recomputed from the original TOML. The JUnit
export is regenerated and compared with the saved file. Regression tests
reject a changed decision and a failure relabeled as an environment error.
Historical v0.3/v0.4 records retain their original provenance.

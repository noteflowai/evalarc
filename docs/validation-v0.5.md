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

# Validation record · v0.4.0 · 2026-09-14

Validation ran locally on Linux with Python 3.12.3 and Node.js v22.23.2.
The release adds repeatability evidence and execution controls to both existing
task packs. The [v0.3 record](validation-v0.3.md) remains historical.

| Check | Observed result |
| --- | --- |
| Python test suite before publication work | 121 passed, including the existing site checks |
| Ruff | Repository lint and formatting passed |
| Coding Docker audit, seed 17 | Reference resolved 15 cases; 8/8 declared faults detected |
| Support Docker audit, seed 17 | Reference resolved 4 cases; 7/7 declared faults detected |
| Support Docker repetition, seed 17, 3 attempts | All 12 episodes resolved; one candidate fingerprint |
| Independent JavaScript policy, trusted local Node, 2 attempts | All 8 episodes resolved |
| Repeat report, Chrome/Playwright at 1280px and 390px | No document overflow or page errors; checks expand; attempt links reach full evidence |
| Fresh wheel install outside the checkout | Version and readiness passed; 30 coding reference, 24 support reference, and 24 faulty-policy episodes assessed |
| Installed-wheel repeated faulty policy and comparison | No resolved attempts, mean 0.9375, exit 1; matched comparison exposed 3 note regressions across 3 seeds |
| Real SIGINT during an installed-wheel candidate run | Exit 130, candidate process reaped, unpublished output removed, external cancellation event retained |
| Local documentation and new report links | 70 resolved |

The [fresh audits](../examples/audit-v0.4/README.md) retain all control outcomes
and progress events. The [repetition example](../examples/repetition/index.html)
retains three complete evaluation records and their reports. Browser screenshots
were inspected locally. The existing public-demo records were not regenerated.

Wheel and source distributions were built from an isolated Git tree. The wheel
was installed in a fresh virtual environment and exercised from outside the
checkout. The publication follow-up below adds the v0.4 repetition explorer;
the earlier audit and comparison records retain their original provenance.

Tests exercise frozen inputs despite changes to the original candidate,
callback isolation, explicit invalid denominators, incomplete attempts,
check variability despite stable case failure, identity mismatches, progress
ordering, bounded stderr, shared restart deadlines, and total-case timeout
despite individually prompt responses. Docker cleanup timeout tests verify
that local processes/pipes are released and cancellation remains cancellation.

Execution evidence uses the immutable local image
`sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea`.
The v0.4 grading fingerprints are:

| Task | Grader SHA-256 |
| --- | --- |
| `durable-kv` | `2283f5c82c24ac536c4467f5833333fc7098adb46839238fdc56eca017ef2039` |
| `support-routing` | `887aea97efec396118521f720f6d8753be9ae964ab92eaa655d6575185326593` |

Case fingerprints match the prior seed-17 records. The runtime and grading
fingerprints change, so evaluations from different releases must not be mixed
in comparisons or trajectories.

No model API, RL trainer, browser-agent environment, confidence interval, or
population reliability estimate was involved. Repeated passing controls show
functional behavior on these cases. Variability aggregation uses clearly marked
synthetic test observations, not fabricated model runs.

## Publication follow-up

The reviewed publication tree passed **123 Python tests**, Ruff lint and
formatting, and fresh seed-17 Docker audits of both task packs. A new real
Docker repetition of the duplicate-write control assessed all three attempts:
mean score 0.9375, zero resolved attempts, zero invalid attempts and no observed
check variation. Its grader, cases and runtime match the preserved reference
repetition.

The browser exposes all six attempts and 24 case episodes, with per-check
counts, frozen-candidate fingerprints, JSONL downloads and links to complete
reports. Desktop (1440 px) and mobile (390 px) checks passed, including all
17 existing audit implementations, 167 audit cases, three comparison cases,
both repetition controls and standalone report navigation. No page errors or
horizontal overflow were observed. Failed attempt badges retain their failure
color when hovered.

Site builds independently recompute each repetition summary from every saved
attempt. Regression checks reject a forged resolution rate and a missing
attempt. The final bundle contains 36 files, including its ownership manifest.

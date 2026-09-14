# Research and development roadmap

The core question is whether auditing graders with independent negative
controls improves the relationship between evaluation reward and software
quality on unseen tasks. Passing this repository's audit is a first engineering
check; answering that question needs substantially more evidence.

| Stage | Deliverable | Acceptance evidence |
| --- | --- | --- |
| v0.1, implemented | Stateful task, grader, eight controls, provenance, checkpoint statistics | Positive and negative controls, protocol tests, Docker execution |
| Next | Task-author API and externally supplied defect packs | A second independent task and reviewer-authored defects |
| Next | Harbor integration using supported verifier boundaries | Actual upstream task execution, pinned compatibility version |
| Next | Procedural task variants with separated public and private acceptance | Measured exposure controls; distribution-level split |
| Research pilot | Three deep task families | Human baselines, repeated real agent attempts, failure taxonomy |
| Research study | Grader-audit ablations and downstream training | Unseen-family transfer, matched budgets, uncertainty intervals |

Candidate deep task families:

1. Persistent storage: schema migration, transaction recovery, and backward
   compatibility under evolving requirements.
2. Workflow execution: retries, idempotency, cancellation, durable scheduling,
   and external side effects.
3. Protocol compatibility: incremental parsers, behavioral conformance,
   malformed-input handling, and bounded resource use.

Do not assign an “8-hour” label until appropriate humans have actually been
timed or a clearly marked estimation methodology exists.

## Study design

Pre-register fault families, task splits, scoring weights, and budgets. Use
independent experts to author held-out defective implementations, including
defects not present in the public audit. Compare ordinary public tests,
audited executable graders, and audited graders with additional private checks.
Measure false acceptance, false rejection on independent correct solutions,
cross-seed stability, agent regression rates, and held-out task performance.

For an RL study, hold model initialization, training compute, task exposure,
sampling, and inference budgets fixed. A higher reward alone is insufficient:
test real behavior using a separately maintained acceptance suite. Bootstrap at
task-family level when possible; seeds of the same generator are not independent
real-world tasks.

## Release and community plan

Before public launch, ship one reproducible audit report, one clearly labeled
failure example, a concise demo, and a beginner task-author guide. The useful
contribution unit is “one contract + one independent correct implementation +
one meaningful defect + evidence that the grader catches it.”

Seek early feedback from environment authors and contribute a small integration
to an existing ecosystem. Avoid promotional claims about partnerships, acquisition
rumors, SOTA, human replacement, or growth metrics that have not been established.
Repository popularity is an outcome to measure, not a technical property a
new project can promise.

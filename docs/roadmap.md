# Research and development roadmap

EvalArc targets auditable evaluations across software agents. The first
implemented task pack is for coding. v0.2 adds a simulated support workflow to
exercise a second interaction model through the [shared metadata](architecture.md).

The research question is whether independent grader audits improve the
relationship between evaluation reward and actual task outcomes on unseen
tasks. Passing the current audit is a first engineering check; answering that
question needs substantially more evidence.

| Stage | Deliverable | Acceptance evidence |
| --- | --- | --- |
| v0.1, implemented | Coding task, grader, eight controls, provenance, checkpoint statistics | Positive and negative controls, protocol tests, Docker execution |
| v0.2, implemented | Task definitions and configurable candidate commands | Python and independent JavaScript support policies use the same verifier |
| v0.2, implemented | Simulated support-ticket workflow and a JSONL policy loop | State-based grading, tool-call traces, correct and seven faulty policies |
| v0.2, implemented | Shared report metadata with domain-specific checks | Both packs record commands, provenance, validity, outcomes, and evidence |
| v0.3, implemented | Readiness checks, individual HTML reports, matched-run comparisons, protected output paths | Read-only inspection, per-check regression detection, input consistency checks, and preserved prior runs |
| v0.4, implemented | Fixed-candidate repeated evaluation, per-check variability, case deadlines, progress events, process diagnostics | Fresh state per attempt, explicit invalid denominators, shared restart budgets, cancellation and cleanup tests |
| v0.5, implemented | Declarative suites, per-job acceptance gates, HTML/JSON and JUnit export | All-candidate preflight, workload preview, protected dimensions, distinct invalid outcomes, no cross-domain score average |
| v0.6, implemented | Python/JavaScript templates and independent controls for both tasks | The same 15 declared faults, Node Docker execution, lossless numeric handling, process-crash recovery, atomic workspace initialization |
| v0.11, implemented | Offline AgentCore trace review and skill receipt linkage | Preserved bytes, versioned golden cases/rubrics, separate missing/skipped/zero results and synthetic vs recorded provenance |
| v0.12, implemented | Offline fixed-record judge repetition diagnosis | Exact recording/rubric checks, per-target denominators, separate score/gate disagreement, preserved-input recomputation |
| Next | Judge calibration and broader trace collection adapters | Live upstream runs and independent calibration cases; descriptive agreement alone is not accuracy |
| Next | Broader language coverage for coding | A non-Python Durable KV submission passes the same full contract |
| Next | Independent defect packs and task authors | Reviewer-authored faults and a third independently authored task |
| Next | Real model-provider adapter | End-to-end run with measured usage, task evidence, repeated attempts |
| Later | Browser environment adapter | Reproducible initial state, backend outcome checks, isolated sessions |
| Research pilot, implemented | Native Harbor task export, oracle/NOP execution and ATIF 1.8 | Pinned Harbor 0.23.0; upstream reward separate from independent checks |
| Next | Procedural task variants with separated public and private acceptance | Measured exposure controls; distribution-level split |
| Research pilot | Three deep task families | Human baselines, repeated real agent attempts, failure taxonomy |
| Research study | Grader-audit ablations and downstream training | Unseen-family transfer, matched budgets, uncertainty intervals |

Candidate task families:

1. Persistent storage: schema migration, transaction recovery, and backward
   compatibility under evolving requirements.
2. Business tools: ticket routing, retries, idempotency, cancellation, and
   verifiable changes to a simulated service.
3. Browser workflows: complete an operation and validate the resulting state
   independently of the agent's final message.
4. Protocol compatibility: incremental parsers, behavioral conformance,
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

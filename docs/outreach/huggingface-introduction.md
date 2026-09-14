I'm publishing EvalArc as its maintainer: an open toolkit for auditing the
graders behind AI-agent evaluations.

**Updated for v0.5: same score, different acceptance gate.**

**New data companion:** the
[EvalArc Casebook](https://huggingface.co/datasets/glayguo/evalarc-casebook)
makes the recorded evidence filterable in Hugging Face: 167 audit cases, six
repeated attempts and three suite jobs in separate development configurations.
Start with `suite_jobs` to compare acceptance with full resolution, or load the
JSONL in Python. Every row links to unchanged source JSON and a fixed code
revision. This is a small scripted casebook, not a new model benchmark.

The new suite showcase puts the same frozen defective policy through two
explicit rules. Both support jobs score 93.75% and resolve 0/2 attempts.
A deliberately permissive gate accepts the partial result; requiring every
notes check rejects it. Task scores and resolution flags stay unchanged.

The recorded Docker suite retains three jobs, five attempts, the original TOML,
progress streams and JUnit. The browser build recomputes every gate from the
configuration and verified attempt records, then checks the exported JUnit.
Configured acceptance is shown separately from full task resolution. The JUnit
export distinguishes failures from environment errors; a hosted CI importer
was not exercised.

`evalarc suite` previews a TOML plan without starting candidates, freezes all
inputs before the first job, and preserves complete evidence for each job.
There is no average score across coding and support tasks.

The existing repeatability explorer preserves six actual Docker attempts: three
of the scripted reference and three of the duplicate-write control. The
reference resolves 3/3 attempts. The faulty control resolves 0/3, although
each attempt scores 93.75%. Switch controls, inspect per-check counts, and open
every attempt's full report, final state and bounded process diagnostics.
The summaries are recomputed from all six saved evaluations during site builds.

`evalarc repeat` freezes the candidate before the first attempt and uses fresh
workspaces and state. It records invalid denominators explicitly, shares a total
case deadline across restarts, and saves host-generated JSONL progress.
These controls show no observed check variation; they are not stochastic model
trials or evidence of reliability on unseen tasks.

The earlier v0.3 side-by-side comparison starts at 90% and rises to 93.75%. Two closure
checks improve, but a previously passing note check now fails. Select each
changed case to inspect the ticket state before and after the revision.
The new CLI comparison returns exit code 1 for that regression despite the
higher score. Standalone evaluation and comparison reports include the input
JSON so the result can be reproduced without executing a candidate.

Start with the support-tools example in this Space. A scripted policy earns
**93.75%**, yet fails acceptance because a retry duplicates an already committed
note. Step through the failed response and retry, then select the reference to
see an idempotent receipt without a second state change.

The coding example shows a different gap: **92.5%**, but a compare-and-swap
operation treats JSON `true` and `1` as equal. Both examples expose the failed
check instead of hiding it behind an aggregate score.

The lab includes two task packs, 15 declared faulty implementations, their
known-good references, and downloadable JSON with reproduction fingerprints.
It replays recorded Docker audits. No model is called in the Space.

- [Source and quickstart](https://github.com/noteflowai/evalarc)
- [Chinese introduction](https://github.com/noteflowai/evalarc/blob/main/README.zh-CN.md)
- [Methodology and limits](https://github.com/noteflowai/evalarc/blob/main/docs/methodology.md)

This is an MIT-licensed research preview with public development tasks and
scripted controls. It does not establish frontier-model performance, arbitrary
reward-hack resistance or RL gains.

The existing workflow includes `evalarc doctor` for readiness checks without executing
candidate code, and protects earlier run outputs by requiring a fresh directory.

Feedback is welcome on plausible defects the current controls miss, clearer
task contracts, and independent reference implementations. A small reproducible
case is especially useful.

Maintainer disclosure: this independent project and announcement were developed
with AI assistance.

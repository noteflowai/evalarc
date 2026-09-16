# Review recorded state with Strands Evals

**The mean improves from 75% to 87.5%. A previously passing notes rule fails.**

This runnable companion example uses **Strands Evals 1.3.0** and its native
`Case`, `Experiment`, `EnvironmentState` and `EvaluationReport` APIs. Two
deterministic evaluators check the final ticket state in four saved EvalArc
Docker cases. It does not execute an agent or call a model, AWS or AgentCore.

Strands already preserves per-row `test_passes` and evaluator identities. The
example shows how to use those fields to review a change; it does not report a
defect in Strands or introduce a replacement report format.

[中文](README.zh-CN.md) · [Source](run.py) ·
[Native baseline report](recorded/baseline-native.json) ·
[Native current report](recorded/current-native.json) ·
[Recorded comparison](recorded/comparison.json)

## Inspect without installing

[Open the interactive native-state review](https://noteflowai.github.io/evalarc/strands/index.html)
to compare the expected, baseline and current values. Filter regressions or
improvements, then expand all eight checks. Each check link identifies both
native report files as well as the case and evaluator.

The page's ZIP includes its HTML, both native reports, the comparison, original
EvalArc inputs and a SHA-256 file inventory. Extract it and open
`strands-review/index.html` offline; no server is needed. Without JavaScript,
all checks remain readable. This is a viewer for this fixed example, not an
uploader or a general Strands importer.

## Run it

From a source checkout, use a separate environment for the optional SDK:

```bash
git clone https://github.com/noteflowai/evalarc.git
cd evalarc
python3 -m venv .venv-strands
. .venv-strands/bin/activate
python -m pip install -r examples/strands-state-review/requirements.lock.txt
python examples/strands-state-review/run.py --output runs/strands-review
```

**Expected exit 1**: the review completed and found a regression. Exit 0 means
no previously passing rule regressed; it is distinct from every current rule
passing. Exit 2 means the example cannot produce a valid review. Use a fresh
output directory on each run.

The full dependency lock was tested with CPython 3.12 on Linux.
`requirements.txt` identifies the two direct SDK pins; EvalArc's normal install
does not acquire these optional dependencies.

The output folder contains two native Strands reports and a small comparison.
You can load a report with the SDK's `EvaluationReport.from_file()` or inspect
its JSON directly.

## What changes

| Check | Baseline | Current |
| --- | --- | --- |
| `route-open-ticket@17 / ticket.status` | Fail | Pass |
| `retry-before-commit@17 / ticket.status` | Fail | Pass |
| `retry-after-commit@17 / ticket.notes` | Pass | Fail |
| Remaining five case/rule pairs | Pass | Pass |
| Equally weighted native mean, eight rows | **0.75** | **0.875** |
| Every rule passes | **No** | **No** |

The retry commits a note, receives a transient error, then uses a different
idempotency key. The final notes list contains a duplicate. Exact list equality
detects this; converting the list to a set would discard the duplicate.

The source record's original **90% → 93.75%** score is different: EvalArc
weights five dimensions, while this companion example averages only two state
rules equally over four cases. **Do not compare these as equivalent scores.**
The notes regression is visible under both aggregations.

## How to adapt the pattern

The task callback supplies an `EnvironmentState` named `ticket`. Each `Case`
declares its expected state, and two evaluator instances have distinct names:
`ticket.notes` and `ticket.status`.

Compare reports by **case name plus evaluator identity**, preserving both
inventories. The example rejects missing, duplicate or unmatched pairs rather
than silently dropping checks. For a real comparison, also freeze the dataset,
rule definitions and relevant execution settings; this example's input hashes
already fix its two known records.

The script deliberately accepts only the original fixture bytes. `--comparison`
can point to the `comparison` folder in the released evidence explorer, but it
is not an importer for arbitrary Strands reports or production ticket data.
To review your own task, adapt the case contract, observed states and rules
explicitly. Missing observations need their own handling; do not replace them
with a fabricated zero or an assumed success.

## Recheck the example

In the optional environment, from the repository root:

```bash
python scripts/check_strands_recipe.py
```

The check runs the real SDK with network connections and DNS attempts rejected.
It exercises native JSON serialization, forward and reverse regressions,
missing/duplicate rows, preservation of an existing output and equality with
the committed native reports. It does not use a mock SDK.

The source hashes, installed SDK versions and aggregation scope are preserved
in `recorded/comparison.json`. Generated session IDs refer to this local review,
not to new agent executions.

## Sources and feedback

- [Strands Evals 1.3.0 release](https://github.com/strands-agents/evals/releases/tag/v1.3.0)
- [Strands evaluation reports](https://github.com/strands-agents/evals/blob/v1.3.0/src/strands_evals/types/evaluation_report.py)
- [Environment state and evaluation data](https://github.com/strands-agents/evals/blob/v1.3.0/src/strands_evals/types/evaluation.py)
- [EvalArc's original comparison](https://noteflowai.github.io/evalarc/#regression)

The records are public scripted controls, not customer incidents or model
performance results. This is an independent EvalArc companion example, not an
upstream endorsement or a live cloud integration.

If you try the pattern, [share a first-use finding](https://github.com/noteflowai/evalarc/issues/new?template=first-use.yml):
which state you need to check, what report shape you have, and where the
workflow becomes unclear. A minimal redacted example is sufficient.

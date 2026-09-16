I maintain **EvalArc** and put together a small companion example using the
native **Strands Evals 1.3.0** APIs. It was developed with AI assistance.

The example asks a narrow review question: **which previously passing state
rule regressed when the mean score improved?**

It uses `Case.expected_environment_state`, task-returned `EnvironmentState`,
two deterministic `Evaluator` instances, and native `EvaluationReport` JSON.
The input is four saved scripted Docker cases, not a new model or agent run.

| Result | Before | After |
| --- | ---: | ---: |
| Passing case/rule pairs | 6/8 | 7/8 |
| Equally weighted mean | 0.75 | 0.875 |
| Every rule passes | No | No |

Two closure checks improve, but `retry-after-commit@17 / ticket.notes` changes
from pass to fail. The note was written before a transient error returned; a
retry with another idempotency key adds it again. Exact list equality keeps
that duplicate visible.

Strands already exposes the per-row verdicts and evaluator identities. This
is an example of using those fields, not a bug report or a replacement for
the native report. It aligns rows by **case name and evaluator name**, rejecting
missing, duplicate or unmatched pairs.

[Runnable example, dependency lock and native reports](https://github.com/noteflowai/evalarc/tree/main/examples/strands-state-review)

```bash
git clone https://github.com/noteflowai/evalarc.git
cd evalarc
python3 -m venv .venv-strands
. .venv-strands/bin/activate
python -m pip install -r examples/strands-state-review/requirements.lock.txt
python examples/strands-state-review/run.py --output runs/strands-review
```

Expected exit **1**: the review completed and the regression gate rejects the
change. CI exercises the real SDK with network attempts rejected, checks the
native JSON round trip and guards the case/rule inventory.

The source records also have an EvalArc five-dimension weighted score
(90% → 93.75%). That is a different aggregation from this two-rule Strands
example; the numbers should not be treated as equivalent. This example is
limited to its fixed public fixtures, with no live AWS/AgentCore evaluation or
claim about customer or model performance.

For developers already checking observed state: does this case/rule comparison
fit your review process? I would especially value a minimal redacted example
of a state or report shape that makes alignment difficult.

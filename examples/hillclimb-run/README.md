# Scripted example for `evalarc hillclimb-run` and `evalarc judge-run`

A ticket-routing workspace whose "agent" (`workspace/evaluate.py`) routes a ticket
correctly when `rules.md` has a rule for it. `workspace/propose.py` stands in for a
model and appends one scripted edit per iteration from `workspace/proposals.json`:

| Iteration | Proposed edit | Outcome |
| --- | --- | --- |
| 1 | `route refund -> billing` | `keep`: tuning and held-out both improve |
| 2 | a failing tuning ticket pasted with its answer | `rollback_pasted_case`, not evaluated |
| 3 | `case t06 -> accounts` (fits one tuning case) | `rollback_overfit`, then stall triage |
| 4 | nothing | `no_change` |
| 5 | `route outage -> oncall` | `keep` |

The loop edits the workspace, so run it on a copy:

```bash
cp -r examples/hillclimb-run /tmp/climb-example
evalarc hillclimb-run /tmp/climb-example/hillclimb.toml --output runs/climb --trust-local
evalarc judge-packet pairwise runs/climb/results/00-baseline.json runs/climb/results/05.json \
  --output runs/ab
evalarc judge-run runs/ab --config /tmp/climb-example/judge.toml --output runs/ab-verdicts.json --trust-local
evalarc judge-score runs/ab runs/ab-verdicts.json --require-current-preferred
```

`judge.py` is a scripted judge (it compares the output with the expected queue). A
real judge command would call a model different from the one under evaluation. No
model is called anywhere in this example.

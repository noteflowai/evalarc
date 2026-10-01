# Authored hillclimbing sequence for `evalarc hillclimb-review`

A constructed ticket-routing evaluation: 12 tuning and 8 held-out tickets, four
epochs each, with a baseline and five proposed changes. It follows the
cost-reduction case in Anthropic's *Automating eval design and hillclimbing with
Claude*. **Outcomes and costs are declared in [`build.py`](build.py); no model was
called.** The model names label configurations and are not measurements of those models.

```bash
python examples/hillclimb-review/build.py   # regenerates results/ and split.json
evalarc hillclimb-review examples/hillclimb-review/results/00-baseline.json \
  examples/hillclimb-review/results/0[1-5]-*.json \
  --held-out examples/hillclimb-review/split.json --objective cost --min-effect 0.05
```

| Step | Change | Decision under `--objective cost` |
| --- | --- | --- |
| 01-prompt-audit | Remove forced tool calls, scratchpad, contradictory rules | `keep`: both partitions improve, cost 0.891x |
| 02-refund-examples | Paste failing tuning tickets into the prompt | `rollback_overfit`: tuning +14.6 pp, held out +0.0 pp |
| 03-opus-5.5-low | Newer model, low thinking | `keep`: equal quality at 0.463x cost |
| 04-haiku-minimal | Much cheaper model | `rollback_regression`: held out −12.5 pp |
| 05-sonnet-5-low | Cheaper model, low thinking | `keep`: equal quality at 0.526x cost |

The final kept configuration costs **0.217x** the baseline per sample, and held-out
cases move from 71.9% to 90.6% of attempts. The recommendation is `merge_cost` (exit 0).
The held-out gain alone is within sampling noise, because the notes before step 1 show
this evaluation resolves only changes of about 31% on held-out cases. With
`--objective quality`, the same sequence ends at `do_not_merge_within_noise` (exit 1),
after a stall that reports remaining tuning headroom below the resolvable change.

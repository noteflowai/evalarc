# Grader audits · v0.4

Fresh Docker executions on 2026-09-14, seed 17:

| Task | Reference | Declared defects detected | Evidence |
| --- | --- | --- | --- |
| Durable KV | 15/15 cases resolved | 8/8 | [HTML](durable-kv/index.html), [JSON](durable-kv/audit.json) |
| Support routing | 4/4 cases resolved | 7/7 | [HTML](support-routing/index.html), [JSON](support-routing/audit.json) |

Each directory also includes host-generated `events.jsonl`. These runs use the
new 60-second case budget and record bounded process diagnostics. Task contracts,
cases, and weights are unchanged; grading source fingerprints differ from v0.3.

```bash
evalarc audit --task durable-kv --seeds 17 --output runs/coding-v04
evalarc audit --task support-routing --seeds 17 --output runs/support-v04
```

The historical `examples/audit`, `examples/support-audit`, `examples/evaluation`,
and `examples/comparison` retain their original execution evidence and continue
to support the existing public demonstration. These audits assess declared
scripted controls, not model performance.

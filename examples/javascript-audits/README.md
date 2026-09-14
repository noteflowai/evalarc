# JavaScript control audits

These records exercise independent Node.js references and deliberately faulty
variants through the existing task graders. They use seed 17 in Docker.

| Task | Reference | Detected faults | Evidence |
| --- | --- | --- | --- |
| Durable KV | 15/15 cases | 8/8 | [Report](durable-kv/index.html), [JSON](durable-kv/audit.json), [events](durable-kv/events.jsonl) |
| Simulated support | 4/4 cases | 7/7 | [Report](support-routing/index.html), [JSON](support-routing/audit.json), [events](support-routing/events.jsonl) |

Reproduce after installing EvalArc 0.6 and pulling `node:22-slim`:

```bash
evalarc audit --language javascript --image node:22-slim \
  --seeds 17 --output runs/js-coding-audit
evalarc audit --task support-routing --language javascript --image node:22-slim \
  --seeds 17 --output runs/js-support-audit
```

The [validation record](../../docs/validation-v0.6.md) identifies the image used.
Each JSON preserves the resolved image ID and the full per-control evaluation.
The archived output is evidence of these executions, not a model benchmark or
proof of general grader robustness. The original Python examples retain their
historical provenance.

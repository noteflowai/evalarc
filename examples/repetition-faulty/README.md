# Repeating a stable defect · v0.4

This is a real three-attempt Docker execution of the bundled
`new-key-on-retry` support-routing control, recorded on 2026-09-14.
All three attempts were assessed. Each scored 0.9375 and failed the
`retry-after-commit` note check; no attempt resolved all four cases.
No check varied across these observations.

The candidate is the support reference with only `NEW_RETRY_KEY = True`.
Its exact `main.py` and `TASK.md` are preserved in
[`../repetition-faulty-candidate`](../repetition-faulty-candidate).
Each attempt used a fresh workspace and state, the same seed 17 and the
same immutable Docker image as the [reference repetitions](../repetition/README.md).

```bash
evalarc repeat examples/repetition-faulty-candidate --task support-routing \
  --seeds 17 --attempts 3 --output runs/repeat-faulty-001
# Exit 1: all attempts assessed, none fully resolved.
```

Read the [summary](index.html), [JSON](repetition.json) and host
[progress events](events.jsonl). Every attempt has a complete evaluation,
tool trace, final state and bounded process diagnostics.

This is a deliberately faulty scripted control on public development cases.
Repeated failure demonstrates the recorded defect; these runs are not
stochastic model measurements, confidence intervals or a population
reliability estimate.

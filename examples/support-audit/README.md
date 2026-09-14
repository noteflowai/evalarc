# Recorded support-routing audit

`audit.json` and `index.html` were generated on 2026-09-14 with EvalArc v0.2.0,
Docker, and public seed 17:

```bash
EVALARC_DOCKER='sudo -n docker' evalarc audit \
  --task support-routing --seeds 17 --output examples/support-audit
```

The positive scripted policy passed all four episodes. Seven declared faulty
policies were detected in their intended dimensions. No LLM was called.

The `new-key-on-retry` policy earns 0.9375 but fails full resolution: after the
service commits a note and returns a transient error, retrying with a new key
duplicates the note. The reference keeps the same key; its trace records a
replayed receipt with no second state change.

The HTML includes reference traces. The complete JSON also includes every
negative control's initial/final state, calls, tool results, state changes,
checks and runtime metadata. Durations include container startup and cleanup;
they are not portable policy-performance measurements.

See [validation](../../docs/validation.md) for the other executed checks.

# Recorded regression comparison

EvalArc v0.3.0 generated this comparison on 2026-09-14 from two fresh Docker
evaluations of `support-routing@0.1.0`, both with seed 17 and identical runtime
settings.

- Baseline: the `close-unresolved` fault policy, score 0.9.
- Current: the `new-key-on-retry` fault policy, score 0.9375.

Two closure checks improve, while the note check in `retry-after-commit`
regresses. `evalarc compare` returns exit code 1 despite the score increase.
These are scripted controls, not observations of any model's quality.

To reproduce the comparison without rerunning candidates:

```bash
evalarc compare examples/comparison/baseline.json examples/comparison/current.json \
  --output runs/reproduced-comparison
```

Choose a fresh output directory. The copied baseline/current JSON retain their
original execution timestamps and provenance.

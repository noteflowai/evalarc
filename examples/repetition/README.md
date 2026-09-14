# Fixed-candidate repetition · v0.4

This is a real three-attempt Docker execution of the bundled scripted
support-routing reference on seed 17, recorded on 2026-09-14. All 12 episodes
resolved. No check varied in these observed attempts.

Open [the summary](index.html) to inspect every attempt, its process diagnostics,
and tool-call evidence. [Progress events](events.jsonl) came from the host
evaluator. The [JSON summary](repetition.json) records all denominators and
the common candidate/grader/case/runtime identity.

Reproduce with a fresh output directory:

```bash
evalarc init workspace/repeat-reference --task support-routing --reference
evalarc repeat workspace/repeat-reference --task support-routing \
  --seeds 17 --attempts 3 --output runs/repeat-reference
```

The saved source snapshot contains both `main.py` and the generated `TASK.md`.
Use the same initialization command to reproduce its candidate fingerprint.
An available `python:3.12-slim` image is required; the saved evaluation records
the actual immutable local image ID.

This is a functional control, not a real-model result or an estimate of
reliability beyond these public cases. Outcome variation is covered by explicitly
synthetic unit-test observations; no stochastic-model evidence is claimed.

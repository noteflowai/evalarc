# Recorded single-candidate evaluation

This report was generated with EvalArc v0.3.0 on 2026-09-14, using the
`support-routing` task, Docker, and seed 17. The candidate is the declared
`new-key-on-retry` scripted fault control.

Its score is 0.9375, but it does not resolve the task: retrying a committed note
with a new idempotency key duplicates the note. The HTML exposes the failed
check and the complete case evidence. No model was called.

The execution JSON is unchanged when the HTML presentation is regenerated.
See the [workflow guide](../../docs/workflow.md) and
[validation record](../../docs/validation-v0.3.md).

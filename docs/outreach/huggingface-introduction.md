**The score went up. A previously passing check failed.**

In EvalArc's recorded support example, two checks improve and the score rises
from 90% to 93.75%. A retry also duplicates a note. The changed check remains
visible instead of being hidden by the average.

[**Inspect the regression →**](https://glayguo-evalarc.static.hf.space/#regression)

Follow the recorded action, compare the acceptance rules, then
[recompute the report on your machine](https://github.com/noteflowai/evalarc/blob/main/docs/first-review.md).
The walkthrough uses the published 0.12.1 wheel and downloadable records;
no source checkout, Docker, GPU or model key is needed for that review.
Verification exits 0 for consistent evidence; comparison exits 1 for the
regressed check.

Have your own records? Compare matching EvalArc evaluations, or use the
[bounded AgentCore export walkthrough](https://github.com/noteflowai/evalarc/blob/main/docs/agentcore-first-review.md).
[First-use feedback](https://github.com/noteflowai/evalarc/issues/new?template=first-use.yml)
about a failed setup or useful finding is welcome. Please use a minimal
redacted example, not a production trace dump.

The featured case is a scripted Docker control, not a customer incident or
model benchmark. The scored trace-import controls are synthetic; the separate
MCP example records actual local delivery without evaluator scores. No live
AgentCore evaluation or independent adoption is claimed.

Maintainer update to this existing introduction, developed with AI assistance.
EvalArc is an independent MIT research preview. Offline consistency does not
authenticate the producer or rerun the candidate.

---
title: EvalArc Evidence Lab
emoji: 🔎
colorFrom: green
colorTo: gray
sdk: static
app_file: index.html
pinned: false
license: mit
short_description: Find agent regressions behind a better score.
tags:
  - agent-evaluation
  - tool-use
  - evaluation
  - reproducibility
  - developer-tools
---

# EvalArc — Find the regression behind the score.

**90% → 93.75%. Two checks improve. One previously passing check fails.**
A tool committed a note but returned an error. Retrying with a new key wrote it
again. Inspect the recorded regression, follow the action, and check the
acceptance rule before trusting the higher score.

[**Try the revision comparison →**](https://glayguo-evalarc.static.hf.space/#regression)
· [First local review](https://github.com/noteflowai/evalarc/blob/main/docs/first-review.md)
· [中文](https://github.com/noteflowai/evalarc/blob/main/README.zh-CN.md)

No account, installation or model key is needed to explore the saved records.
The featured comparison contains scripted Docker controls, not customer data
or a model leaderboard.

## Start with one review

1. Compare the two revisions and select `retry-after-commit`.
2. Step through the action that duplicates the note in the case explorer.
3. Compare the permissive gate with the strict notes gate. The score stays
   93.75%; acceptance changes with the declared rule.
4. [Install the published wheel and recompute the report](https://github.com/noteflowai/evalarc/blob/main/docs/first-review.md).
   The local review needs Python 3.11+, with no Docker, Node, GPU or model call.

## Bring your own evidence

- **Matching EvalArc evaluations:** compare changed checks and retain original inputs.
- **Strands Evals users:** run the [native state-review companion](https://github.com/noteflowai/evalarc/tree/main/examples/strands-state-review).
  Two deterministic rules recheck saved states; its equally weighted mean is
  separate from the original five-dimension EvalArc score.
- **Saved AgentCore Evaluate results and spans:** use the
  [export-to-review walkthrough](https://github.com/noteflowai/evalarc/blob/main/docs/agentcore-first-review.md).
  The adapter accepts a bounded input wrapper, not arbitrary cloud exports.
- **Repeated judgments on a fixed trace:** inspect
  [score variation and verdict disagreement](https://glayguo-evalarc.static.hf.space/judge-stability/index.html)
  separately from missing judgments. The five displayed controls are synthetic.
- **A received suite:** download `suite-evidence.zip` and verify the preserved
  configuration, plan, attempts, gates and JUnit offline.

Trying your own records? [Share a first-use finding or setup problem](https://github.com/noteflowai/evalarc/issues/new?template=first-use.yml).
A minimal redacted example is enough.

## Evidence and scope

The saved audits detect **21 declared faults across three task packs**; six
faults each depend on one detecting case. The
[Casebook](https://huggingface.co/datasets/glayguo/evalarc-casebook) contains
251 audit case records, six repeated attempts and three suite jobs in separate
configurations. These public-development controls do not establish coverage
of unseen faults or general model performance.

The recorded suite has two accepted jobs and one fully resolved job out of
three. Consistency, acceptance and full resolution are separate outcomes.
Offline verification recomputes supplied records; it does not authenticate
the producer or rerun the candidate.

The Trace Workbench's five scored controls are synthetic. Its separate MCP
example contains real local delivery and no evaluator scores; no live
AgentCore evaluation is claimed. The
[GPU pilot](https://glayguo-evalarc.static.hf.space/skill-impact/index.html)
contains 27 recorded model trials with every failure retained; it does not
establish skill efficacy or a model ranking.

MIT · Research preview. `manifest.json` identifies the deployed source commit
and SHA-256 of published files. Maintainer publication does not imply
Hugging Face endorsement.

[Source](https://github.com/noteflowai/evalarc) ·
[Methodology](https://github.com/noteflowai/evalarc/blob/main/docs/methodology.md) ·
[Changelog](https://github.com/noteflowai/evalarc/blob/main/CHANGELOG.md)

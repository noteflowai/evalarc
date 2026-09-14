---
title: EvalArc Evidence Lab
emoji: 🔎
colorFrom: green
colorTo: gray
sdk: static
app_file: index.html
pinned: false
license: mit
short_description: Look past the score. Inspect agent grader failures.
tags:
  - agent-evaluation
  - tool-use
  - evaluation
  - reproducibility
  - developer-tools
---

# EvalArc — Look past the score.

**A 93.75% score. A duplicated write. Would your grader catch it?**

Explore saved evidence from two executable task packs for AI-agent evaluation.
Switch between known-good references and 15 declared faulty implementations,
inspect failed checks, and step through tool calls and state changes.

- **Support tools:** a note is committed, its response fails, and a retry with a
  new idempotency key duplicates it. The recorded partial score is 0.9375;
  full resolution fails.
- **Coding artifacts:** treating JSON `true` and `1` as equal breaks
  compare-and-swap. The recorded partial score is 0.925; full resolution fails.
- **Reproduction:** full JSON, grader/candidate/case fingerprints, seeds and
  container image IDs accompany the reports.

The browser replays the committed Docker audits. It does not execute arbitrary
submissions or call a model. The Python CLI has no third-party runtime
dependencies; the bundled trusted controls can run on a CPU.

[Source & quickstart](https://github.com/noteflowai/evalarc) ·
[中文说明](https://github.com/noteflowai/evalarc/blob/main/README.zh-CN.md) ·
[Methodology](https://github.com/noteflowai/evalarc/blob/main/docs/methodology.md) ·
[Security boundaries](https://github.com/noteflowai/evalarc/blob/main/SECURITY.md)

## Scope

Research preview 0.2.0. These are scripted controls and public development
tasks, not held-out frontier-model results. Detection applies only to the
declared faults. No arbitrary reward-hack resistance, human time horizon,
hardware-agent validation or RL improvement is established.

The source and evidence are MIT licensed. `manifest.json` identifies the source
commit and SHA-256 of each published file. Publication is performed by the
maintainer and does not imply endorsement by Hugging Face.

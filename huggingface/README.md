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
· [PyPI package](https://pypi.org/project/evalarc/)
· [中文](https://github.com/noteflowai/evalarc/blob/main/README.zh-CN.md)

No account, installation or model key is needed to explore the saved records.
The featured comparison contains scripted Docker controls, not customer data
or a model leaderboard.

## Actual model configuration comparison

[Review Qwen3-8B and Qwen3.8-27B-FP8](https://glayguo-evalarc.static.hf.space/model-upgrade/index.html):
eight public support-planning cases, three fresh generations per configuration,
all 48 original outputs and native pytest checks. Download and regrade offline.
Plans were not executed; model sizes and quantization differ.
Complete plans improve **15/24 → 19/24**, but **10 named checks lose passes**:
the upgrade gate fails. These checks share two format/schema failures.

[First review with the published CLI](https://github.com/noteflowai/evalarc/blob/main/docs/first-model-review.md): Install the released CLI, download the fixed records, and reproduce the failed model-upgrade gate.
The 30-second walkthrough uses four annotated views of the actual interface,
with captions and source hashes. No GPU or model-service account is needed.

## Start with one review

1. Compare the two revisions and select `retry-after-commit`.
2. Step through the action that duplicates the note in the case explorer.
3. Compare the permissive gate with the strict notes gate. The score stays
   93.75%; acceptance changes with the declared rule.
4. [Install from PyPI and recompute the report](https://github.com/noteflowai/evalarc/blob/main/docs/first-review.md).
   The local review needs Python 3.11+, with no Docker, Node, GPU or model call.

## Bring your own evidence

**A finish signal is not task acceptance.**
[Context controls](https://glayguo-evalarc.static.hf.space/context-controls/index.html)
compare relevant guidance and unrelated prose at 476 tokens per MCP load.
Twelve real Qwen3-8B attempts remain in two separate cohorts, each with 0/6
resolved tasks. Inspect protocol failures, partial scores and unchanged starter
programs, with complete records and an offline download. This diagnostic
follow-up does not establish general skill efficacy.

**Retrieve a prior session and inspect what changed.**
[Funes MCP handoff](https://glayguo-evalarc.static.hf.space/funes-handoff/index.html)
retains six Qwen3-4B continuations, native retrieval receipts and independently
graded programs. Six retrieval results succeed; all six programs remain unchanged
at 87.5%, and none fully resolves the task. Review operation counts alongside
the prior session; they do not estimate work or time saved.

**Keep the reviewed skill version across sessions.**
[Pinned skill handoff](https://glayguo-evalarc.static.hf.space/skill-handoff/index.html)
links a prior MCP load to six new continuations. Both conditions receive the
same historical skill through workflow-selected MCP, and one also offers
Funes retrieval. All six preloads and six historical retrieval results succeed;
the programs remain unchanged and full task acceptance is 0/6. The original
skill, version-rejection control and complete records are downloadable.
This is a separate cohort with a different prior session from the report above.

**Correct answers can accompany an incorrect program.**
The [Harbor control report](https://glayguo-evalarc.static.hf.space/harbor-controls/index.html)
compares three actual container runs. A detached answer file receives 100%
answer reward while the delivered program scores 80% and fails strict
acceptance. Native ATIF, programs, answers and the offline bundle are available.
These are declared scripted controls, without model inference.

- **Matching EvalArc evaluations:** compare changed checks and retain original inputs.
- **Final files and runtime actions:** [inspect behavior records](https://glayguo-evalarc.static.hf.space/behavior-audit/index.html)
  for temporary writes, file access and actual service submissions. The report
  separates 32 authored controls from 12 GPU model attempts and retains every failure.
  [Recheck a recorded case locally](https://github.com/noteflowai/evalarc/blob/main/docs/behavior-first-review.md)
  with the released reviewer and evidence ZIP; no source checkout or candidate execution is needed.
- **Independent-source SWE tasks:** [inspect 36 GPU workflow attempts](https://glayguo-evalarc.static.hf.space/independent-swe/index.html)
  on three public SWE-bench Verified tasks. 31 have assessable native reports,
  five remain uncertain after upstream infrastructure flags, and none is accepted.
  All attempts are also available as a [dataset](https://huggingface.co/datasets/glayguo/evalarc-independent-swe).
- **Strands Evals users:** [inspect the native state review](https://glayguo-evalarc.static.hf.space/strands/index.html)
  without installing, or run the [SDK companion](https://github.com/noteflowai/evalarc/tree/main/examples/strands-state-review).
  Filter all eight checks, compare expected and observed state, and download the offline review.
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

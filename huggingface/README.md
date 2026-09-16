---
title: EvalArc Evidence Lab
emoji: 🔎
colorFrom: green
colorTo: gray
sdk: static
app_file: index.html
pinned: false
license: mit
short_description: Inspect scores, acceptance gates and every agent attempt.
tags:
  - agent-evaluation
  - tool-use
  - evaluation
  - reproducibility
  - developer-tools
---

# EvalArc — Look past the score.

**New in v0.12: same trace, same verdict?** Inspect three saved judgments for
each of five synthetic controls. Separate changing scores, flipped acceptance
decisions and unavailable results; download the complete evidence for offline
verification. All-reject agreement remains rejection. No model or AWS evaluation
was run for these controls. [Judge Stability](https://glayguo-evalarc.static.hf.space/judge-stability/index.html)
· [Import guide](https://github.com/noteflowai/evalarc/blob/main/docs/judge-stability.md).

**Share the exact evidence.** Select a case and trace step, then **Copy evidence
link**. Recipients reopen the same recorded observation. Keyboard users can
inspect a case and return to its list; failed sections can be retried separately.
If one task pack fails to load, the other remains inspectable.

**Python and JavaScript candidates.** Generate starters or independent
references for all three task packs, audit the declared faults, and combine runtimes
in one suite. The task contracts and graders are unchanged. See the
[language guide](https://github.com/noteflowai/evalarc/blob/main/docs/languages.md)
and recorded mixed-language Docker suite; this does not establish a language ranking.

**The score rose from 90% to 93.75%. A previously passing check now fails.**

**New in v0.5: same score, different gate.** Two support jobs use the same
frozen defective policy and score 93.75%, with 0/2 resolved attempts each.
A deliberately permissive gate accepts the partial result; requiring every
notes check rejects it. Inspect the three-job Docker suite, all five attempts,
the original TOML, and JUnit output distinguishing a failed gate from an
environment error. Gate acceptance remains separate from full task resolution.
A hosted CI importer was not exercised.

**Explore the data as tables:** the
[EvalArc Casebook](https://huggingface.co/datasets/glayguo/evalarc-casebook)
offers three separate configurations for 251 audit cases, six repeated attempts
and three suite jobs. Filter the results or load the JSONL in Python; original
source records and fingerprints accompany every row.

**Every v0.4 attempt remains visible.** Switch between three
recorded Docker attempts of the reference and three of the duplicate-write
control. The reference resolves 3/3 attempts; the faulty control resolves 0/3
despite a mean score of 93.75%. Open every attempt, inspect per-check
denominators, and download the full summary and progress JSONL.
No check variation was observed in either scripted control.

The **v0.3 comparison** remains available: compare two recorded support
policies side by side. Two closure
checks improve, while a retry introduces a duplicate note. Inspect all three
changed cases, then open the standalone comparison and individual reports.
`evalarc compare` returns exit code 1 for the regression despite the higher score.

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

The browser replays the committed Docker audits and evaluation records. It does not execute arbitrary
submissions or call a model. The Python CLI has no third-party runtime
dependencies; the bundled trusted controls can run on a CPU.

[Source & quickstart](https://github.com/noteflowai/evalarc) ·
[中文说明](https://github.com/noteflowai/evalarc/blob/main/README.zh-CN.md) ·
[Methodology](https://github.com/noteflowai/evalarc/blob/main/docs/methodology.md) ·
[Security boundaries](https://github.com/noteflowai/evalarc/blob/main/SECURITY.md)

## Scope

Research preview 0.8.0. These are scripted controls and public development
tasks, not held-out frontier-model results. Detection applies only to the
declared faults. No arbitrary reward-hack resistance, human time horizon,
hardware-agent validation or RL improvement is established. Repeated fixed
cases do not establish reliability on unseen tasks or a model success rate.

The source and evidence are MIT licensed. `manifest.json` identifies the source
commit and SHA-256 of each published file. Publication is performed by the
maintainer and does not imply endorsement by Hugging Face.

### Verify a handoff offline

With EvalArc 0.8+, download **suite-evidence.zip** from the lab and unzip it.
Run `evalarc verify suite-evidence --json` to check the original configuration,
plan, all five attempts, custom gates and JUnit without executing a candidate.
The 12 original input files are unchanged: two of three jobs are accepted, one
is fully resolved. Default verification exits 0 for consistency;
`--require-accepted` exits 1 because the strict notes gate rejects the result.
`--require-resolved` separately requires full resolution.
[Workflow and limits](https://github.com/noteflowai/evalarc/blob/main/docs/verification.md).

## Recorded GPU pilot

[Inspect 27 actual model trials](https://noteflowai.github.io/evalarc/skill-impact/): no skill, direct delivery and real MCP, with independent grading and every failure retained. [Composition and public-session handoff records](https://noteflowai.github.io/evalarc/research/) are separate small pilots. No accuracy or memory efficacy gain is claimed.

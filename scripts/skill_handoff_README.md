# Continue with the prior agent's reviewed skill version

This package contains six Qwen3-4B continuations of one published Qwen3-8B
session. The predecessor actually loaded `robot-recording-review` over MCP.
The successor workflow preloads the same historical SKILL.md and bundle
identities over MCP in both conditions; only one condition exposes Funes
history tools to the model.

Open `index.html` to follow the prior load, workflow preload, retrieved passages,
candidate programs and independent acceptance. The complete ZIP includes
original records, source files, compiled provider code, dependency locks and
an internal record inventory. It works offline with JavaScript disabled.

## What was recorded

- Three attempts with the pinned skill and no memory, and three with the same
  skill plus Funes MCP. Public generation seeds: 17, 41 and 97, in alternating
  condition order. Every scheduled attempt is retained.
- Six successful **workflow-selected** MCP preloads. These are harness actions,
  not six model-requested skill discoveries or loads.
- Six successful model-requested historical retrieval results across the three
  Funes attempts. Each returned passage or turn retains its selected source.
- __PROGRAM_SUMMARY_EN__
  A successful load, retrieval or finish signal is not task completion.

The source was selected by time from already published development records:
the earliest Qwen3-8B session with a successful MCP load of the robot skill.
Its result was known. The six new attempts are a separate cohort from the
earlier no-skill handoff and pre-injected-context experiments.

Each attempt uses at most 12 generations, 4,096 output tokens per generation
and 600 seconds of interaction. Skill preload, memory startup and grading
are timed separately. The same authoritative task, starter, diagnostic and
historical skill bytes are supplied to both conditions. The prior and successor
use different models and contexts; comparing them is not a controlled model
ranking or a causal estimate of skill benefit.

## Verify the records

From the matching EvalArc source revision:

```sh
python -m scripts.build_skill_handoff --verify --output /path/to/extracted/evidence
```

The verifier reads the evidence. It checks source identities, actual MCP
receipts, the skill content supplied in the prompt, candidate and evaluation
consistency, operation counts, all six scheduled attempts, frozen input bytes
and derived page content. It neither executes archived code nor reruns inference.
The internal inventory supports verification after ZIP extraction; the hosted
outer manifest additionally binds the ZIP. These checks do not authenticate
the producer.

`validation/` contains scripted checks, not extra model trials. Retrieval,
empty-range and override checks were collected before the cohort; the
source-deletion control and standalone baseline were collected afterward.
The baseline executes the unchanged prior program under the current grader.
`preflight-pin-drift.json` records a new MCP process rejecting changed skill
bytes against the original pins.

The original command used a shared editable Python environment. During-run
and post-run observations show that all 54 imported core source files from
the canonical main checkout matched the frozen feature-tree copy. Their
timestamps are preserved; these observations were not collected before the
first generation. The subsequent recorder rejects a different editable
checkout unless its own source is selected with `PYTHONPATH=src`.

## Reproduce the workflow

Use the frozen source and dependency identities in `experiment.json` and
`frozen/`, the model-file identities in `model-files.json`, and the memory-model
identities recorded before and after execution. Model weights and the Funes
binary must be obtained separately under their upstream terms.

1. Export only the selected public prior trial with `scripts/export_funes_trace.py`.
2. Index that explicit Parquet path using native Funes; use a separate
   `FUNES_HOME` and the prepared public embedding/reranking cache.
3. Bind the original trial, program, export, memory and historical skill with
   `scripts/prepare_skill_handoff.py`, including the provider's license.
4. From the recorder checkout, run `PYTHONPATH=src python scripts/record_handoff_mcp.py`
   with the selected source, native Funes bridge and `--skill-bridge` pointing to
   Skills Anywhere's `examples/skill-impact/bridge.mjs`. Supply the explicitly
   reviewed model endpoint, model files, binary and cache paths.

Do not replace the historical skill with the repository's current version:
the handoff pins intentionally reject that change. The workflow indexes only
the selected generated public session, not a user's private history.

Repeated command and write counts are descriptive operation counts. They
do not establish wasted work, human time saved, general memory efficacy or
native state restoration in a branded client. Public seeds are development
inputs, not hidden tests or an independent final evaluation.

Licenses: `LICENSE`, `source/SKILL-LICENSE.txt`,
`source/ROBOT_DATA_LICENSE.txt` and `source/ROBOT_DATA_NOTICE.md`.

---
pretty_name: EvalArc Casebook — inspect scores, failures and acceptance gates
license: mit
language:
  - en
size_categories:
  - n<1K
task_categories:
  - other
tags:
  - tabular
  - agent-evaluation
  - software-testing
  - reproducibility
  - synthetic
configs:
  - config_name: suite_jobs
    default: true
    data_files:
      - split: development
        path: data/suite_jobs.jsonl
  - config_name: audit_cases
    data_files:
      - split: development
        path: data/audit_cases.jsonl
  - config_name: repetition_attempts
    data_files:
      - split: development
        path: data/repetition_attempts.jsonl
---

# EvalArc Casebook

**The same 93.75% score can pass one acceptance gate and fail another.**
Inspect the rules, actual failed checks and original Docker records in a
filterable table. This is the data companion to the
[interactive evidence lab](https://huggingface.co/spaces/glayguo/evalarc).

In the default `suite_jobs` view, compare `support-partial` and
`support-protected`. Both use the same frozen defective policy, score 93.75%
and fully resolve 0/2 attempts. The deliberately permissive rule accepts partial
progress; the rule requiring every notes check rejects it. `gate_accepted`
and `fully_resolved` are separate columns.

## What is included

| Configuration | Rows | Unit and purpose |
| --- | ---: | --- |
| `suite_jobs` | 3 | One configured gate per job, backed by five Docker attempts; compare acceptance and full resolution. |
| `audit_cases` | 251 | One case execution per scripted control: 135 coding, 32 support and 84 robot-evidence cases across three references and 21 declared faults. |
| `repetition_attempts` | 6 | One recorded attempt of a frozen support policy; three reference and three faulty attempts. |

Each configuration has a single **`development`** split. These are different
units, so their row counts must not be summed into a number of independent
trials or benchmark examples. `evaluation_score` in the case table is the
parent evaluation's score, repeated for navigation; averaging that column
across case rows would reweight evaluations incorrectly.
`control_detection_margin` counts distinct detecting case IDs for the parent
faulty control; references have null in this field. It is repeated for filtering,
and must not be summed across case rows or interpreted as independent trials.

These are saved **scripted controls on public development tasks**, not runs of
a trained language model. Support tickets, identifiers and messages are
synthetic fixtures. No customer data or private logs were collected.

## Use without the web viewer

```python
from datasets import load_dataset

jobs = load_dataset("glayguo/evalarc-casebook", "suite_jobs", split="development")
for job in jobs:
    if not job["fully_resolved"]:
        print(job["id"], job["mean_score"], job["gate_accepted"])
```

No dataset loading script, candidate execution or model credential is required.
You can also download the three JSONL files and read them with Python's standard
`json` module. The `datasets` package is only needed for the example above.

## Inspect a row's evidence

`source_file` points to an unchanged JSON file in this dataset repository.
`source_pointer` is a JSON Pointer locating the exact original object; an empty
pointer means the whole evaluation. `source_sha256` authenticates that file.
`source_url` links the corresponding file at a fixed GitHub commit.

All configurations preserve candidate, grader and case fingerprints and the
recorded runtime. The case table additionally includes original check outcomes
and `case_json`; this retains available support states and tool traces.
The suite configuration, plan, all five attempts and JUnit are included under
`evidence/examples/suite/`. Repetition summaries and all six attempts are included
under their original example directories.

The original records come from EvalArc 0.2, 0.4, 0.5 and 0.9. Their
`recorded_evalarc_version` and grader fingerprints are preserved. Do not treat
the three configurations as matched version comparisons; use the lab's separate
matched comparison for that question.

Build source:
[`@SOURCE_COMMIT@`](https://github.com/noteflowai/evalarc/tree/@SOURCE_COMMIT@).
[`manifest.json`](manifest.json) lists every exported file hash.

```bash
git clone https://github.com/noteflowai/evalarc.git
cd evalarc
git checkout @SOURCE_COMMIT@
python3 scripts/build_dataset.py --output dist/casebook
```

The build validates evaluations, recomputes repetitions and suite decisions,
and checks JUnit before exporting. It does not rerun candidates. See the
[methodology](https://github.com/noteflowai/evalarc/blob/@SOURCE_COMMIT@/docs/methodology.md)
for the task contracts and limitations.

## Intended uses and limits

Use this small casebook to learn grader auditing, inspect retries and
idempotency, test report readers, and discuss acceptance criteria. Reference
implementations and deliberate faults were authored for these tasks; this is
not an exhaustive collection of possible defects.

The repeated controls show no observed check variation. They do not establish
independence, a population reliability estimate or performance on unseen tasks.
The dataset does not support model rankings, arbitrary reward-hack resistance
or RL improvement claims. Public development cases should not be presented
as a held-out benchmark. No hosted CI importer was exercised.

## Authorship and license

Published by the EvalArc maintainer, with AI-assisted development and writing.
Code, task fixtures and these derived records are MIT-licensed; see
[`LICENSE`](LICENSE). No third-party model weights are included.

Related maintainer projects:
[Robot Reel](https://huggingface.co/spaces/glayguo/robot-reel) inspects recorded
Physical AI experiments;
[Skills Anywhere](https://huggingface.co/spaces/glayguo/dsh-skills-anywhere)
provides reusable skill discovery and file checks.
The [project collection](https://huggingface.co/collections/glayguo/noteflow-ai-open-source-playgrounds-6aa693c382b0184786eb8856)
groups these independent tools; it does not imply a shared model evaluation
or upstream endorsement.

# Casebook: filter and reuse the recorded evidence

The [Hugging Face dataset](https://huggingface.co/datasets/glayguo/evalarc-casebook)
provides a tabular companion to the interactive lab. The default `suite_jobs`
view makes an important distinction inspectable: two jobs share a 93.75% mean
score and zero resolved attempts, but their configured gates disagree.

| Configuration | Rows | One row represents |
| --- | ---: | --- |
| `suite_jobs` | 3 | A configured job and its gate decision |
| `audit_cases` | 167 | A case execution within one of 17 scripted controls |
| `repetition_attempts` | 6 | A recorded attempt of a frozen support policy |

The row units differ. Do not add them together as independent trials or average
the parent `evaluation_score` repeated across case rows. Each configuration uses
a `development` split. No training or held-out model test split is claimed.

```python
from datasets import load_dataset

jobs = load_dataset("glayguo/evalarc-casebook", "suite_jobs", split="development")
for job in jobs:
    if not job["fully_resolved"]:
        print(job["id"], job["mean_score"], job["gate_accepted"])
```

Install `datasets` only if using this optional reader. The three JSONL files
are also readable with Python's standard `json` module. EvalArc itself still
has no third-party runtime dependency.

Every row carries the original file path, JSON Pointer, file hash, source commit,
candidate/grader/cases fingerprints and recorded runtime. The bundle includes
unchanged source JSON, all repeated attempts, suite configuration and JUnit.
`case_json`, `checks_json`, `gate_json`, `decision_json` and `runtime_json` are
JSON strings so unrelated task schemas remain readable in a common table.

## Reproduce and publish

From a clean checkout of the commit named in the dataset card:

```bash
python3 scripts/build_dataset.py --output dist/casebook
```

The builder reuses the site's evidence checks, validates each audit evaluation,
recomputes repetitions and suite decisions, and verifies JUnit. It checks row
counts and unique identities, preserves original evidence bytes and writes a
file manifest. An existing output directory is never overwritten.

CI builds the dataset and site from the same source, retaining both artifacts.
The existing publication job requires all tests, Docker audits and browser
checks to pass. It publishes only the current main commit, uses an expected
Hub parent revision, and verifies every uploaded file without credentials.
A retry can initialize an empty dataset owned by the authenticated user; an
existing unrelated dataset is rejected.

The source records come from EvalArc 0.2, 0.4 and 0.5; their original versions
and grader hashes are retained. These are authored development fixtures,
not model-generated trajectories or a matched longitudinal benchmark.
See the full [dataset card](../huggingface/DATASET.md) for authorship,
license, provenance and interpretation limits.

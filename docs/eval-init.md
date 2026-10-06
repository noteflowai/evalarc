# Start an evaluation project

`evalarc eval-init` creates a runnable evaluation project, the offline half of
the article's `build-eval` step: cases, an application stub, a programmatic
grader, an evaluation runner that writes Inspect-format logs, and a hillclimb
configuration, wired to every EvalArc command. `evalarc review-inputs` renders
the cases for you to read before anything runs. [中文](eval-init.zh-CN.md).

```bash
evalarc eval-init my-eval
cd my-eval
evalarc review-inputs cases.jsonl --output ../review --write-split split.json \
  --write-manifest cases.manifest.json
python evaluate.py ../results/baseline.json --epochs 3
evalarc eval-health ../results/baseline.json --cases cases.manifest.json --min-effect 0.05 \
  --plan-attempts 5 --plan-configs 2 --output ../health
evalarc judge-packet grader ../results/baseline.json --sample 20 --output ../spot
evalarc hillclimb-run hillclimb.toml --output ../climb --trust-local
```

The stub routes tickets with keyword rules in `prompt.md`, so every command runs
before you change anything. Replace `respond()` in `app.py` with your model call,
`cases.jsonl` with your cases, and `propose.py` with a model call that edits
`prompt.md`. The generated `README.md` walks through each step.

## Cases

`cases.jsonl` holds one JSON object per line:

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Unique case ID |
| `input` | yes | What the application receives; state every condition the grader checks |
| `check` | yes | `exact`, `contains`, `label`, `json_keys`, `json_schema` or `command` (see `grader.py`) |
| `expected` | yes | The answer; a list of keys for `json_keys`; a JSON Schema for `json_schema`; an argument array for `command` (for example a unit-test runner), which gets the output on stdin and passes on exit 0 |
| `labels` | for `label` | The allowed labels, including `expected` |
| `source` | yes | `production`, `bug_report`, `support_ticket`, `user_traffic`, `manual`, `synthetic`, `model_failure` |
| `difficulty` | for `model_failure` | Why the task itself is hard |
| `held_out` | no | `true` to keep the case away from the tuning loop |

Prefer production sessions (after checking retention and sensitive-data rules),
then bug reports and tickets, then 5–10 hand-written cases, and only then
synthetic cases grounded in those.

## `review-inputs`

Validates every line (exit 2 with the file and line on error), writes a review
page listing each case with its split, source, check, expected answer and
difficulty, and reports `no_held_out`, `held_out_share`, `duplicate_inputs`,
`few_cases`, `dominant_answer` and the source findings from
[`eval-health --cases`](eval-health.md#case-provenance) (`adversarial_sampling`,
`no_real_cases`, `mostly_synthetic`, `traffic_only`). `--write-split` and
`--write-manifest` regenerate `split.json` and the case manifest from
`cases.jsonl`, so the case file stays the single source of truth.
`--require-clean` exits 1 on any warning.

`--random-split F` (with `--seed`) holds out a random share of cases,
stratified by `source` so each source keeps tuning and held-out cases, and writes
the choice into `cases.jsonl` as `held_out`. It refuses to run once `held_out`
is declared, so the split is decided once and cannot be reshuffled after results
are seen.

## What remains yours

Choosing representative cases, writing grading criteria two experts would agree
on, and writing a model judge for open-ended outputs are design decisions.
EvalArc checks them afterwards (`review-inputs`, `eval-health`,
`judge-packet grader`) but cannot make them.

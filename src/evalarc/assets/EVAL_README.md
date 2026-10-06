# Evaluation project

Created by `evalarc eval-init`. It runs end to end with a stub application, so
every step below works before you change anything. Replace the stub and the
example cases with your own.

| File | Purpose |
| --- | --- |
| `cases.jsonl` | One case per line: `id`, `input`, `expected`, `check`, `source`, optional `labels`, `difficulty`, `held_out` |
| `app.py` | The application under evaluation; replace `respond()` with your model call |
| `prompt.md` | The text the hillclimb loop may edit |
| `grader.py` | Programmatic checks: `exact`, `contains`, `label`, `json_keys`, `json_schema`, `command` (e.g. unit tests) |
| `evaluate.py` | Runs every case for several epochs and writes an Inspect-format log |
| `propose.py` | Stub proposer for `evalarc hillclimb-run`; replace with your model call |
| `hillclimb.toml` | Loop configuration: only `prompt.md` may change |
| `split.json`, `cases.manifest.json` | Generated from `cases.jsonl` by `evalarc review-inputs` |

## 1. Choose cases

In order of preference: production sessions (check retention and sensitive-data
rules first), bug reports and support tickets, 5–10 cases you write by hand, and
only then synthetic cases grounded in those. Record each case's `source`. A case
you chose because a model failed it is `model_failure` and needs a `difficulty`
explaining why the task itself is hard. State every condition the grader checks
in the input, so two experts would grade it the same way. Mark about a third as
`"held_out": true`, or let `review-inputs --random-split 0.33` choose them once;
the hillclimb loop never sees them.

## 2. Review the inputs before running anything

```bash
evalarc review-inputs cases.jsonl --output ../review --write-split split.json \
  --write-manifest cases.manifest.json
```

Open `../review/index.html`, read every case, and rerun after each edit.

## 3. Run the baseline and check the evaluation

```bash
python evaluate.py ../results/baseline.json --epochs 3
evalarc eval-health ../results/baseline.json --cases cases.manifest.json \
  --min-effect 0.05 --plan-attempts 5 --plan-configs 2 --output ../health
evalarc judge-packet grader ../results/baseline.json --sample 20 --output ../spot
```

Read `../health/index.html` (per-case scores with outputs) and fix pipeline,
truncation, ambiguous tasks and grader problems first. Judge the spot-check
packet yourself, then `evalarc judge-score ../spot verdicts.json --min-agreement 0.9`.

## 4. Hillclimb

```bash
evalarc hillclimb-run hillclimb.toml --output ../climb --trust-local
```

Review `../climb/index.html` and `../climb/final.diff` before merging.

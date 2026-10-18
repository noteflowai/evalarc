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
| `check` | yes | `exact`, `contains`, `label`, `regex`, `fuzzy`, `json_keys`, `json_schema` or `command` (see `grader.py`) |
| `expected` | yes | The answer; a list of keys for `json_keys`; a JSON Schema for `json_schema`; an argument array for `command` (for example a unit-test runner), which gets the output on stdin and passes on exit 0 |
| `labels` | for `label` | The allowed labels, including `expected` |
| `source` | yes | `production`, `bug_report`, `support_ticket`, `user_traffic`, `manual`, `synthetic`, `model_failure` |
| `difficulty` | for `model_failure` | Why the task itself is hard |
| `held_out` | no | `true` to keep the case away from the tuning loop |
| `min_ratio` | for `fuzzy`, optional | Similarity needed, in (0, 1], default 0.9 |
| `suite` | no | `capability` (a hill to climb, may start at a low pass rate) or `regression` (already works and must pass every trial); copied into the case manifest for [`eval-health --cases`](eval-health.md#case-provenance) |
| `expect_action`, `expect_change`, `impact`, `owner` | no | [Case attributes](eval-health.md#case-attributes), copied into the case manifest: should the agent act or abstain, fail-to-pass or pass-to-pass, impact, and owner |

Prefer production sessions (after checking retention and sensitive-data rules),
then bug reports and tickets, then 5–10 hand-written cases, and only then
synthetic cases grounded in those.

## `review-inputs`

Validates every line (exit 2 with the file and line on error), writes a review
page listing each case with its split, source, check, expected answer and
difficulty, and reports `no_held_out`, `held_out_share`, `duplicate_inputs`,
`few_cases`, `dominant_answer` and the source findings from
[`eval-health --cases`](eval-health.md#case-provenance) (`adversarial_sampling`,
`no_real_cases`, `mostly_synthetic`, `traffic_only`). When any case declares a
`expect_action`, `expect_change` or `impact`, `review.json` counts each; when
any case declares an attribute (including only `owner`), the case table gains
an Attributes column, and the review reports the
`expect_action` balance findings (`one_sided_behavior`, `behavior_imbalance`,
`behavior_undeclared`) and `impact_undeclared` (info). When any case declares
`suite`, it also counts the suites and reports `suite_undeclared` (some cases
declare none) and `no_regression_suite` (none is `regression`), both info,
and the case table gains a Suite column. When `eval-health` lists
`graduation_candidates`, change `suite` in `cases.jsonl` and rerun
`--write-manifest`; editing the manifest directly is overwritten.
`--write-split` and
`--write-manifest` regenerate `split.json` and the case manifest from
`cases.jsonl`, so the case file stays the single source of truth.
`--require-clean` exits 1 on any warning.

`regex` passes when the whole stripped output matches the pattern in
`expected` (Python `re.fullmatch`; add `.*` to allow surrounding text).
`review-inputs` rejects patterns that do not compile or are longer than 1,000
characters; patterns run on your evaluation host, so keep them simple. `fuzzy`
passes when difflib's similarity ratio between the output and `expected`,
ignoring case and repeated whitespace, is at least `min_ratio`. Both tolerate
valid variation better than `exact` and stay deterministic; use a model judge
only when even these are too rigid.

`--prompt FILE...` names the prompt, skill or tool-description files the agent
sees. Everything the grader checks should be stated in the task: a case graded
with `label` needs every allowed label, `json_keys` every key, and
`json_schema` every required key and string enum value, mentioned as a whole
word in those files or in the case input (ignoring case). Otherwise the review
reports `unstated_requirement` (warning) naming the case and missing terms; an
agent that follows the instructions could not know them. The expected answer
itself is not required (that would leak it), and `exact`, `contains`, `regex`,
`fuzzy` and `command` cases are not checked. `review.json` records the files'
names and SHA-256 as `prompt_files`.

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

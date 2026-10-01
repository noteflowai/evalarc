# Review a hillclimbing sequence before merging it

A hillclimbing loop proposes one change at a time (a prompt edit, a skill rule, a
model or thinking-effort switch), reruns the evaluation, and keeps the change only
when it helps. `evalarc hillclimb-review` replays that decision offline from the
saved results: a baseline, then the result after each proposed change, plus a
declared [held-out split](ci-gate.md#held-out-split-did-the-change-generalize).
It does not propose changes, rerun anything or call a model. [中文](hillclimb-review.zh-CN.md).

```bash
evalarc hillclimb-review examples/hillclimb-review/results/00-baseline.json \
  examples/hillclimb-review/results/0[1-5]-*.json \
  --held-out examples/hillclimb-review/split.json --objective cost --min-effect 0.05 \
  --output climb
```

```text
Note: Before the first step: the tuning partition resolves changes of about 27.1%, larger than the 5.0% target. Add cases or repetitions before hillclimbing.
Note: Before the first step: the held-out partition resolves changes of about 31.2%, larger than the 5.0% target. Add cases or repetitions before hillclimbing.
  1. 01-prompt-audit.json: keep (tuning +20.8 pp, held out +18.8 pp, cost 0.891x)
  2. 02-refund-examples.json: rollback_overfit (tuning +14.6 pp, held out +0.0 pp, cost 1.049x)
  3. 03-opus-5.5-low.json: keep (tuning +0.0 pp, held out +0.0 pp, cost 0.463x)
  4. 04-haiku-minimal.json: rollback_regression (tuning -10.4 pp, held out -12.5 pp, cost 0.211x)
  5. 05-sonnet-5-low.json: keep (tuning +0.0 pp, held out +0.0 pp, cost 0.526x)
Final kept: 05-sonnet-5-low.json | held out 71.9% -> 90.6% (within noise) | cost ratio 0.217
Recommendation: merge_cost — Merge: recorded cost fell with no held-out check losing passes and no drop in either partition's pass rate.
```

The example is [authored](../examples/hillclimb-review/README.md): its outcomes and
costs are declared in `build.py`, not measured.

## Rules

Each step is compared with the **last kept** result, not with the baseline:

| Decision | When |
| --- | --- |
| `rollback_regression` | A held-out check lost passes or coverage, or either partition's pass rate fell |
| `rollback_overfit` | Tuning cases improved, held-out cases did not |
| `keep` | Quality objective: both partitions improved. Cost objective: recorded cost fell with neither partition falling, or both improved at no higher cost |
| `rollback_no_gain` | Anything else |

After `--stall-after` consecutive rollbacks (default 2), the failing **tuning**
cases of the last kept result are triaged: `pipeline` (errors, timeouts, skips),
`truncated`, `grader_inconsistent`, `regressed`, `never_passes`, `variable`,
`consistent_failure`. Only consistent failures are candidates for another
change. If the remaining tuning headroom is smaller than the resolvable change,
the report says to stop and add cases or repetitions.

The final kept result is compared with the baseline on held-out cases, with 95%
Wilson intervals:

| Recommendation | Exit | Meaning |
| --- | ---: | --- |
| `merge` | 0 | Quality: held-out cases improved beyond sampling noise, nothing regressed |
| `merge_cost` | 0 | Cost: final/baseline cost below 1 and at most `--max-cost-ratio`; no held-out check lost passes and neither partition fell |
| `no_change_kept` | 1 | Every step was rolled back |
| `do_not_merge_regression` | 1 | The final result is worse than the baseline on held-out checks or either partition |
| `do_not_merge_within_noise` | 1 | Quality objective, but the held-out gain is within noise |
| `do_not_merge_cost` | 1 | Cost did not fall enough, or was not recorded |
| `do_not_merge_leakage` | 1 | `--harness` found held-out case text in prompts, skills or tool descriptions |

Invalid or incomparable inputs exit 2: different formats or tasks, different
case sets between steps, a file listed twice, or `--objective cost` without cost
or tokens recorded on every attempt.

`--output` writes `hillclimb.json`, `summary.md`, `index.html`, `split.json`, byte
copies under `inputs/`, and `tuning-failures.json`. That last file lists only
tuning-case failures and is the file to hand a tuning loop: it contains no held-out
outcomes.

## How the article maps to EvalArc

| Practice in *Automating eval design and hillclimbing with Claude* | EvalArc |
| --- | --- |
| Frontier models still have headroom; warn at ≥95% | `eval-health` `saturated` |
| A task that always fails is often ambiguous or mis-graded | `eval-health` `always_failing`, triage `never_passes` |
| Low variance; the grader gives consistent verdicts on the same output | `eval-health` `flaky_checks`, `inconsistent_grading`; `diff` `same_output_different_verdict`; `judge-run --repeat` judge consistency; `trace-stability` |
| Configuration variance, e.g. a thinking setting that does not take effect | `eval-health` `config_not_applied` |
| State eval size (cases × repeats × models) and estimated runtime; one record per case and a results page with transcripts | `eval-health` size, `--plan-attempts`/`--plan-configs`, `cases.jsonl`, per-case page |
| Cost drivers such as prompt caching | `diff` `usage.cache_read_share` |
| Pipeline checks: timeouts, API errors, truncation | `eval-health` `unassessed_attempts`, `truncated_outputs`, triage `pipeline`/`truncated` |
| The judge must not be the model under test | `eval-health` `self_graded`; `judge-score` `self_judged` |
| LLM judge picks the better output blind to which is the baseline | `judge-packet pairwise` + `judge-run` (your judge command) + `judge-score` (randomized A/B, position-bias check) |
| Programmatic checks where the output space is small | `eval-health` `model_judge_replaceable` |
| Read graded transcripts and check the grader on a small batch | `judge-packet grader` + `judge-score --min-agreement` (false accepts and rejects) |
| Stronger models or more thinking should score higher | `eval-health --ordered` `capability_inversion` |
| Baseline with confidence intervals | 95% intervals in `diff`, `eval-health` and `hillclimb-review` |
| Measure eval noise before the first iteration; compare with the minimum effect | `eval-health --min-effect`, `hillclimb-review` notes |
| Train/test split; roll back when train improves but test does not | `diff --held-out`, `hillclimb-review` `rollback_overfit` |
| Roll back regressions; keep only when both improve | `hillclimb-review` rules |
| Do not paste failing cases into the prompt | `--harness` leakage scan; `tuning-failures.json` excludes held-out cases |
| After 2–3 flat rounds, triage the remaining failures; stop if the gain is below noise | `hillclimb-review` stall triage |
| Same quality at lower cost | `diff --max-cost-ratio`, `hillclimb-review --objective cost` |
| Final report against the baseline; do not merge a gain within noise | `hillclimb-review` recommendation |
| Prefer production sessions, bug reports and tickets over synthetic cases | `eval-health --cases` `no_real_cases`, `mostly_synthetic`, `traffic_only` |
| Do not build the set only from one model's failures | `eval-health --cases` `adversarial_sampling` |

Running the loop and a judge model is covered by `hillclimb-run` and
`judge-run`, which execute your commands (EvalArc itself calls no model): the
propose command sees only tuning failures, may edit only allowed files, and
patches that copy case text are rolled back before evaluation.

The `build-eval` step is covered by `eval-init` (cases, programmatic grader,
runner and loop configuration) and `review-inputs` (the input review page before
any run). Choosing the cases and grading criteria remains design work for you
and your coding agent; EvalArc checks the result (`review-inputs`,
`eval-health`, `judge-packet grader`).
Whether cases match production is declared in the case manifest, not verified.

## Limits

Decisions are replayed from saved results; EvalArc cannot confirm that the steps
are the ones the loop actually ran, or that held-out results were hidden from it.
Pass rates pool check attempts, which are not independent within one case, so
intervals are optimistic. Cost ratios come from one run each. Declare the split
before the first step and change it only in a reviewed commit.

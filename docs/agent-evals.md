# Agent evaluations with EvalArc: the article, mapped

Anthropic's engineering article
[Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
(January 9, 2026) describes how teams build agent evaluations they can trust.
This page maps each of its recommendations to the EvalArc command, finding or
field that applies it, and says plainly which parts EvalArc does not cover.
EvalArc is an offline review layer: it reads results your evaluation harness
already wrote (Inspect AI, promptfoo, JUnit, AgentCore, ATIF) and runs three
built-in task packs. It does not call models, simulate users, drive browsers or
monitor production. [中文](agent-evals.zh-CN.md).

## Terms

| Article | EvalArc | Notes |
| --- | --- | --- |
| Task (problem, test case) | Case; a task pack for built-ins | One line of `cases.jsonl`, one Inspect sample, one promptfoo test, one JUnit testcase |
| Trial | Attempt (Inspect epoch, promptfoo repeat, repeated testcase) | A case-level trial succeeds only when every check passed ([trials](eval-health.md#case-level-trials-passk-and-passk)) |
| Grader with assertions | Check (scorer, assertion, testcase result) | `diff` compares each case and check separately |
| Transcript (trace, trajectory) | Recorded messages, trace or `trace.jsonl` | Inspect messages with `--transcript-metrics` / `--include-transcript`; built-in packs keep the full trace |
| Outcome | Final state checked by the host | Built-in verifiers read host-owned state; a claimed success has no scoring authority |
| Evaluation harness | The tool that wrote the results; `evaluate`, `repeat`, `suite` for built-ins | EvalArc reads its output |
| Agent harness (scaffold) | Prompt, skill and tool files given to `--harness` | Scanned for leaked case text; edited by `hillclimb-run` within `allow` |
| Evaluation suite | A result file, a TOML suite, or a `capability` / `regression` suite role | Suite roles come from the case manifest |

## Recommendation by recommendation

### Graders

| Recommendation | In EvalArc |
| --- | --- |
| String match: exact, regex, fuzzy | `eval-init` checks `exact`, `contains`, `label`, `regex`, `fuzzy` ([eval-init](eval-init.md)) |
| Binary tests: fail-to-pass, pass-to-pass | `expect_change` in the case manifest; `diff --cases --require-f2p` ([ci-gate](ci-gate.md#over--and-undertriggering-fail-to-pass-and-impact)) |
| Static analysis: lint, type, security | One stable test per analyzer, compared with `diff` ([recipe](../examples/static-analysis/README.md)) |
| Outcome verification | Built-in packs grade host-owned final state; [behavior review](https://noteflowai.github.io/evalarc/behavior-audit/index.html) checks actual service submissions |
| Tool-call verification | Built-in support trace; imported runs: tool-call counts with `--transcript-metrics`. See [grade outcomes, not paths](#grade-outcomes-not-paths) |
| Transcript analysis: turns, tokens | `usage` in `diff`; `--transcript-metrics` adds turns, tool calls, messages and error retries, gateable with `--cost-metric turns` |
| Model-based graders and their calibration | `eval-health` flags `self_graded` and `model_judge_replaceable`; `judge-packet grader` measures a grader against blind human or model judgments ([judging](judging.md)) |
| Multi-judge consensus, inter-annotator agreement | `judge-score PACKET A.json B.json C.json`: pairwise and Fleiss' kappa, majority or unanimous consensus, `--min-annotator-agreement` |
| Pairwise comparison, A/B | `judge-packet pairwise` with randomized hidden order and position-bias detection |
| Give the judge a way out ("Unknown") | `unsure` in grader packets; `--allow-unsure` in pairwise packets |
| Weighted, binary or hybrid scoring | Built-in weighted dimensions plus full resolution; TOML suite gates ([suites](suites.md)) |

### Capability, regression and non-determinism

| Recommendation | In EvalArc |
| --- | --- |
| Capability evals start low; regression evals stay near 100% | `"suite": "capability"` / `"regression"` per case; `regression_case_failing`, `diff --require-regression-suite`, `hillclimb` rollback on a broken regression case |
| Graduate saturated capability cases | `graduation_candidates` |
| pass@k and pass^k | Unbiased estimators per file and per suite in `eval-health` and `diff --cases` |
| Changes within noise | 95% Wilson intervals, `within_sampling_noise`, `noise_exceeds_min_effect`, `--min-effect` |

### Building the task set

| Recommendation | In EvalArc |
| --- | --- |
| Start with 20–50 tasks from real failures | `eval-init` scaffold; `few_cases` below 20 |
| Source from manual checks, bug trackers, support queues | `source` per case; `no_real_cases`, `mostly_synthetic`, `adversarial_sampling` |
| Prioritize by user impact; ownership | `impact` and `owner` per case; `diff --cases` lists blocking changes by impact with owners |
| Unambiguous tasks that two experts grade alike | `review-inputs` page to read every case; `judge-score` with two or more annotators |
| Everything the grader checks is stated in the task | `review-inputs --prompt` raises `unstated_requirement` |
| 0% after many trials means a broken task; a reference solution per task | `always_failing`, `never_passes`; `eval-health --reference` raises `reference_fails` and triages `task_or_grader_broken`; built-in packs run a reference and declared faults |
| Balanced problem sets; over- and undertriggering | `expect_action` (`act` / `abstain`) per case; `one_sided_behavior`; over- and undertriggering in `eval-health` and `diff --cases` |

### Harness, graders and maintenance

| Recommendation | In EvalArc |
| --- | --- |
| Isolated, clean environment per trial | Built-in Docker runs ([isolation checklist](#trial-isolation-checklist)); `--cluster-errors` flags correlated infrastructure failures |
| Deterministic graders where possible | `model_judge_replaceable`, `inconsistent_grading` |
| Partial credit | Built-in weighted score separate from full resolution |
| Bugs in tasks and graders | `capability_inversion`, `always_failing`, `reference_fails`, `limit_reached`, `truncated_outputs`, `config_not_applied` |
| Graders resistant to hacks | Built-in graders run outside the candidate; audits with declared faults; `--harness` leakage scan; `hillclimb-run` pasted-case rollback |
| Read the transcripts | `eval-health --output` writes `cases.jsonl` and an index of outputs; `judge-packet --include-transcript`; built-in case explorer |
| Saturation | `saturated`, `graduation_candidates` |
| Open contribution of tasks | [Contribute cases by pull request](#contribute-cases-by-pull-request) |
| Eval-driven development and tuning | `hillclimb-run` / `hillclimb-review` with held-out cases and rollback rules |

## Grade outcomes, not paths

Prefer checking what the agent produced or changed over the exact sequence of
steps it took. Agents regularly find valid approaches the task author did not
anticipate, so a check that a particular tool was called in a particular order
punishes creativity and turns a correct answer into a failure. In EvalArc:

- Built-in task packs grade final, host-owned state: the support pack checks the
  ticket queue, notes and closure, not which tool calls produced them.
- In `eval-init` projects, grade the answer (`label`, `json_schema`, `command`)
  rather than parsing the transcript for tool names.
- Use transcript data as a constraint or a cost, not as correctness: a turn or
  tool-call budget with `--cost-metric turns`, or a check that a forbidden side
  effect did not happen.
- Check a specific tool call only when the call itself is the outcome, for
  example that a refund was submitted exactly once.

## Trial isolation checklist

Trials that share state are not independent: leftover files, caches, shared
databases or a visible git history can make later trials easier, and one
resource limit can fail many trials at once. EvalArc enforces isolation only in
its built-in Docker backend (`--network=none`, read-only root and candidate
mount, CPU, memory and PID limits, a fresh state directory per case; see
[SECURITY.md](../SECURITY.md)). For results produced elsewhere, check:

- Each trial starts from a fresh checkout or container, without the git history
  or files left by earlier trials.
- Caches, scratch folders and databases are reset or per trial.
- The agent cannot read the grader, the expected answers or other trials' outputs.
- Resource limits are high enough not to fail trials; use
  `eval-health --cluster-errors` to see whether failures share one cause.
- Trials of one case use the same budget and configuration; `config_not_applied`
  and `limit_reached` catch some mismatches.

Correlated trials make pass^k, intervals and noise estimates optimistic. EvalArc
cannot verify isolation in an external harness; these checks are yours.

## Contribute cases by pull request

People closest to users (product managers, support, sales) can add cases
without touching the harness. Keep cases in `cases.jsonl` and review every
change in CI:

```yaml
# .github/workflows/eval-cases.yml
name: Review eval cases
on:
  pull_request:
    paths: ["evals/cases.jsonl", "evals/prompt.md"]
permissions:
  contents: read
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"
      - run: python -m pip install evalarc==0.21.0
      - run: >-
          evalarc review-inputs evals/cases.jsonl --prompt evals/prompt.md
          --write-manifest evals/cases.manifest.json --output review --require-clean
      - run: git diff --exit-code evals/cases.manifest.json
```

The job fails on an invalid case (exit 2), on any review warning (exit 1:
for example unstated requirements, one-sided behavior, duplicate inputs, no
held-out cases or no real-world sources)
and when the committed manifest is stale. Pin the version, and give reviewers
the `review/index.html` artifact to read each new case.

## What EvalArc does not cover

| Article layer | Status |
| --- | --- |
| Automated evals before release and in CI | Covered for recorded results and built-in packs |
| Manual transcript review | Supported: blind packets, transcripts, case explorer; the reading is yours |
| Systematic human studies | Measurement only (`judge-score` agreement); recruiting and training raters is yours |
| A/B tests with real traffic | Not covered; `judge-packet pairwise` is an offline preference check, not a live experiment |
| Production monitoring, user feedback | Not covered |
| Simulated users, browser and computer-use environments | Not covered; import their results instead |
| Research-agent groundedness and source quality | Not covered as a pack; import a judge's results and calibrate it with `judge-score` |
| Latency: time to first token, output tokens per second | Not reported; supported exports carry no streaming timestamps |

No single layer catches every failure. Use EvalArc as the offline gate and
review layer, alongside production monitoring and user feedback.

# Check an evaluation before tuning against it

An evaluation that is saturated, noisy or partly broken rewards changes that do
not help users. `evalarc eval-health` reads saved Inspect AI, promptfoo or JUnit
result files for one evaluation and reports what to fix first. It is offline: it
does not rerun the evaluation or call a model. [中文](eval-health.zh-CN.md).

```bash
evalarc eval-health examples/results-diff/inspect/baseline.json \
  examples/results-diff/inspect/current.json --ordered --min-effect 0.05 --output health
```

```text
Eval health: 1 warning(s) | Pass rate: baseline.json 62.5%, current.json 84.4%
  info: flaky_checks — 1 of 32 repeated check(s) both passed and failed across attempts. ...
  warning: noise_exceeds_min_effect — At 32 assessed check attempts and a 84.4% pass rate, only changes larger than about 25.2% separate from sampling noise, above the 5.0% you want to detect. Record about 811 assessed check attempts per run (more cases or more repetitions).
Report: health/index.html
```

`--output` creates a new folder with `health.json`, `summary.md`, an offline
`index.html` and byte-for-byte copies of the inputs under `inputs/`.

## Findings

| Finding | Severity | Raised when | What to inspect |
| --- | --- | --- | --- |
| `saturated` | warning | the best file passes at least `--saturation` (default 95%) of check attempts | Add harder cases that two domain experts would grade the same way, or tune for cost and latency at equal quality |
| `always_failing` | warning | a check fails on every assessed attempt in every file (at least two attempts) | Task wording and grader first: unstated requirements, ambiguous tasks and grader bugs look like a permanent capability gap |
| `flaky_checks` | warning above 10% of repeated checks, otherwise info | a check both passes and fails across attempts in one file | Ambiguous tasks, inconsistent grading of one output, unstable configuration, state left over between attempts. Regrade one fixed output with [`evalarc trace-stability`](judge-stability.md) |
| `unassessed_attempts` | warning | attempts have errors, timeouts or skips | Fix the pipeline before tuning so infrastructure failures are not read as model behavior |
| `single_attempt` | info | every check was recorded once | Record repeats (Inspect `--epochs`, promptfoo `--repeat`) |
| `noise_exceeds_min_effect` | warning | with `--min-effect D`, the change two runs of this size can resolve is larger than D | Add cases or repetitions; the message gives the approximate attempt count |
| `capability_inversion` | warning, or info within noise | with `--ordered`, a later (stronger) file scores lower than an earlier one | A stronger model or more thinking should not score lower; look for ambiguous tasks or a miscalibrated grader |
| `inconsistent_grading` | warning | a byte-identical recorded output was graded both passed and failed (within or across files) | The grader is nondeterministic or changed; use a deterministic check or pin and regrade the grader |
| `truncated_outputs` | warning | an attempt stopped at a token limit (`max_tokens`, `length`, an Inspect token limit) | Raise the limit or shorten the task; a truncated answer measures the budget |
| `config_not_applied` | warning | an Inspect log requests `reasoning_effort` (other than none/minimal) or `reasoning_tokens`, but every attempt records 0 reasoning tokens | The setting may not have reached the model; check the parameter name, model support and overrides |
| `model_judge_replaceable` | info | a model-graded check saw at least 10 outputs with at most 10 distinct values, or only JSON | Use an exact match, a fixed label set or a JSON schema check; keep model judges for open-ended outputs |
| `self_graded` | warning | the model under test is also the judge: a model-graded Inspect scorer without a `model` option or `grader` role, or a promptfoo grading provider equal to the tested provider | Name a separate judge model |

Outputs are compared by SHA-256 of the recorded completion (Inspect
`output.completion`, promptfoo `response.output`); JUnit records no outputs, so
grading consistency, truncation and self-grading are not assessed for it.

## Failure triage

The report classifies each failing case in the last file, first matching rule
wins, so the cause is known before anything is changed:

| Category | Rule | Next step |
| --- | --- | --- |
| `pipeline` | a failing check has errors, timeouts or skips | Fix the pipeline; not a model failure |
| `truncated` | an attempt hit a token limit | Raise the limit or shorten the task |
| `grader_inconsistent` | the same output got different verdicts | Fix or pin the grader |
| `regressed` | fails every attempt here but passed in an earlier file | Inspect what the change broke |
| `never_passes` | fails every attempt in every file | Read the task and grader for ambiguity |
| `variable` | passes on some attempts | Add attempts; separate agent from grader variation |
| `consistent_failure` | fails, single attempt | Candidate for a root-cause fix |

Each run row also carries a 95% Wilson interval, mean recorded duration and cost.

The resolvable change is twice the 95% normal-approximation half-width at the
last file's pass rate, the same non-overlap rule `evalarc diff` uses for its
[sampling-noise flag](ci-gate.md#sampling-noise-annotation). Attempts of one
case are not independent, so this is an optimistic lower bound.

Exit codes: **0** the report was produced; with `--require-healthy`, **1** when
any warning was reported; **2** unreadable or incomparable inputs, invalid
options or an existing output folder. Inputs must share a format and, for
Inspect, a task name.

## Size, plan and per-case records

Every report states the size of the last file: cases × attempts × files, with
the recorded duration and cost per configuration. `--plan-attempts K` and
`--plan-configs M` estimate a planned run from the recorded mean duration and
cost per attempt:

```text
Plan: 8 cases × 5 attempt(s) × 3 configuration(s) = 120 case attempts, about 4.0 min serial.
```

`--output` also writes `cases.jsonl`, one line per file, case and attempt with
its verdicts, output, stop reason and usage, and `index.html` lists every case
of the last file with its passing check attempts and a link to its recorded
outputs. Read some of those outputs before trusting the grader.

## Case provenance

Saved results do not say where a case came from. `--cases MANIFEST` reads an
`evalarc.case-manifest.v1` file that declares a source per case ID or glob
(first match wins) and, optionally, why a case is hard:

```json
{
  "schema_version": "evalarc.case-manifest.v1",
  "cases": [
    {"match": "refund-*", "source": "support_ticket", "difficulty": "refund limits and duplicate detection interact"},
    {"match": "status-*", "source": "production"},
    {"match": "cancel-pending", "source": "model_failure"}
  ]
}
```

Sources: `production`, `bug_report`, `support_ticket`, `user_traffic`, `manual`,
`synthetic`, `model_failure`. Findings:

| Finding | Severity | Raised when |
| --- | --- | --- |
| `adversarial_sampling` | warning | a case is `model_failure` with no `difficulty`: chosen because one model failed it, which measures that model rather than the task |
| `no_real_cases` | warning | no case comes from production, bug reports, tickets or user traffic |
| `mostly_synthetic` | warning | more than half the declared cases are synthetic |
| `traffic_only` | info | every case is user traffic, which under-represents hard requests |
| `provenance_undeclared` | info | some cases match no manifest entry |

Every entry must match a recorded case. The manifest is copied to `cases.json`
in the output folder. Provenance is declared, not verified; confirm retention and
sensitive-data rules before using production sessions.

## Limits

A finding points to something to read, not a proven defect, and a clean report
does not show that the cases match production traffic. Choose cases from
production logs, bug reports and support tickets where you can, and do not
build the set only from one model's failures: that measures that model's weak
spots instead of the task.

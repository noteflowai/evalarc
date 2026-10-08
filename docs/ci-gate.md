# Gate pull requests on changed checks

A headline score can rise while a check that used to pass starts failing.
`evalarc diff` reads two saved result files from the same evaluation, pairs
every case and check, and fails when any check loses passes or disappears. It
reads Inspect AI logs, promptfoo `--output` JSON and JUnit XML (pytest,
DeepEval via pytest, and most test runners). It does not rerun the evaluation or
call a model. [中文](ci-gate.zh-CN.md).

`evalarc diff` and the GitHub Action ship in 0.14.0. To run the diff outside
the Action, install the released version from PyPI:

```bash
python -m pip install evalarc==0.14.0
```

## Try it on recorded results

The [examples](../examples/results-diff/README.md) were produced by Inspect AI
0.3.268, promptfoo 0.123.1 and pytest 8.4.2 with scripted replies, so no model
key is needed to reproduce them. From a checkout:

```bash
evalarc diff examples/results-diff/inspect/baseline.json \
  examples/results-diff/inspect/current.json --output inspect-diff
```

```text
match accuracy: 0.625 -> 0.8125 | Checks that lost passes or coverage: 3 | Improved: 6 | Unchanged: 7
  1 within sampling noise (record more attempts to separate from repeat-sampling variation; the gate still fails)
  regressed: refund-duplicate / includes
  regressed: refund-duplicate / match
  less_reliable: cancel-pending / match
Report: inspect-diff/index.html
```

The command exits **1**. Inspect's accuracy improved, but the current revision
now refunds a duplicate order in both epochs, and one exact-match check passes
in only one of two epochs. The promptfoo example keeps the same 75% pass rate
while a different test fails; the JUnit example turns one passing test into a
skip.

`--output` creates a new folder with `diff.json`, `summary.md`, an offline
`index.html` and byte-for-byte copies of both inputs. Their SHA-256 digests are
recorded in `diff.json`, so a reviewer can rerun the same comparison.

## What changes fail the gate

Each check's pass count is compared across all recorded attempts (Inspect
epochs, promptfoo repeats, repeated JUnit cases).

| Change | Meaning | Fails the gate |
| --- | --- | --- |
| `regressed` | Passed before; no current attempt passes | yes |
| `less_reliable` | Pass rate fell but some attempts still pass | yes |
| `unassessed` | Passed before; now only errors or skips | yes |
| `less_covered` | Fewer attempts were assessed than in the baseline, so the pass rate cannot count as unchanged or improved | yes |
| `removed` | The check or case is missing from the current run | yes |
| `improved` | Pass rate rose | no |
| `added` | New in the current run | no |

A current Inspect log whose status is not `success` also fails the gate.
A rerun with fewer epochs or with lost samples fails the gate as `less_covered`
until the attempt counts match or a new baseline is committed; a falling pass
rate is still reported as `regressed` or `less_reliable` first.
Removing a failing check fails too: deleting it would otherwise turn a red gate
green.

**Unfinished baseline.** A baseline Inspect log whose status is not `success`
(an interrupted or errored run, often missing samples) fails the gate as well.
Otherwise every check missing from it would appear as `added`, which never
blocks, and missing evidence would read as new coverage. `diff` exits **1**,
`diff.json` records `"baseline_incomplete": true` (the key is omitted for a
finished baseline), `summary.md` and `index.html` say the baseline is
incomplete, and the terminal prints:

```text
The baseline run is incomplete (status error); 2 check(s) appear only in the current run and were not compared. Rerun the baseline to completion; the gate fails.
```

Rerun the baseline to completion (or commit a finished result file) and compare
again. EvalArc does not reconstruct missing samples. Exports that record no run
status, such as JUnit, are never marked incomplete.

Exit codes: **0** no check lost passes, **1** at least one did, **2** the files
could not be read or compared (different formats, different Inspect task names,
no samples, malformed input, an Inspect sample repeated in the same epoch).
Treat 2 as a broken pipeline, not a regression.

An Inspect log that contains the same sample ID twice in one epoch (an integer
`7` and a string `"7"` count as the same ID) exits 2 and names the sample
and epoch. Counting the copy as an extra attempt would overstate coverage and
could hide a `less_covered` change. Such logs usually come from merging,
concatenating or editing results; re-export with
`inspect log dump LOG.eval > LOG.json` or rerun the evaluation. The same ID in
different epochs is a normal repeated attempt, and samples without an integer
`epoch` are not checked.

## Sampling-noise annotation

A single evaluation is a sample. When a check records more than one attempt
(Inspect epochs, promptfoo repeats, repeated JUnit cases), `diff` marks a change
**within sampling noise** when both sides show variation and their 95% Wilson
intervals overlap, so the recorded number of attempts cannot separate the change
from repeat-sampling variation. `diff.json` carries `within_sampling_noise` on
each affected change and `blocking_changes_within_sampling_noise` at the top
level; `summary.md`, `index.html` and the CLI line repeat the count.

This is a descriptive flag, not a significance test, and it **never relaxes the
gate**: a flagged regression still exits 1. It answers a different question than
the gate — whether the recorded evidence is enough to trust the direction of the
change. A clean all-pass to all-fail swing is the strongest signal available at
that attempt count and is never called noise. To resolve a flagged change,
record more attempts per check (Inspect `--epochs`, promptfoo `--repeat`); if
the change persists, it was real, and if it disappears, it was noise. This
mirrors the practice of requiring a gain to exceed evaluation noise before
acting on it.

## Held-out split: did the change generalize?

When a change was tuned against some evaluation cases, those cases alone cannot
show that it will help elsewhere. Declare which cases were **not** looked at while
making the change, in a small JSON file:

```json
{
  "schema_version": "evalarc.case-split.v1",
  "description": "Status and address cases were not used while revising the answers.",
  "held_out": ["status-*", "address-change"]
}
```

Entries are exact case IDs or glob patterns; each must match at least one case,
and at least one case must remain for tuning. Then:

```bash
evalarc diff examples/results-diff/inspect/baseline.json \
  examples/results-diff/inspect/current.json \
  --held-out examples/results-diff/inspect/split.json \
  --harness examples/results-diff/inspect/harness
```

```text
Held-out split: held_out_gain_within_noise | tuning +15.0 pp (5 cases) | held out +33.3 pp (3 cases)
Harness leakage: 2 hit(s) in 1 file(s), 2 from held-out cases
  examples/results-diff/inspect/harness/system-prompt.md:9 input of status-missing
  examples/results-diff/inspect/harness/system-prompt.md:9 expected of status-missing
```

`diff` compares the pass rate of check attempts in each partition and reports
one state:

| State | Meaning |
| --- | --- |
| `held_out_regressions` | A held-out check lost passes or coverage |
| `generalizes` | Held-out cases improved beyond sampling noise (non-overlapping 95% Wilson intervals) |
| `overfitting_signal` | Tuning cases improved beyond noise; held-out cases did not |
| `held_out_gain_within_noise` | Held-out cases improved, but the recorded attempts cannot separate it from noise |
| `no_measurable_gain` | Neither partition improved beyond noise |

In the recorded example, the three held-out cases rise from 8/12 to 12/12
passing attempts. Twelve attempts are not enough to call that beyond noise, so
the state is `held_out_gain_within_noise`. The split file is copied to
`split.json` in the output folder with its SHA-256 in `diff.json`.

The split is only as independent as its declaration: EvalArc cannot confirm that
held-out results were hidden from whoever made the change. Keep the held-out
cases out of the files, logs and failure transcripts the author or tuning loop
reads, and change the split only in a reviewed commit.

## Harness leakage scan

`--harness PATH ...` scans prompt, skill, instruction and tool-description files
(or folders; hidden entries and binary files are skipped) for recorded case
inputs and expected answers copied verbatim. Matching ignores case and
whitespace; strings shorter than `--leak-min-chars` (default 12) are ignored.
Inputs come from Inspect sample inputs and promptfoo test variables; expected
answers come from Inspect targets and positive promptfoo assertion values
(`not-*` and code assertions are skipped). JUnit reports carry neither, so
nothing is scanned for them.

The example prompt contains `"What is the status of order 9999?" ->
status:9999:unknown`, a held-out input and its reference answer. A tuning loop
that pastes failing cases into the prompt raises the score without helping on
new inputs. Paraphrased or encoded copies are not detected, and a shared
phrase can be legitimate; review each hit.

## Require generalization

`--require-generalization` (requires `--held-out`) additionally fails the gate
unless the state is `generalizes` and no held-out case text was found in the
harness. Without it, the split and leakage sections are informational and the
exit code is unchanged. Both examples above exit 1 because checks regressed.

## Cost at equal quality

When an evaluation is near saturation, the useful change is often the same
quality at lower cost: a smaller model, lower thinking effort, a shorter prompt
or better prompt caching. `diff.json` always includes a `usage` block with the
mean usage per attempt over cases present in both runs, for every metric the
tool recorded:

| Metric | Inspect AI | promptfoo | JUnit |
| --- | --- | --- | --- |
| `cost_usd` | `model_usage.*.total_cost` | `cost` | — |
| `total_tokens`, `input_tokens`, `output_tokens` | `model_usage` sums | `tokenUsage` | — |
| `cached_input_tokens`, `reasoning_tokens` | cache reads, reasoning tokens | `cached`, `completionDetails.reasoning` | — |
| `duration_seconds` | sample `working_time` (else `total_time`) | `latencyMs` | test `time` |

Missing values stay unknown and are never counted as zero; each metric reports
how many attempts recorded it. When input and cache-read tokens are both
recorded, `usage.cache_read_share` gives the share of input tokens read from the
prompt cache, a main cost driver. The Markdown and HTML reports add a "Cost and
usage" section when cost or tokens were recorded.

`--max-cost-ratio R` adds a gate: current mean usage per attempt must be at most
`R` times the baseline (`1.0` = no increase, `0.5` = at least halve it). The
quality gate still applies, so a cheaper run that loses a check fails.
`--cost-metric auto` (the default) uses recorded cost, else total tokens;
`cost`, `tokens` and `duration` select one explicitly. If the chosen metric is
missing on any matched attempt, or the baseline mean is zero, the comparison
exits 2 rather than guessing.

```bash
evalarc diff baseline.json current.json --max-cost-ratio 0.5
```

```text
Cost gate (cost_usd): current/baseline 0.412, limit 0.5 — pass
```

EvalArc does not price tokens. Token counts from different models use different
tokenizers and prices, so prefer recorded cost when the model changes. A JUnit
duration times the test, which may not include the agent. Ratios come from one
run each and carry no interval; repeat runs when the margin is small.

## How each format maps to checks

| Format | Case | Check | Passed when |
| --- | --- | --- | --- |
| Inspect AI log | sample `id` | each scorer (dictionary values become `scorer/key`) | `C`, `true`, or a number ≥ `--threshold` (default 1.0) |
| promptfoo JSON | test description (plus vars when descriptions repeat; provider and prompt index when a run has several) | each assertion (`metric` name, or type and value) | the assertion's `pass` |
| JUnit XML | `classname::name` | `passed` | no `failure`, `error` or `skipped` element |

`I`, `N` and `P` (partial) Inspect scores count as not passed. Errors and
skips are unassessed, not failures. Inspect's `.eval` archives use zstd, which
Python reads from 3.14. On earlier versions, run Inspect with
`--log-format json` or convert with `inspect log dump LOG.eval > LOG.json`.

## Use the GitHub Action

The action installs EvalArc from its own revision into a virtual environment,
runs the diff, appends the summary to the job summary and exposes
`gate-passed`, `blocking-changes` and `report` outputs. It runs on Linux and
macOS runners with Python 3.11+.

```yaml
- uses: noteflowai/evalarc@v0.14.0 # or a full commit SHA
  with:
    baseline: evals/baseline.json
    current: results/current.json
- uses: actions/upload-artifact@v4
  if: always()
  with:
    name: evalarc-diff
    path: evalarc-diff/
```

Inputs: `baseline`, `current` (required), `format` (`auto`), `threshold`
(`1.0`), `output` (`evalarc-diff`, must not exist yet) and
`fail-on-regression` (`true`; set `false` to report without failing). Unusable
input always fails the step. Optional `held-out` (split file), `harness`
(space-separated paths) and `require-generalization` (`false`) add the
[held-out review](#held-out-split-did-the-change-generalize) and
[leakage scan](#harness-leakage-scan); their results are exposed as the
`generalization-state` and `leakage-hits` outputs and as warning annotations on
the leaking file and line. `max-cost-ratio` and `cost-metric` add the
[cost gate](#cost-at-equal-quality); its ratio is the `cost-ratio` output.

```yaml
- uses: noteflowai/evalarc@v0.16.0
  with:
    baseline: evals/baseline.json
    current: results/current.json
    held-out: evals/split.json
    harness: prompts/ skills/ tools.json
    require-generalization: "true"
```

To review every step of a tuning loop rather than one change, use
[`evalarc hillclimb-review`](hillclimb-review.md). Before tuning against an
evaluation, run [`evalarc eval-health`](eval-health.md)
on its results to find saturation, never-passing checks, flaky checks and
pipeline errors.

### Where the baseline comes from

**Committed baseline.** Keep an accepted result file in the repository
(for example `evals/baseline.json`) and update it in a reviewed commit when a
change is intended. This is the simplest option and makes baseline updates
visible in code review.

**Base-branch run.** Evaluate the pull request's base commit in the same job,
then the head commit. Use this when results depend on the code under review and
the evaluation is cheap and deterministic enough to run twice:

```yaml
name: Evaluation regressions
on: pull_request
permissions:
  contents: read
jobs:
  diff:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.base.sha }}
          path: base
      - uses: actions/checkout@v4
        with:
          path: head
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - name: Evaluate both revisions with the same configuration
        run: |
          (cd base && npx promptfoo@0.123.1 eval --no-cache -o ../baseline.json) || true
          (cd head && npx promptfoo@0.123.1 eval --no-cache -o ../current.json) || true
      - uses: noteflowai/evalarc@v0.14.0
        with:
          baseline: baseline.json
          current: current.json
```

promptfoo exits nonzero when a test fails, hence `|| true`; the diff still exits
2 if a result file was not written. For repeated model calls, record several
attempts (Inspect `--epochs`, promptfoo `--repeat`) so `less_reliable` separates
flaky checks from consistent failures.

### Comment on the pull request

The job summary needs no extra permissions. To also post `summary.md` as a
comment, grant `pull-requests: write` and add:

```yaml
- if: always() && github.event.pull_request.head.repo.full_name == github.repository
  env:
    GH_TOKEN: ${{ github.token }}
    PR: ${{ github.event.pull_request.number }}
  run: gh pr comment "$PR" --body-file evalarc-diff/summary.md --edit-last --create-if-none
```

Pull requests from forks receive a read-only token, so the condition skips them.

## Limits

The comparison trusts each tool's recorded pass/fail decisions and scores; it
does not regrade outputs or authenticate the files. Matching is by recorded
identifiers: renaming a promptfoo test description or Inspect sample ID appears
as one removed and one added check. Numeric scores below full credit count as
not passed unless you lower `--threshold`; a fall from 0.9 to 0.6 at the default
threshold is not reported. Use the [EvalArc audit workflow](workflow.md) when
you also need to check the grader itself.

In `summary.md`, the run status, the headline metric name and the case and check
identifiers in the change table are escaped (pipes as `\|`, backticks as
apostrophes, line breaks including carriage returns as spaces), so a crafted
value cannot add a heading or a passing verdict; `diff.json` keeps them
unmodified. The same rule covers the harness-leakage table (file, case and
matched text), and the `eval-health` and `judge-score` Markdown summaries (file,
case, check and judge model names, and values embedded in finding text, in code
spans, which GitHub does not autolink; the rest of the finding text on one line
with Markdown and HTML punctuation backslash-escaped). HTML reports escape every
value. Escaping protects the rendered summary only; it does not validate or
change the recorded evidence.

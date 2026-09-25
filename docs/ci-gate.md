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
| `removed` | The check or case is missing from the current run | yes |
| `improved` | Pass rate rose | no |
| `added` | New in the current run | no |

A current Inspect log whose status is not `success` also fails the gate.
Removing a failing check fails too: deleting it would otherwise turn a red gate
green.

Exit codes: **0** no check lost passes, **1** at least one did, **2** the files
could not be read or compared (different formats, different Inspect task names,
no samples, malformed input). Treat 2 as a broken pipeline, not a regression.

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
input always fails the step.

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

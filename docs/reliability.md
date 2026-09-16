# Repeatability and execution evidence

`evalarc repeat` evaluates one frozen candidate on the same cases several
times. Each attempt receives a fresh workspace, processes, and case state.
Durable KV still preserves state across restarts within a case. The command
works with all built-in task packs and their existing command manifests.

For repeated **judge** decisions on the same saved execution, see
[Judge Stability](judge-stability.md). This guide covers fresh candidate
executions; those observations must not be pooled with judge repetitions.

```bash
evalarc init workspace/repeated-support --task support-routing --reference
evalarc repeat workspace/repeated-support --task support-routing \
  --seeds 17 41 97 --attempts 3 --case-timeout 60 --progress \
  --output runs/repeated-support
```

Docker is the default backend and requires the chosen image to be available.
For the bundled trusted policy, add `--backend local --trust-local`.
The original candidate is snapshotted before the first attempt: edits to its
source directory between attempts do not change later submissions.
Use a new output directory for each run.

## Read the result

The HTML summary links to every attempt's full evidence. These are descriptive
observations on a fixed set of public cases. Repetition does not expand task
coverage or establish a success rate on unseen work.

| Summary field | Meaning |
| --- | --- |
| `requested_attempts` / `completed_attempts` | Intended attempts and recorded evaluations |
| `assessed_attempts` / `invalid_attempts` | Fully assessed evaluations and evaluations with environment failure |
| `resolved_attempts` | Assessed evaluations in which every check passed |
| `all_attempts_resolved` | Every requested attempt completed and resolved |
| `mean_score`, `min_score`, `max_score` | Scores from fully assessed attempts; `null` when there are none |
| `assessed_resolution_rate` | Resolved divided by assessed attempts, with its denominator explicit |
| `variable_cases` / `variable_checks` | Items with both passed and failed observations |
| Per-case/check `passed` / `assessed` | Pass counts and assessed denominators for that item |

Environment failures are neither successes nor agent failures. Repetition
stops after the first invalid evaluation; its summary records the remaining
unrun attempts through the requested/completed counts. A partially assessed
evaluation contributes its valid case observations to case/check rates, but
does not contribute an aggregate score or a resolved attempt. There is no
best-attempt selection, automatic retry of invalid trials, or resume support.

A case can fail in every attempt while individual checks vary. Inspect
`variable_checks` as well as `variable_cases`. No independence assumption,
confidence interval, significance test, or general population estimate is
provided. An all-passing scripted reference is a functional control, not a
model benchmark.

## Budgets and diagnostics

`--timeout` defaults to 10 seconds per protocol exchange.
`--case-timeout` defaults to 60 seconds for the case's protocol execution,
including startup and elapsed time between process restarts. Both must be
positive finite numbers. A fresh case receives a fresh deadline.

Exceeding a budget produces an assessed agent error; checks follow each task's
existing scoring rules. Cleanup may outlast the protocol deadline: Docker
removal has a separate 20-second timeout and local process waiting allows 5
seconds. Cleanup exceptions make the case unassessed and still release local
processes and pipes where possible. These limits do not guarantee termination
after a host crash or forced kill.

Each evaluation case includes `processes` diagnostics: observed exit code,
captured stdout/stderr byte count, and the last 2048 captured stderr bytes.
Decoding replaces incomplete UTF-8 sequences. These are bounded diagnostics,
not a full process-output archive. The existing combined output limit applies
per process session. Candidate output never becomes progress metadata or
authoritative scoring input.

## Files, progress, and exit status

```text
runs/repeated-support/
  repetition.json
  index.html
  events.jsonl
  attempts/
    0001/evaluation.json
    0001/index.html
    0002/evaluation.json
    0002/index.html
    ...
```

`evaluate` and `audit` also save `events.jsonl`. `--progress` streams the same
host-owned JSONL to stderr, with UTC timestamps, task/case identity, lifecycle
events, and completion status. Repetition adds attempt numbers; audits add
control names. Event schemas are versioned as `evalarc.event.v1`.
The CLI summary stays on stdout.

To retain progress when cancelling, redirect stderr to a file outside the
candidate and output directories:

```bash
evalarc repeat workspace/repeated-support --task support-routing \
  --attempts 3 --progress --output runs/repeat-02 2> repeat-02.events.jsonl
```

Completed artifacts are published together. On cancellation or setup failure,
unpublished artifacts are removed. With `--progress`, the external stream ends
with `run_cancelled` or `run_error` for handled failures; those terminal events
are not a completed report. Abrupt process or worker termination can leave
temporary files and an incomplete external stream.

| Exit code | Meaning for `repeat` |
| --- | --- |
| `0` | All requested attempts resolved |
| `1` | All attempts assessed, at least one did not resolve |
| `2` | Invalid/incomplete run or usage/setup error |
| `130` | User cancellation |

The Python `repeat(..., on_attempt=callback, on_event=callback)` API returns the
summary. Use `on_attempt(index, evaluation)` to persist full evidence; without
that callback, only compact summary inputs remain between attempts. Indices
start at 1. `summarize_attempts` validates existing evaluation records and
rejects mismatched candidate, task, grader, cases, runtime, weights, or coverage.

See [migration notes](migration.md), [execution boundaries](../SECURITY.md),
and the [v0.4 validation record](validation-v0.4.md).

# Suites and CI acceptance

`evalarc suite` coordinates multiple candidates, tasks, and repeated evaluations
from a versioned TOML file. Each job has its own score and gate. The suite
passes only when every job is valid and meets its declared gate.

Start with the [runnable configurations](../examples/suites/README.md).
The [recorded example](../examples/suite/index.html) shows the same faulty
policy accepted by a permissive gate and rejected by a gate protecting notes.
Its underlying task outcomes are identical.

## Declare a plan

```toml
schema_version = "evalarc.suite-config.v1"
name = "Release acceptance"

[[jobs]]
id = "support"
task = "support-routing"
candidate = "./workspace/support"
seeds = [17, 41, 97]
attempts = 3

[jobs.runtime]
backend = "docker"
image = "python:3.12-slim"
timeout = 10.0
case_timeout = 60.0
output_limit = 1048576

[jobs.gate]
min_mean_score = 1.0
min_resolution_rate = 1.0
required_dimensions = ["scope", "protocol"]
```

All defaults are shown except `attempts`, which defaults to **1**.
`runtime` and `gate` tables are optional. Default seeds are `[17, 41, 97]`.
Candidate paths resolve relative to the configuration file; `--output` resolves
relative to the CLI's working directory. Environment variables, tildes, and
shell substitutions are not expanded inside configuration paths.

```bash
evalarc suite acceptance.toml --dry-run
evalarc suite acceptance.toml --progress --output runs/acceptance-01
```

The preview validates keys, task names, candidate directory existence, limits,
and gates. It prints `evalarc.suite-plan.v1` JSON with planned attempts and case
executions. It does not open candidate files, launch candidates, or contact
Docker. Candidate command validation happens later in the bounded, regular-file
snapshot. A preview does not establish runtime/image readiness or candidate behavior.

Unknown keys are rejected, including misspelled gate settings. Job IDs must
be unique lowercase slugs, at most 64 characters, beginning with a letter or
digit. A suite has 1–100 jobs, each with 1–100 unique integer seeds and 1–100
attempts. The total limits are 1000 attempts and 100000 planned case executions.
Configuration files are limited to 1 MiB.

## Keep acceptance separate from scoring

| Gate | Default | Meaning |
| --- | --- | --- |
| `min_mean_score` | `1.0` | Mean score across fully assessed attempts must meet the threshold |
| `min_resolution_rate` | `1.0` | Fraction of fully resolved attempts must meet the threshold |
| `required_dimensions` | `[]` | Every applicable check in these dimensions must pass in every attempt |

Thresholds are finite numbers from 0 to 1, compared against recorded values.
Required dimension names belong to the selected task. Every gate also requires
all requested attempts to complete and be valid; this condition cannot be
disabled by lowering thresholds.

To allow partial progress, lower both thresholds deliberately. A job can then
be accepted while `fully_resolved` is false. HTML labels this outcome explicitly.
For example, a support policy scoring 0.9375 can meet a 0.90 mean-score gate with
`min_resolution_rate = 0`, yet fail `required_dimensions = ["notes"]` because
it duplicates a note. Every failed requirement and affected case remains visible.

Suite gates do not change task checks, scores, weights, or acceptance in the
individual evaluation. There is no mean score across jobs or domains, ranking,
significance test, or estimate of general agent capability. Repeated results
keep the [fixed-case interpretation](reliability.md).

## Inputs and execution boundaries

All candidate directories are snapshotted and command/image setup is checked
before the first job executes. Jobs referencing the same resolved candidate
path share that initial snapshot. Edits to the original directory during the
suite do not alter later jobs. Each job still gets fresh per-attempt workspaces,
processes, and state through `repeat`.

The original TOML bytes and SHA-256 are preserved alongside the resolved plan.
Each job records candidate/grader/case fingerprints and actual runtime metadata.
Snapshots are temporary; archive candidate source and runtime dependencies
separately if you need to reproduce a run elsewhere. Pin an installed EvalArc
version and avoid modifying its grading source during execution.

Configuration cannot grant local trust, supply a Docker command wrapper, or
replace a task's verifier. Any local job requires `--trust-local` on the CLI.
Use `--docker-command` or `EVALARC_DOCKER` for a host-selected Docker wrapper.
The existing [execution boundaries](../SECURITY.md) still apply.

Configuration/preflight failures stop before any candidate execution and publish
no report. After execution begins, a recorded invalid evaluation stops that
job's remaining attempts; subsequent jobs still execute. Its invalid outcome
always rejects the suite. Jobs execute sequentially; there is no worker pool,
resume feature, or whole-suite time limit.

## Output and exit codes

```text
runs/acceptance-01/
  suite.toml       # exact input configuration
  plan.json       # resolved paths, defaults, planned workload
  suite.json      # decisions and per-job metrics
  index.html
  junit.xml
  events.jsonl
  jobs/support/
    repetition.json
    index.html
    events.jsonl
    attempts/0001/evaluation.json
    attempts/0001/index.html
    ...
```

JUnit contains **one testcase per job gate**. Class names include the task ID,
and test names use unique job IDs. An assessed rejection is `<failure>`; an
invalid/incomplete evaluation is `<error>`. `<system-out>` retains observed
metrics, gate settings, full-resolution status, and an evidence path. It does
not embed candidate stderr or full tool traces. XML-invalid control characters
are replaced. The exporter is tested with XML parsing; no hosted CI importer
run is claimed.

Exit codes are `0` for all gates accepted, `1` for assessed gate failures, `2`
for invalid jobs or configuration/runtime setup errors, and `130` for
cancellation. JUnit importers may only display results; use the CLI exit code
as the required acceptance check.

Retain `junit.xml` and the entire run directory as CI artifacts, including on
failure. For a GitHub Actions job that has already installed EvalArc, prepared
candidate workspaces, and made the Docker image available:

```yaml
- name: Evaluate acceptance suite
  run: evalarc suite acceptance.toml --output runs/acceptance
- uses: actions/upload-artifact@v4
  if: always()
  with:
    name: evaluation-evidence
    path: runs/acceptance/
```

Output directories must be new and outside every candidate directory. Completed
artifacts publish together. Cancellation or an unhandled run error removes
unpublished artifacts, including completed jobs in that unfinished suite.
Use `--progress 2> acceptance.events.jsonl` to retain external progress on
cancellation; keep that file outside candidates and the output directory.
The suite stream adds job IDs to the existing `evalarc.event.v1` events.

See the [validation record](validation-v0.5.md) for the checks actually run.

## Verify a received suite without executing it

With EvalArc 0.8+, keep the original TOML, plan, suite JSON, JUnit and all job
attempts together. Run `evalarc verify received/suite --json --require-accepted`
to recompute configured gates offline. Full resolution is a separate condition,
available through `--require-resolved`. Original candidate paths are metadata;
do not rewrite them when moving the evidence. [Handoff guide](verification.md).

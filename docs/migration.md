# Migration notes

## EvalArc v0.5 → v0.6

`init` and `audit` accept `--language python|javascript`; Python remains the
default. Default Python workspace bytes and audit source controls are unchanged.
JavaScript templates need Node.js 22+. Choose `--image node:22-slim` explicitly
for Docker; image selection does not follow the language flag.

JavaScript workspaces contain `main.js`, a command manifest, the task contract,
and runtime notes. `evaluate`, `repeat`, and `suite` execute that manifest with
their existing options. Local JavaScript audits resolve Node from the host PATH
and record the absolute executable path. See the [language guide](languages.md).

Initialization now stages all files before publishing the workspace. Existing
destinations are still refused; a write failure removes partial output.

No evidence schema, task contract, task case, or grading/runtime source changes.
Existing matching v0.4/v0.5 records remain comparable. Different-language or
different-image runs still fail the matched-command/runtime requirements.

## EvalArc v0.4 → v0.5

`evalarc suite CONFIG.toml` adds declarative, sequential multi-job execution.
Use `--dry-run` to validate a plan without starting candidates. Local jobs need
`--trust-local` on the CLI; a configuration file cannot grant itself host trust
or specify a Docker wrapper. See the [suite guide](suites.md).

New schemas are `evalarc.suite-config.v1`, `evalarc.suite-plan.v1`, and
`evalarc.suite.v1`. Each job uses the existing `evalarc.repetition.v1` and
`evalarc.evaluation.v2` evidence. A suite exports one JUnit test per job gate.
Invalid jobs produce JUnit errors and exit code 2; assessed gate failures
produce JUnit failures and exit code 1.

Gate thresholds only affect suite acceptance. They do not rewrite task scores,
checks, or full-resolution flags. The default gate requires all attempts to
resolve. A more permissive gate can accept unresolved work; that distinction is
explicit in both the JSON and HTML reports.

The grading sources, task contracts, runtime enforcement, and fingerprints are
unchanged from v0.4. Evaluations remain comparable when their task, seeds,
grader, cases, command, and runtime metadata match. The new suite coordinator
is not part of the grading fingerprint.

## EvalArc v0.3 → v0.4

`evalarc repeat` runs 1–100 attempts of one frozen candidate, writes every
attempt's evaluation JSON and HTML, and produces `evalarc.repetition.v1`.
An invalid attempt stops repetition; the summary preserves the requested,
completed, assessed, and invalid counts. See [repeatability](reliability.md).

`evaluate`, `audit`, and `repeat` save `events.jsonl` using `evalarc.event.v1`.
`--progress` streams the same events to stderr. Standard output retains the
human-readable command result. Cancellation exits with code 130 and removes
unpublished output; externally redirected progress remains available.

`--case-timeout` defaults to 60 seconds, alongside the existing 10-second
response timeout. Its deadline spans process restarts within a case; cleanup
can extend wall time beyond the protocol budget. Evaluation schema v2 adds
`runtime.case_timeout_seconds` and per-case `processes` diagnostics, including
captured output bytes, exit code, and the last 2048 captured stderr bytes.

Both task contracts remain v0.1.0, with unchanged cases and scoring weights.
Runtime enforcement and grading-source fingerprints change. Old v2 files
remain readable, but comparisons and checkpoint trajectories must not combine
v0.3 and v0.4 runs. Re-run both candidates with matching v0.4 conditions.
Historical example reports retain their original version and evidence.

## EvalArc v0.2 → v0.3

The package version is `0.3.0`. Both task contracts, grading rules, and evaluation
schema v2 remain unchanged. `evaluate` now writes an offline HTML report beside
its JSON. `doctor` inspects runtime readiness, and `compare` identifies check
regressions across matching evaluations. See the [workflow guide](workflow.md).

CLI outputs no longer overwrite existing paths. `audit`, `evaluate`, and
`compare` require a new output directory; `trajectory` requires a new file.
Scripts that previously reused a default output path should supply unique run
names. Output within a candidate workspace is rejected.

Comparisons support consistent `evalarc.evaluation.v2` records, including v0.2
reports. They reject invalid evaluations and mismatched experimental conditions.
New outputs use `evalarc.comparison.v1` and `evalarc.doctor.v1`.

## EvalArc v0.1 → v0.2

The package version is now `0.2.0`; both built-in task contracts are version
`0.1.0`. Existing default coding commands continue to work. Select
`--task support-routing` for the new tool workflow; use `evalarc tasks` to list
the built-in registry. Custom commands are optional and documented in
[candidate commands](candidate-commands.md).

New evaluation/audit reports use `evalarc.evaluation.v2` and `evalarc.audit.v2`.
They add task domain, command metadata, run validity, per-case status/checks, and
unassessed results. `score` and `mutation_score` can be `null` on environment
failure. Consumers must check `valid` before interpreting aggregate scores.
The trajectory utility rejects invalid scores and compares schema and command.
Its own output shape remains `evalarc.trajectory.v1`.

Snapshot fingerprints now include normalized executable permission. Grading
fingerprints cover the common evaluator/runtime/registry and the selected pack's
source files. Old and new runs are not comparable checkpoints. Archived examples
are regenerated by execution, not by relabeling old JSON.

## Original local rename: GradeRail → EvalArc

The [historical naming review](naming.zh-CN.md) preserves the original decision
and search snapshot. The project was renamed before its first public package
release. EvalArc keeps the existing Durable KV task contract and grading weights.
Runtime identifiers change as follows:

| Item | Initial local prototype | Selected name |
| --- | --- | --- |
| Repository directory | `graderail` | `evalarc` |
| Python distribution | `graderail` | `evalarc` |
| Python imports | `graderail.*` | `evalarc.*` |
| CLI | `graderail` | `evalarc` |
| Docker command override | `GRADERAIL_DOCKER` | `EVALARC_DOCKER` |
| Report schemas | `graderail.evaluation.v1`, `graderail.audit.v1`, `graderail.trajectory.v1` | `evalarc.evaluation.v1`, `evalarc.audit.v1`, `evalarc.trajectory.v1` |
| Package version field | `graderail_version` | `evalarc_version` |

At the rename, the software and `durable-kv` task versions remained `0.1.0`. There is no
legacy command alias or automatic rewrite of old reports. The naming research,
Git history, and bibliography keys retain historical names where they identify
the original records.

For a checkout with the original editable install, recreate its virtual
environment after moving the repository, or uninstall the old distribution and
install the new checkout. Virtual-environment scripts often contain absolute
paths.

From a fresh environment in the renamed checkout:

```bash
python -m pip install -e .
evalarc --help
python -m evalarc --help
```

Renaming imports and runner identifiers changes the grading-code fingerprint.
Recorded examples are regenerated by running the renamed package; historical
scores are not relabeled as new executions. Checkpoints collected before and
after the rename have different grader fingerprints and must not be combined
into one comparable trajectory.

The rename itself did not change v0.1's coding-only scope. v0.2 adds the
support-routing simulation described above. Neither version includes a browser
environment or LLM-provider adapter.

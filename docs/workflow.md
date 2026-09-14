# Run, inspect, and compare evaluations

These commands are available in EvalArc v0.3. The two task contracts and grading
rules are unchanged from v0.2.
Executed checks are recorded in [v0.3 validation](validation-v0.3.md).

## Check the installation

```bash
evalarc --version
evalarc tasks --json
evalarc doctor
```

`doctor` inspects the host and configured Docker image. It does not pull an image,
start a container, or execute a candidate. A missing image or unavailable Docker
command appears as a failed check. Use the same `--image`, `--docker-command`,
or `EVALARC_DOCKER` setting that you intend to use for evaluation.

For a local candidate:

```bash
evalarc doctor --backend local --task support-routing \
  --candidate examples/support-node --json
```

This checks the snapshot, manifest, and executable availability using the
runner's search path. Local inspection does not require `--trust-local` because
the candidate is never started. In Docker mode executable availability inside
the image is explicitly `not_checked`; image inspection alone cannot establish
that an arbitrary command will run.

## Inspect one evaluation

```bash
evalarc init workspace/support --task support-routing --reference
evalarc evaluate workspace/support --task support-routing --output runs/support-001
```

Each `evaluate` run now produces:

- `evaluation.json`: complete evidence and metadata.
- `index.html`: offline dimension scores, case outcomes, failed checks, and
  expandable case evidence, including support-tool traces.

The report marks an environment failure as unassessed. A high partial score is
displayed alongside full-resolution status. Host execution times include
overhead and are not model or human task-duration baselines.

See the [recorded evaluation example](../examples/evaluation/index.html).

## Compare two revisions

Run the same task and seeds with the same runtime settings before and after
editing a candidate, then compare the saved JSON:

```bash
evalarc compare runs/baseline/evaluation.json runs/current/evaluation.json \
  --output runs/comparison-001
```

Comparison requires matching schema, task identity, grading-code fingerprint,
case fingerprint, seeds, runtime, dimension weights, and case/check coverage.
Candidate fingerprints and creation times may differ. Case display order does
not affect the comparison.

Matching runtime metadata covers the recorded settings, not every installed
dependency. Archive the interpreter and dependencies as described in
[candidate commands](candidate-commands.md).

The reader checks that case outcomes, validity, dimension totals, and aggregate
scores agree. Duplicate JSON keys, nonfinite values, malformed records, and
inconsistent claims are rejected. Input files are limited to 64 MiB each.
This is consistency checking, not authentication of whoever produced the data.

Every passing-to-failing check is reported as a regression, even if another
improvement raises the total score. A comparison with no regressions can still
contain unresolved cases. Invalid evaluations cannot be compared.

The output directory contains `comparison.json`, `index.html`, and copies of
`baseline.json` and `current.json`, so the report can be shared with its evidence.
The [recorded comparison](../examples/comparison/index.html) demonstrates a
score increase from 0.9 to 0.9375 that introduces a duplicate-note regression.

## Output ownership

`evaluate`, `audit`, and `compare` require a **new output directory**, including
when using their default output paths. Existing files and directories are never
replaced. Use a new run name for each attempt. A candidate's own directory
cannot contain its evaluation output.

Files are staged beside a reserved output directory and published together on
successful completion. Configuration errors or interrupted Python execution
clean up unpublished staging files. An assessed failure or invalid evaluation
still produces a complete report, because that outcome is useful evidence.
Abrupt worker termination can leave an empty reservation or staging directory;
choose a new path and inspect the abandoned files before manual cleanup.

`trajectory` also refuses an existing output file. Its JSON file is published
only after serialization completes.

## Exit codes

| Command | `0` | `1` | `2` |
| --- | --- | --- | --- |
| `evaluate` | Fully resolved | Assessed task failure | Invalid evaluation or usage/setup/output error |
| `audit` | Reference passes and every declared fault is detected | Valid audit fails | Invalid audit or usage/setup/output error |
| `compare` | No observed check regression | At least one check regressed | Incompatible/invalid inputs or output error |
| `doctor` | Available readiness checks pass | At least one check fails | Invalid CLI arguments or unsupported configuration |

Neither comparison nor readiness checks call a model API. Browser environments,
provider adapters, and training integrations remain outside this release.

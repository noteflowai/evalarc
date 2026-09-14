# Python and JavaScript candidates

EvalArc's evaluator remains Python 3.11+. Version 0.6 packages Python and
JavaScript starters and scripted references for both task packs. Candidate
language does not select the verifier or change the scoring contract.

| Command | Python | JavaScript |
| --- | --- | --- |
| `init` | Default; creates `main.py` and `TASK.md` | `--language javascript`; also creates `evalarc.toml` and `RUNTIME.md` |
| `init --reference` | SQLite service or ticket policy | JSON-snapshot service or independent ticket policy |
| `audit` | Default; existing controls | `--language javascript`; the same 8 coding / 7 support faults |
| `evaluate`, `repeat`, `suite` | Execute the candidate manifest or default command | Execute the generated manifest; no language flag needed |

## Generate and evaluate

After installing EvalArc, run from the repository root:

```bash
docker pull python:3.12-slim
docker pull node:22-slim
evalarc init workspace/kv-python --reference
evalarc init workspace/kv-javascript --language javascript --reference
evalarc init workspace/support-javascript --task support-routing --language javascript --reference

evalarc doctor --candidate workspace/kv-javascript --image node:22-slim
evalarc evaluate workspace/kv-javascript --image node:22-slim --output runs/kv-javascript
evalarc evaluate workspace/support-javascript --task support-routing \
  --image node:22-slim --output runs/support-javascript
```

Omit `--reference` to generate unfinished starter code. The starter produces
valid protocol responses but does not complete the task. Initialization needs
neither Node nor Docker, refuses existing destinations, and publishes a
complete workspace only after all files have been written.

Docker image selection is explicit. The language option does not replace the
default Python image. Node.js 22+ must be in the chosen image; no packages are
installed at evaluation time. The exact immutable image ID is recorded.

## Audit the controls

```bash
evalarc audit --language javascript --image node:22-slim \
  --seeds 17 --output runs/js-coding-audit
evalarc audit --task support-routing --language javascript --image node:22-slim \
  --seeds 17 --output runs/js-support-audit
```

Audits apply the existing named defects to each language's reference source,
then run every control through the existing host verifier. Success requires
the reference to resolve and each defect to fail in its declared dimension.
The [recorded audits](../examples/javascript-audits/README.md) retain the
commands, candidate fingerprints, image IDs, checks, and traces. These are
scripted controls on public development tasks, not model performance results
or a bound on undiscovered grader defects.

## Run multiple languages together

The generated workspaces above match the paths in the example suite:

```bash
evalarc suite examples/multilanguage/suite.toml --dry-run
evalarc suite examples/multilanguage/suite.toml --output runs/multilanguage
```

The three jobs choose their own task, image, cases, and full-resolution gate.
All candidates and images are preflighted before the first job starts. Results
retain separate scores and a JUnit testcase per job gate.
The [recorded Docker suite](../examples/multilanguage/run/index.html) preserves
all three jobs and their 34 case executions.

`compare` and checkpoint trajectories still require matching recorded runtime
commands and conditions. A Python/Node pair, or a pair using different images,
is not automatically a matched comparison. Shared task checks let you inspect
conformance; they do not establish a language ranking.

## Local execution and other languages

For trusted candidates only, append `--backend local --trust-local` to an
evaluation or audit. Candidate subprocesses use a minimal PATH. If Node lives
in nvm or another version manager, put its absolute executable path in the
workspace's `evalarc.toml`. Local JavaScript audits resolve Node from the host
PATH themselves and record the resulting command. Docker manifests should
keep the container command, usually `"node"`.

TypeScript can be compiled before evaluation and launched through the same
command manifest. EvalArc does not include a TypeScript compiler or SDK.
A prebuilt Rust executable can use the generic command interface, but this
release does not supply or validate a Rust reference/worker.

## Durable reference semantics

The Node reference is independent of the Python SQLite implementation. It
stores a complete JSON snapshot, flushes it, and renames it before acknowledging
each mutation. Only acknowledged mutations surviving process crashes are in
the task contract; this is not a production database or a power-loss claim.

It retains numeric source text using the Node 22 JSON APIs. This preserves
integers larger than JavaScript's exact Number range and distinguishes `1`
from `1.0`. CAS compares nested JSON values independent of object property
order, while retaining Boolean/number, integer/float, and signed-float-zero
distinctions. Equivalent floating spellings compare equally. Map-based storage
supports keys such as `__proto__` without treating them as object metadata.

The [validation record](validation-v0.6.md) describes protocol edge cases,
fault detection, packaging, and runtime checks. Tests do not expand the
published grader's case set or alter its fingerprint.

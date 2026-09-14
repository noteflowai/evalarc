<p align="center"><img src="docs/assets/banner.svg" alt="EvalArc — Run agents. Measure outcomes." width="960"></p>

<p align="center">
  <strong>Open environments and evaluations for AI agents.</strong><br>
  Python 3.11+ · Linux host · No runtime dependencies · MIT · Research preview
</p>

<p align="center">
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="docs/research.zh-CN.md">Research & papers</a> ·
  <a href="docs/architecture.md">Architecture</a> ·
  <a href="docs/methodology.md">Methodology</a> ·
  <a href="docs/roadmap.md">Roadmap</a>
</p>

EvalArc is a research preview for **auditable agent evaluations**. It starts by
checking whether a grader can distinguish correct work from plausible defects:
run known-good and deliberately flawed submissions, inspect the evidence, and
record exactly what was evaluated.

**v0.3 includes two working task packs**, a shared evidence format, and
configurable candidate commands:

| Task | Interaction | Host verification | Declared faults |
| --- | --- | --- | ---: |
| `durable-kv` | Run a coding agent's completed service | Responses, transactions, restart durability | 8 |
| `support-routing` | Drive a policy through simulated ticket tools | Routing, exact notes, closure, unrelated state, protocol | 7 |

v0.3 adds `evalarc doctor`, individual HTML reports, and `evalarc compare` for
check regressions that a higher average score can hide. Every run preserves
earlier outputs. See the [run-and-compare guide](docs/workflow.md).

The support pack records tool calls and state changes, including retries after
ambiguous write outcomes. Python and JavaScript scripted policies use the same
host verifier. Browser environments, LLM-provider adapters, and RL training
integrations remain planned. No frontier-model benchmark result is claimed.

## Run an audit

From this checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
docker pull python:3.12-slim
evalarc audit --seeds 17 41 97 --output runs/audit
```

The command evaluates the reference and eight negative controls, writes
`runs/audit/audit.json`, and creates a standalone `runs/audit/index.html` report.
Exit code `0` means the reference passed and every declared defect was detected
in its intended dimension. Exit code `1` means an audit or candidate failed;
`2` indicates a usage/configuration error or an invalid run caused by an
environment failure.

For the bundled, trusted controls, a faster CPU-only demo is:

```bash
evalarc audit --backend local --trust-local --output runs/local-audit
evalarc audit --task support-routing --backend local --trust-local --output runs/support-audit
```

Local execution has the host user's privileges. Use Docker for candidate
isolation and read the [execution boundaries](SECURITY.md).
If your Docker setup requires a wrapper, set `EVALARC_DOCKER` to that command
or pass `--docker-command`.

## Coding task

| Dimension | Weight | Representative evidence |
| --- | ---: | --- |
| Basic behavior | 25% | Overwrite, deletion, JSON values, seeded state machine |
| Validation | 15% | Reject bad inputs without mutating state or terminating |
| Transactions | 20% | Commit complete batches; roll back invalid batches |
| Compare-and-swap | 15% | Match, mismatch, absent keys, Boolean/number distinction |
| Persistence | 15% | State survives clean process restarts |
| Crash recovery | 10% | Acknowledged writes survive SIGKILL and restart |

There are **15 cases per seed**. Scores average cases within a dimension, then
apply the weights above. Full resolution requires every case to pass.
The eight controls cover false acknowledgements, memory-only storage, partial
batches, unconditional CAS, weak JSON equality, ignored deletes, invalid keys,
and commits deferred until exit.

In the bundled Docker audit, the Boolean/number equality defect earns a
**0.925 partial score** but fails full resolution. The report identifies the
specific CAS check that detects it. Partial progress and acceptance are separate.

The grader computes expectations outside the candidate container; it never
accepts a candidate's claimed reward. The SQLite reference and the in-memory
oracle use different implementations. Each report records the candidate, grader,
and case fingerprints, runtime limits, seeds, and resolved container image ID.

## Evaluate a coding agent's output

```bash
evalarc init workspace/durable-kv
# Give this workspace and its TASK.md to your coding agent.
# After it edits main.py:
evalarc evaluate workspace/durable-kv --seeds 17 41 97 --output runs/candidate
```

For the coding pack, the CLI evaluates completed artifacts; it does not record
the process that produced them. Use `evalarc init --reference workspace/reference`
to create the positive control. Custom entrypoints are described in the
[candidate command guide](docs/candidate-commands.md).

## Tool-using agents

```bash
evalarc tasks
evalarc init workspace/support --task support-routing --reference
evalarc evaluate workspace/support --task support-routing --output runs/support
```

Replace the scripted reference with a policy that speaks the
[support JSONL protocol](src/evalarc/assets/SUPPORT_TASK.md). The evaluator sends
observations; the candidate requests tool operations or finishes. Only the
host's resulting ticket state determines business scores. Claimed success has
no scoring authority. A case is resolved only when every check passes.

In the [recorded support audit](examples/support-audit/index.html), retrying a
committed note with a new idempotency key earns **0.9375** but fails acceptance
because it duplicates the note. The trace shows the error, retry, and state changes.

An [independent JavaScript policy](examples/support-node/README.md) demonstrates
a non-Python entrypoint:

```bash
evalarc evaluate examples/support-node --task support-routing \
  --backend local --trust-local --output runs/support-node
```

This command requires Node.js. The Python core has no third-party runtime
dependencies. EvalArc does not call an LLM or provision model credentials.

## Checkpoint analysis

For progress over time, save checkpoint evaluation JSON together with elapsed
seconds measured by your experiment harness:

```bash
evalarc trajectory checkpoints.json --budget-seconds 3600 --output runs/trajectory.json
```

The [checkpoint format and scoring rules](docs/methodology.md#checkpoint-analysis)
include regression handling and comparability checks. Missing agent tokens and
costs remain `null`. Caller-reported elapsed time is not a METR time horizon.

## Why this project?

The research direction comes from executable SWE environments, verifier quality,
and long-horizon evaluation. The [research report](docs/research.zh-CN.md)
connects the design to SWE-bench, SWE-Gym, SWE-smith, R2E-Gym, SWE-rebench,
METR, RE-Bench, SWE-EVO, and current Terminal-Bench/Harbor work.
The [paper catalog](research/papers.json) records primary sources and verified
publication status.

EvalArc's intended place is an **audit layer alongside existing environment
and training frameworks**. Harbor already supports multi-step tasks and separate
verifier environments; neither is claimed as an invention here.
Harbor and Prime Intellect adapters are roadmap items, not current integrations.

## Project name

The initial local prototype was called GradeRail. EvalArc is the selected
project name; the package, Python imports, command, and new report schemas use
`evalarc`. See [migration notes](docs/migration.md) for the identifier changes.
The [naming review](docs/naming.zh-CN.md) preserves the original search snapshot.

## Scope and evidence

The tasks, references, fault controls, and seeds are all public development material.
Different seeds do not establish uncontaminated evaluation. Detected
defects do not prove resistance to arbitrary reward hacking. There are no
frontier-model results, human time baselines, RL gains, or claimed SOTA results.
See the [coding audit](examples/audit/index.html),
[support audit](examples/support-audit/index.html), and
[validation record](docs/validation.md) for the checks actually run.

Task difficulty, diversity, independent faults, and transfer to real model
failures must be established before this becomes a research benchmark.

## Development

```bash
python -m pip install -e ".[dev]"
pytest -q
ruff check .
ruff format --check .
python -m build
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and
[LICENSE](LICENSE). The [task-author guide](docs/task-authoring.md) explains
the current built-in extension points. CI includes Python checks, the Node
policy, and Docker audits for both packs.

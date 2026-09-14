<p align="center"><img src="docs/assets/banner.svg" alt="GradeRail — Test the grader before you train the agent." width="960"></p>

<p align="center">
  <strong>Behavioral audits for executable coding-agent graders.</strong><br>
  Python 3.11+ · Linux host · No runtime dependencies · MIT · Research preview
</p>

<p align="center">
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="docs/research.zh-CN.md">Research & papers</a> ·
  <a href="docs/methodology.md">Methodology</a> ·
  <a href="docs/roadmap.md">Roadmap</a>
</p>

An agent can pass an evaluation while delivering a broken system. GradeRail asks
whether the **grader can distinguish correct work from plausible defects**.
It evaluates a known-good implementation and deliberately flawed submissions,
then produces an inspectable report of which checks caught which defects.

This first release contains one original stateful engineering task: **Durable KV**.
It is a working grader-audit starter kit, with a checkpoint analysis utility for
longer coding experiments. It is not a calibrated frontier benchmark or an RL trainer.

## Run an audit

From this checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
docker pull python:3.12-slim
graderail audit --seeds 17 41 97 --output runs/audit
```

The command evaluates the reference and eight negative controls, writes
`runs/audit/audit.json`, and creates a standalone `runs/audit/index.html` report.
Exit code `0` means the reference passed and every declared defect was detected
in its intended dimension. Exit code `1` means an audit or candidate failed;
`2` indicates a usage or configuration error.

For the bundled, trusted controls, a faster CPU-only demo is:

```bash
graderail audit --backend local --trust-local --output runs/local-audit
```

Local execution has the host user's privileges. Use Docker for candidate
isolation and read the [execution boundaries](SECURITY.md).
If your Docker setup requires a wrapper, set `GRADERAIL_DOCKER` to that command
or pass `--docker-command`.

## What is tested?

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
graderail init workspace/durable-kv
# Give this workspace and its TASK.md to your coding agent.
# After it edits main.py:
graderail evaluate workspace/durable-kv --seeds 17 41 97 --output runs/candidate
```

The CLI evaluates completed artifacts. It does not start an LLM, provision API
keys, or record its tool calls. Any coding workflow that produces the documented
`main.py` protocol can submit a directory. Use `graderail init --reference
workspace/reference` to create the positive control.

For progress over time, save checkpoint evaluation JSON together with elapsed
seconds measured by your experiment harness:

```bash
graderail trajectory checkpoints.json --budget-seconds 3600 --output runs/trajectory.json
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

GradeRail's intended place is an **audit layer alongside existing environment
and training frameworks**. Harbor already supports multi-step tasks and separate
verifier environments; neither is claimed as an invention here.
Harbor and Prime Intellect adapters are roadmap items, not current integrations.

## Scope and evidence

The task, reference, fault controls, and seeds are all public development material.
Different seeds do not establish uncontaminated evaluation. Eight detected
defects do not prove resistance to arbitrary reward hacking. There are no
frontier-model results, human time baselines, RL gains, or claimed SOTA results.
See the [sample audit](examples/audit/index.html) and its
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
[LICENSE](LICENSE). CI includes Python unit/integration checks and an actual
Docker grader audit.

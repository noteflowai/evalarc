<p align="center"><img src="docs/assets/banner.svg" alt="EvalArc — Higher score. New failure." width="960"></p>

<p align="center"><strong>Find the agent regression behind a better score.</strong><br>
Review changed checks, follow the recorded actions, and hand off evidence someone else can verify.</p>

<p align="center">
  <a href="https://noteflowai.github.io/evalarc/#regression"><strong>Try the recorded failure →</strong></a> ·
  <a href="docs/first-review.md">First local review</a> ·
  <a href="https://huggingface.co/spaces/glayguo/evalarc">Hugging Face</a> ·
  <a href="README.zh-CN.md">简体中文</a>
</p>

**90% → 93.75%. Two checks improve. One previously passing check fails.**
A tool commits a note but returns an error. Retrying with a new key writes the
note again. EvalArc exposes that regression instead of letting the higher
average score settle the review.

<a href="https://noteflowai.github.io/evalarc/#regression"><picture>
  <source media="(prefers-reduced-motion: reduce)" srcset="docs/assets/first-review.png">
  <img src="docs/assets/first-review.gif" alt="Recorded walkthrough: the score rises, a retry duplicates a note, and the strict acceptance gate rejects the policy." width="960">
</picture></a>

The demonstration replays saved Docker runs of scripted controls. No installation,
account or model key is needed to explore it. **Research preview** · MIT ·
Python 3.11+ · Linux for local workflows · no third-party Python runtime dependencies.

## Start with one review

1. **See the regression.** [Compare the two revisions](https://noteflowai.github.io/evalarc/#regression),
   then inspect `retry-after-commit` in the [case explorer](https://noteflowai.github.io/evalarc/#explorer).
2. **Check the decision.** [Compare the acceptance gates](https://noteflowai.github.io/evalarc/#suite):
   the same 93.75% score passes a permissive rule and fails the strict notes rule.
3. **Recompute it locally.** The [first-review walkthrough](docs/first-review.md)
   installs the published wheel, downloads the records and rebuilds the comparison.
   Verification exits 0 for consistency; comparison exits 1 for the regression.

Install the released reviewer in a fresh virtual environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install "https://github.com/noteflowai/evalarc/releases/download/v0.13.0/evalarc-0.13.0-py3-none-any.whl#sha256=1a3845cb92b594364f83a50307ad6c3b96c4504033a41d41900b9d1390ca803b"
evalarc --version
```

The offline review needs no Docker, Node, GPU or model API. Follow the
[download and comparison commands](docs/first-review.md#3-recompute-the-recorded-regression)
to produce your first HTML report without cloning the source.

## Bring your own work

| What you need to review | Use EvalArc to | Start here |
| --- | --- | --- |
| A changed agent implementation | Compare matching evaluations and inspect regressed checks | [Run and compare](docs/workflow.md) |
| A Strands Evals task with observed state | Recheck notes and closure using native SDK reports and case/rule identities | [Interactive review](https://noteflowai.github.io/evalarc/strands/index.html) · [Run the example](examples/strands-state-review/README.md) |
| Saved AgentCore Evaluate results and spans | Inspect valid zero scores, skipped judgments, missing results and skill delivery | [Export-to-review walkthrough](docs/agentcore-first-review.md) |
| Repeated judgments on one fixed recording | Separate score variation, verdict disagreement and incomplete assessments | [Judge Stability](docs/judge-stability.md) |
| A report received from another developer | Recompute summaries, configured gates and JUnit from original inputs | [Offline verification](docs/verification.md) |
| A correct file with questionable execution | Inspect temporary writes, file access and actual service submissions | [Runtime behavior review](https://noteflowai.github.io/evalarc/behavior-audit/index.html) · [Local review without cloning](docs/behavior-first-review.md) |
| A grader or candidate you want to execute | Run a reference and deliberate faults against a task contract | [Run an audit](#run-an-audit) |

Trace import accepts a [bounded export format](docs/trace-workbench.md), not arbitrary
cloud exports. Its scored controls are synthetic; the separate MCP example records
actual local delivery with no evaluator scores. No live AgentCore evaluation is claimed.

Trying your own records? [Tell us where the first review helped or got stuck](https://github.com/noteflowai/evalarc/issues/new?template=first-use.yml).
A minimal redacted example is enough; a failed setup is useful feedback too.

## What the recorded evidence covers

| Task | Interaction | Declared faults | Detected by only one case |
| --- | --- | ---: | ---: |
| `durable-kv` | Coding artifact: responses, transactions and restart durability | 8 | 3 |
| `support-routing` | Simulated ticket tools: routing, exact notes, closure and unrelated state | 7 | 2 |
| `robot-evidence-review` | Attributed recordings: coordinates, clocks and missing observations | 6 | 1 |

The saved audits detect **21/21 declared faults across three task packs**. Six
faults depend on one detecting case each. Removing a sole detector lowers a fresh
audit's mutation score; these margins expose that dependency before the change.
They do not establish coverage of unseen faults.
[Inspect coverage](https://noteflowai.github.io/evalarc/#coverage) ·
[Methodology](docs/methodology.md) · [251 audit case records](docs/casebook.md).

For deeper exploration: [repeated attempts](docs/reliability.md),
[TOML suites and CI](docs/suites.md), [Python/JavaScript candidates](docs/languages.md),
[recorded GPU research pilots](docs/research-pilots.md),
[architecture](docs/architecture.md) and [papers](docs/research.zh-CN.md).

**Review independent-source task outcomes.**
[The SWE workflow review](https://noteflowai.github.io/evalarc/independent-swe/index.html)
retains 36 GPU attempts on three public source tasks across four fixed conditions.
31 have assessable native reports; five remain uncertain because of upstream
infrastructure flags. None obtained acceptance. Inspect the actual MCP preloads,
eight nonempty patches, tool failures and six upstream controls.
[Methods and offline records](examples/independent-swe/README.md).

**Does “finished” mean the task passed?**
[Equal-length context controls](https://noteflowai.github.io/evalarc/context-controls/index.html)
retain twelve Qwen3-8B attempts in two separate cohorts. Relevant guidance and
unrelated prose each use a 476-token MCP payload. Inspect protocol timeouts,
unchanged starter programs, numerical errors and every independent case check.
Each cohort resolves 0 of 6 tasks; the diagnostic follow-up is a public development
experiment, not a held-out efficacy result. [Methods and offline verification](examples/context-controls/README.md).

**Continue from a reviewed session, then check the delivered work.**
[Funes MCP handoff](https://noteflowai.github.io/evalarc/funes-handoff/index.html)
records six Qwen3-4B continuations of one public Qwen3-8B program.
The memory condition retrieves through the actual MCP entrypoint; all six
programs remain unchanged and score 87.5%, with no task fully resolved.
Inspect the source passages, commands and independent coordinate checks.
[Use the source example](https://github.com/noteflowai/dsh-skills-anywhere/tree/main/examples/funes-handoff)
· [Methods and offline evidence](examples/funes-handoff/README.md).

**Carry the reviewed skill into the next session.**
[Pinned skill handoff](https://noteflowai.github.io/evalarc/skill-handoff/index.html)
follows an earlier MCP skill load into six new continuations. Both conditions
receive the exact historical skill through workflow-selected MCP; one also
offers Funes retrieval. Six preloads and six historical retrieval results
succeed, but every program remains unchanged and full acceptance is 0/6.
[Methods and complete evidence](examples/skill-handoff/README.md).
This uses a different prior session from the no-skill handoff above.

**Does a correct answer file prove the delivered program works?**
[Three native Harbor controls](https://noteflowai.github.io/evalarc/harbor-controls/index.html)
separate answer reward from independently executed code. One control receives
100% answer reward but its program scores 80% and fails strict acceptance.
These are declared scripted controls, with raw ATIF and an offline evidence
bundle; no model inference or unseen-exploit claim.
Feature history lives in the [changelog](CHANGELOG.md).

## Run an audit

To execute the built-in Python reference and eight deliberate coding faults,
install the wheel above, then use Docker:

```bash
docker pull python:3.12-slim
evalarc audit --seeds 17 41 97 --output runs/audit
```

Open `runs/audit/index.html`. Exit 0 means the reference passed and all declared
faults were detected in their intended dimensions; 1 means an audit/candidate
failed, and 2 means invalid input or an environment failure.

For the bundled trusted controls, this shorter CPU-only run uses the host:

```bash
evalarc audit --task support-routing --backend local --trust-local --output runs/support-audit
```

Local execution has your user privileges. Use Docker for candidate isolation;
see [execution boundaries](SECURITY.md) and [readiness checks](docs/workflow.md).
Use a fresh output path for another run. To develop EvalArc itself, see
[Development](#development).

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

## Project scope

**EvalArc audits graders and reviews evaluation evidence for coding and
tool-using agents.** Executable tasks, outcome checks outside the candidate,
revision comparisons and portable reports help developers assess whether
results meet acceptance requirements and grading rules detect declared defects.

The project serves as an audit layer within existing evaluation environments
and experiment workflows. It focuses on three questions: does the result meet
the task contract, did a change introduce a regression, and can the conclusion
be checked against the original records? See the
[architecture](docs/architecture.md) and [methodology](docs/methodology.md)
for task contracts, scoring rules and integration scope.

Native Harbor task export, oracle/NOP execution and ATIF 1.8 records are
available as [bounded research integrations](docs/research-pilots.md).
A general production adapter, Prime Intellect integration and calibrated
long-horizon task sets remain future work.

## Research basis

Software-engineering agent evaluation, executable training environments and
verifier reliability inform the design. The [research report](docs/research.zh-CN.md)
explains the technical motivation and engineering references; the
[paper catalog](research/papers.json) records paper sources, versions and
publication status as of the documented search.

## Scope and evidence

The public records validate graders and the review workflow. Tasks, reference
implementations, fault controls and random seeds are public. Detection results
apply to the declared defects, selected cases and recorded execution conditions.
Changing seeds alone does not create an independent held-out evaluation or
establish that the data was excluded from training.

The [coding audit](examples/audit/index.html),
[support audit](examples/support-audit/index.html) and
[validation record](docs/validation.md) provide inspectable implementation evidence.
Coverage of unknown defects, resistance to reward hacking, model capability
rankings and training transfer require separate evaluation with independent
data and an appropriate experimental design.

## Development

Clone the source for development and for the `examples/` commands in this README:

```bash
git clone https://github.com/noteflowai/evalarc.git
cd evalarc
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
pytest -q
ruff check .
ruff format --check .
python -m build
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md),
[migration notes](docs/migration.md), and [LICENSE](LICENSE).
The [task-author guide](docs/task-authoring.md) explains
the current built-in extension points. CI includes Python checks, the Node
policies, and Docker audits for all three task packs.

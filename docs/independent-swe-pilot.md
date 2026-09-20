# Independent-source SWE pilot

This optional recorder compares a frozen generic engineering workflow on public
SWE-bench Verified tasks. It records edits, tool responses, model usage and the
upstream evaluator's result. It is a small controlled experiment, not a model
leaderboard or evidence that the public tasks were absent from model training.

The initial cohort has three tasks, four conditions and three generation seeds:
36 scheduled attempts. The tasks were selected deterministically from Astropy,
pytest and SymPy after freezing the generic skill. The development case is
excluded. The dataset revision, exclusions and selection procedure are separate
inputs; changing a failed task is not a supported recovery mechanism.

| Condition | Workflow delivery |
| --- | --- |
| None | No additional skill |
| Direct | Read the frozen generic skill through the direct bridge |
| MCP | Read the same skill through an actual stdio MCP session |
| Unrelated | Read unrelated museum notes through MCP, with matched delivered tokens |

Direct and MCP conditions must deliver exactly the same model-visible object.
The unrelated control uses the same experimental skill name to hold the tool-call
shape constant. Its delivered object and complete initial prompt must match the
related condition's token count under the pinned tokenizer. Preloading is a
workflow action; these conditions do not measure autonomous skill discovery.

## Components

- `scripts/prepare_swe_conditions.py` verifies the pre-selection skill hash,
  records actual bridge receipts and creates the matched unrelated control.
- `scripts/swe_workspace.py` prepares source archives and runs disposable editing
  containers. It exports the live filesystem through a process inside the
  container, then produces a Git-format patch without checking out candidate
  paths on the host.
- `scripts/record_swe_control.py` executes the pinned upstream evaluator for an
  original defect, upstream fix or recorded candidate patch. Empty patches still
  execute the original-defect evaluation.
- `scripts/record_swe_pilot.py` follows a saved schedule, records every generation
  and tool interaction, exports the final patch and invokes the independent
  evaluator. It imports Docker only in the optional runtime.
- `scripts/local_model_server.py` checks the local weight manifest and exposes
  generation and tokenizer measurement on loopback. `/measure` does not generate
  a model completion.

The standard-library EvalArc package does not acquire these optional runtime
dependencies.

## Isolation and identity

The editing process runs as UID/GID 65534 with no Linux capabilities, no network,
no host binds and no Docker socket. Its image root is read-only. Source is copied
into a writable tmpfs; Git metadata, including submodule Git metadata, is omitted.
Initialized submodule content is retained. The container has a 2-CPU limit,
8 GiB memory limit and a 256-PID limit. The recorder checks actual container and
process settings, image identity and source hashes.

The trusted host controller needs Docker access. The native upstream grader runs
separately as root inside its evaluation container, with capabilities removed,
network disabled and no host binds. Do not describe this as an entirely non-root
pipeline. The model receives the repository name and original issue text; the
reference fix, extra test patch and grading data stay with the host controller
and independent grading stage.

An image's initial commit can differ from the dataset's base commit. Both must
be recorded; the dataset base must be an ancestor, and the source image must be
clean. Compare their source content before accepting a fixture. An image digest
is required; a mutable `latest` tag is insufficient.

## Fixed execution contract

The initial study uses Qwen3-8B, BF16, thinking disabled, with a pinned weight
revision and manifest. Each attempt allows 20 model turns, 2,048 new tokens per
turn and a 900-second interaction budget. Temperature is 0.2, top-p is 0.9 and
top-k is 20. Generation seeds are 17, 41 and 97; turn `n`, starting at zero, uses
the attempt seed plus `n`. All conditions share these settings and tools.

The service measures the actual chat-template tokens before generation. When
necessary, the controller removes the oldest complete interactions until the
request fits 28,000 tokens including its generation allowance and at most
90 messages. It preserves the initial task and workflow preload. Full original
interactions and the exact submitted requests remain in the record.

The interaction deadline stops further dispatch. Commands and review exports
receive bounded remaining time; process termination, final evidence capture and
independent grading have separate limits. The native grader receives a
600-second test limit. Record observed durations rather than inferring them from
these ceilings.

Keep a frozen copy of the recorder, EvalArc imports, provider bridge, provider
library, dependency identity, conditions, source manifests and model identity.
Use explicit `PYTHONPATH` entries pointing to that copy. Do not accidentally
import another editable checkout. The configuration lists each frozen file hash;
the controller verifies it before every scheduled attempt.

## Records and interruption

Each attempt saves the submitted prompts, complete model responses, usage,
context-trimming decisions, tool receipts, actual container settings, final patch
and original native report. Tool outputs have explicit archive and model-visible
limits; truncation is recorded. Missing model responses leave usage incomplete.
Protocol errors, no-change submissions and failed generations remain in the
denominator.

Run the controller in a durable service with a lifetime that covers the whole
cohort. `--resume` requires the exact original configuration. Completed slots are
preserved. A started but unfinished slot is marked interrupted, preserving the
previous record and any native report already written; it is never generated
again. Only unstarted slots execute. Do not launch a duplicate controller while
the original service is active.

For a recorded candidate:

```bash
python scripts/record_swe_control.py \
  --instance /private/instance.json \
  --swe-source /pinned/SWE-bench \
  --image 'repository/image@sha256:REVIEWED_DIGEST' \
  --image-head REVIEWED_FULL_COMMIT \
  --mode candidate --candidate-patch /records/candidate.patch \
  --output /records/native-grade --timeout 600
```

For a frozen cohort:

```bash
PYTHONPATH=/frozen/evalarc/src:/frozen/evalarc \
  /runtime/bin/python -B /frozen/evalarc/scripts/record_swe_pilot.py \
  --config /frozen/cohort.json
```

The configuration contains the schedule, immutable image mappings, prepared
source locations, private row location, bridge and condition paths, model
identity, budgets and file hashes. Preserve it with the resulting records.

## Interpreting results

Original-defect and upstream-fix executions validate the environment and parser;
they are not model runs. Report required failing-to-passing and passing-to-passing
tests separately. The upstream evaluator may label an empty prediction as having
a patch even when its `skip_patch` branch was used; retain those raw fields and
the explicit recorder flag rather than silently rewriting upstream output.

Compare any deliberately loose aggregate gate with upstream acceptance as a
declared rule audit. Missing or incomplete evidence is unknown. Rule disagreement
on a candidate is not independently established task truth, and a deliberately
loose gate is not an undisclosed SWE-bench vulnerability.

Report three source tasks and their repeated seeds explicitly; do not treat the
repetitions as nine independent tasks per condition. Preserve negative results.
Track source and project licenses separately; the evaluator's code license does
not establish a blanket license for dataset issue text.

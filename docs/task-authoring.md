# Adding a built-in task

The current extension point is the internal `TaskDefinition` registry in
`src/evalarc/tasks.py`. It is not a stable plugin or remote task-loading API.
Use the two existing packs as examples: `coding.py` runs completed artifacts;
`support.py` drives a tool policy and verifies host-owned state.

1. Write a versioned contract. Define the goal, protocol, allowed effects,
   reset behavior, action/time limits, and what each score means.
2. Implement a deterministic `generate_cases(seed)` returning dataclass cases.
   Their complete content is serialized into the cases fingerprint. Different
   seeds of one generator are not independent task families.
3. Implement `run_case(case, workspace, state, runtime)`. Candidate execution
   goes through `runtime.start`; host state and verifiers must stay outside the
   candidate workspace. Return case evidence with the fields below.
4. Register the task, dimension weights, default command, packaged assets, and
   every task-specific grading source file in `TaskDefinition`. Weights sum to
   one; every dimension must have at least one check in each generated suite.
5. Add an independently implemented reference and meaningful defects. Register
   declared fault controls in `CONTROL_PACKS` in `audit.py`, with the intended
   target dimension. The audit must reject a fault in that dimension.
6. Test positive outcomes, false-success claims, side effects, protocol failures,
   and unassessable environment failures. Run an actual Docker audit and archive
   its evidence. Change the task version when case generation, contract, budget,
   or scoring semantics change.

Common case fields:

| Field | Meaning |
| --- | --- |
| `case_id` | Stable family identifier; seed is added by the evaluator |
| `checks` | Map of applicable dimension names to `true`, `false`, or `null` |
| `passed` | Every required case check passed |
| `status` | `passed`, `failed`, `agent_error`, or `environment_error` |
| `error` | Diagnostic string or `null` |
| `duration_seconds` | Host-measured execution duration |
| `transcript_sha256` | Fingerprint of the recorded/observed sequence |

Set checks to `null` for an unassessable environment failure. The shared
aggregator sets `valid: false` and overall `score: null` if any case is invalid.
Expected recoverable tool errors belong in the task's trace and do not by
themselves invalidate an episode. Preserve task-specific evidence such as
initial/final state, calls, receipts, or artifact diagnostics.

The shared score calculation averages checks within each dimension and applies
that task's weights. This does not make scores across domains comparable. New
domains needing a different aggregation rule should introduce and document an
explicit versioned rule instead of forcing their outcomes into an existing one.

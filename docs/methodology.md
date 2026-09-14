# Methodology

## What the result means

EvalArc v0.2 tests two public, seeded task distributions: `durable-kv@0.1.0`
and `support-routing@0.1.0`. The coding pack compares observed responses with a
host-side in-memory oracle; its independent reference uses SQLite. The support
pack verifies final host-owned ticket state and protocol completion.

Let `p_d` be the proportion of complete cases that pass in dimension `d`, averaged
over the specified distinct seeds. The development score is
`sum(weight_d * p_d)`. Weights sum to 1 within each task, and scores are not
cross-domain rankings. Coding cases each contribute to one dimension and pass
only when every response, exit, and required restart satisfies the contract.
Partial response counts are diagnostics. Support episodes each contribute one
check to every dimension; a partially completed workflow can pass some checks.

Full resolution requires every applicable check in every case to pass.
Neither a high weighted score nor self-reported success constitutes resolution.
These weights are explicit design choices, not empirically validated measures
of economic value.

Each audit runs one known-good submission and declared defective variants:
eight for coding, seven for support.
A mutant is detected only if it fails a case in the intended target dimension.
Audit success requires both a passing positive control and detection of every
declared negative control. Its denominator is that pack's declared fault models,
not independent draws from all possible defects.

An environment failure sets a case's checks to `null`, the evaluation's
`valid` to `false`, and its aggregate score to `null`. An invalid control run
cannot count as a detected defect. If any run is invalid, the audit's aggregate
mutation score is also `null`. A valid control that did not encounter the failed
service may still have observed results, but the overall audit remains invalid.

Expected transient tool failures are part of the support task. They remain in
the trace alongside actual state changes and retry receipts. Recovering from
them can yield a passing episode. Agent protocol errors produce `agent_error`;
ordinary wrong outcomes produce `failed`.

## Relation to hack-verifiable environments

Planting known defects to get automated, deterministic verification is the same
move made by the **hack-verifiable environments** (HVE) methodology
([arXiv:2605.20744](https://arxiv.org/abs/2605.20744v1), and its terminal-task
adaptation HVTB, [arXiv:2608.22103](https://arxiv.org/abs/2608.22103v1)). Both
lines exist because the alternative — inspecting trajectories after the fact, by
hand or with an LLM judge — is unreliable.

They measure opposite directions, and EvalArc is not an HVE implementation:

| | HVE / HVTB | EvalArc audit |
| --- | --- | --- |
| What is planted | A detectable hacking opportunity, in the environment | A declared fault, in the submission |
| Subject measured | The agent | The grader and its checks |
| Question | Does the agent exploit it? | Does the evaluation catch it, and by how much? |
| Reported | Reward-hacking rate across models | Detection of every declared fault, with margins |

The two are complements rather than substitutes. HVE takes for granted that a
planted hack is detectable by construction, which is what makes an exploitation
rate meaningful. An audit here asks the prior question: does this suite detect a
deliberate defect at all? A grader that does not is exactly the condition under
which reward hacking goes unmeasured, because the intended objective is violated
and the signal never moves.

Neither an audit nor a mutation score bounds reward hacking. The denominator is
this pack's declared fault models, not the space of possible exploits, and no
model is being ranked.

## Detection margins

A mutation score of 1.0 says every declared fault was caught. It does not say
how narrowly. Each mutant therefore reports `detection_margin`, the number of
cases that independently failed on it, and the audit reports the weakest margin
across the pack, the faults caught by exactly one case, and the cases that are
the sole detector of some fault.

The measured margins for the two shipped packs, from real runs:

| Pack | Declared faults | Detected | Weakest margin | Caught by a single case |
| --- | ---: | ---: | ---: | --- |
| `durable-kv` | 8 | 8 | 1 | `accept-nonstring-keys`, `boolean-equals-one`, `partial-batch` |
| `support-routing` | 7 | 7 | 1 | `new-key-on-retry`, `skip-retry` |
| `robot-evidence-review` | 6 | 6 | 1 | `assume-complete` |

All three packs score 1.0. Six of the twenty-one declared faults rest on a
single case each, and their sole detectors are `cas-type-sensitivity`,
`reject-and-continue`, `rollback-batch`, `retry-after-commit`,
`retry-before-commit` and `incomplete-recording`. Weaken or drop any one of
those six cases and the corresponding fault becomes invisible while the mutation
score still reads 1.0. That is the number worth publishing next to a perfect
score, and it is a statement about this suite's own coverage, not about any
candidate.

A margin counts distinct cases, not case runs. The same case failing under two
seeds is one detector; counting runs would double every margin per added seed
and make a suite look more robust for changing nothing.

The margins above are identical under the Python and the JavaScript reference
implementations, for all three packs. That is what should happen if a margin
measures the check suite rather than a particular candidate, and it is reported
as an observation from these runs, not as a proof of language independence.

## State and process boundaries

Every coding case gets a fresh state directory. Sessions within that case reuse its
database path. EOF tests clean exit; SIGKILL tests loss of the process after a
write has been acknowledged. This version does not inject faults inside an
unacknowledged transaction, simulate power loss, test disk corruption, or test
concurrent writers.

Each support episode starts with a fresh host-owned ticket state. The candidate
sees only task instructions and tool observations, never a mounted copy of the
service state. The trace records attempted tools, results, injected/validation
error sources, and before/after changes. `finish.message` is recorded but does
not determine the score. The independent verifier checks final data without
calling the service's mutation handlers.

The Docker candidate sees only the copied candidate workspace, its writable
state, and protocol requests. It cannot write the host score file. Host grading
code, expected responses, and the reference implementation are not mounted.
All bundled code is nevertheless public and therefore unsuitable as a secret
holdout.

The default Docker image tag is resolved to a local content ID before evaluation.
Limits are one CPU, 256 MiB RAM, 64 processes, no network, and a bounded temporary
filesystem. Output is bounded per session and response deadlines include Docker
startup for the first exchange. Consequently, these timings are infrastructure
measurements, not candidate algorithm performance benchmarks.

## Checkpoint analysis

`evalarc trajectory` accepts a JSON array:

```json
[
  {
    "elapsed_seconds": 120,
    "evaluation": {
      "score": 0.4,
      "resolved": false,
      "task": {"id": "durable-kv", "version": "0.1.0", "split": "public-development"},
      "grader_sha256": "the value from evaluation.json",
      "cases_sha256": "the value from evaluation.json",
      "runtime": {"the complete runtime object": "from evaluation.json"}
    }
  }
]
```

Use actual complete `evaluation.json` objects in your data. The abbreviated
object above illustrates the schema and is not a measured experiment. The
experiment harness supplies elapsed time from its own monotonic start clock;
EvalArc does not independently authenticate these times.

For a budget `B`, the utility computes `(1/B) * integral_0^B score(t) dt`.
It uses a left-step curve: score is zero until the first observation, each
observation applies until the next, and the last score is held to `B`. It does
not interpolate progress or replace a regression with the best previous result.
Checkpoint times must strictly increase, and schema version, task, grader
fingerprint, cases fingerprint, and runtime must match across all checkpoints.
Invalid/unassessed evaluations are rejected. Changing command, timeout, image,
seeds, scoring rules, or task version makes observations incomparable.

This is an observed score-area statistic. It does not estimate a METR time
horizon: that requires human task-duration calibration and success probabilities
across a suitable task distribution. A last-known score held until the budget
does not prove the agent continued running or that its artifact stayed valid.

## Reproducibility

Reports include task and package versions; SHA-256 fingerprints of the exact
copied candidate, grading code, and generated cases; seeds; runtime limits;
platform; image ID; command template; per-case outcomes; and transcript hashes.
Coding stores a request/response hash without every value; support stores its
bounded complete tool trace and initial/final state.
Candidate directories are limited to 10 MiB and 1000 files, and symlinks are
rejected. Copied executable modes and the optional command manifest are included
in the fingerprint. Stop the producing process before evaluating a directory so that the
snapshot represents a coherent artifact.

Fingerprints are provenance aids, not cryptographic attestation. A trusted
operator can still fabricate JSON. For independent reproduction archive the
candidate snapshot, source commit, runtime image, and result file together.

## Training versus evaluation

The current material is public development data. Do not describe a new random
seed as an unseen task family or as evidence that a model was not exposed to the
generator. Keep private acceptance cases outside an agent's accessible workspace
and do not repeatedly train against them.

If used as an RL signal, the weighted score is only a development reward. It has
not been validated for learning stability, incentive compatibility, or transfer
to unseen tasks. The ticket simulator has a local step interface, but a trainer
adapter, production API integration, and real optimization results remain outside
v0.2.

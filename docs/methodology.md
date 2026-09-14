# Methodology

## What the result means

GradeRail v0.1 tests one task distribution, `durable-kv@0.1.0`, using public,
seeded scenarios. It checks whether observed responses match a host-side
in-memory oracle. The independent reference submission uses SQLite.

Let `p_d` be the proportion of complete cases that pass in dimension `d`, averaged
over the specified distinct seeds. The development score is
`sum(weight_d * p_d)`. Weights sum to 1. A case passes only when every response,
exit, and required restart satisfies the contract. Partial response counts are
diagnostics and do not yield partial case credit.

Full resolution requires all cases, including crash recovery, to pass.
Neither a high weighted score nor self-reported success constitutes resolution.
These weights are explicit design choices, not empirically validated measures
of economic value.

The audit runs one known-good submission and eight declared defective variants.
A mutant is detected only if it fails a case in the intended target dimension.
Audit success requires both a passing positive control and detection of every
declared negative control. Its denominator is eight fault models, not eight
independent draws from all possible defects.

## State and process boundaries

Every case gets a fresh state directory. Sessions within that case reuse its
database path. EOF tests clean exit; SIGKILL tests loss of the process after a
write has been acknowledged. This version does not inject faults inside an
unacknowledged transaction, simulate power loss, test disk corruption, or test
concurrent writers.

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

`graderail trajectory` accepts a JSON array:

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
GradeRail does not independently authenticate these times.

For a budget `B`, the utility computes `(1/B) * integral_0^B score(t) dt`.
It uses a left-step curve: score is zero until the first observation, each
observation applies until the next, and the last score is held to `B`. It does
not interpolate progress or replace a regression with the best previous result.
Checkpoint times must strictly increase, and task, grader fingerprint, cases
fingerprint, and runtime must match across all checkpoints. Changing timeout,
image, seeds, scoring rules, or task version makes the observations incomparable.

This is an observed score-area statistic. It does not estimate a METR time
horizon: that requires human task-duration calibration and success probabilities
across a suitable task distribution. A last-known score held until the budget
does not prove the agent continued running or that its artifact stayed valid.

## Reproducibility

Reports include task and package versions; SHA-256 fingerprints of the exact
copied candidate, grading code, and generated cases; seeds; runtime limits;
platform; image ID; per-case outcomes; and transcript hashes. A transcript hash
identifies the observed request/response sequence without storing every value.
Candidate directories are limited to 10 MiB and 1000 files, and symlinks are
rejected. Stop the coding process before evaluating a directory so that the
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
to unseen software projects. A native `step/reset` environment, trainer adapter,
and real optimization results are outside v0.1.

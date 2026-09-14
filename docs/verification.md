# Verify received evaluation evidence

EvalArc provides a read-only handoff check. Recompute recorded claims without
Node, Docker, the original candidate directory or candidate execution.
Version 0.8 also checks complete suite configuration, acceptance gates and JUnit.

```bash
evalarc verify received/evaluation.json --json
evalarc verify received/repetition --json
evalarc verify received/comparison --json
evalarc verify received/suite --json
```

Pass a summary file or its directory. A directory must contain exactly one
supported report type. An individual evaluation may have any filename.
Keep a repetition with `attempts/0001/evaluation.json`, `0002/evaluation.json`,
and so on. A comparison needs `baseline.json` and `current.json` alongside it.

A suite handoff contains `suite.json`, the original `suite.toml`, `plan.json`,
`junit.xml` and every `jobs/<id>/repetition.json` with its attempt evaluations.
Do not edit the TOML to relocate candidate paths: they describe the original
machine and the verifier never resolves or reads them. The TOML byte hash must
match both the saved plan and the suite summary.

| Evidence | Recomputed checks |
| --- | --- |
| Evaluation v2 | Case/check counts, dimensions, weighted score, validity and resolution |
| Repetition v1 | Exact attempt inventory, input identities, aggregate counts, scores and variance |
| Comparison v1 | Matching task/runtime/grader/cases, score delta, regressions and improvements |
| Suite v1 | Original configuration/hash, job order and inventory, plan/budgets, task/runtime/seeds, attempts, custom gates, totals and JUnit |

The result includes SHA-256 and byte length for every input checked, including
TOML and XML. Historical package versions remain readable; verification does
not rewrite reports. JUnit counts, testcase identities, failure versus error,
gate payloads and recorded observations must match the recomputed suite.
XML indentation and attribute order may differ.

## Consistency, acceptance and resolution

Default exit **0** means records are internally consistent, even if a gate
rejects the candidate or the run records an environment error. Contradictory,
malformed or incomplete evidence exits **2** with `verified: false` in JSON.

```bash
# Require the suite's configured gates:
evalarc verify received/suite --json --require-accepted
# Require full resolution for any supported report:
evalarc verify received/suite --json --require-resolved
```

`--require-accepted` applies only to suites. Exit **0** requires valid records
and every gate accepting; **1** means valid records with rejected gates;
**2** means invalid records or a verification error. `--require-resolved` uses
the same exit convention for full resolution. In a comparison it refers to the
current evaluation. Using both flags requires both conditions. A permissive
gate can accept a partially resolved result.

## Try the published handoff

Download **suite-evidence.zip** from the
[evidence lab](https://huggingface.co/spaces/glayguo/evalarc), unzip it, and run:

```bash
evalarc verify suite-evidence --json
# Expected: verified=true; accepted=false; accepted_jobs=2;
# fully_resolved_jobs=1; total_jobs=3; 12 input files; exit 0.
evalarc verify suite-evidence --json --require-accepted
# Expected exit 1: the strict notes gate rejects the recorded faulty policy.
```

The ZIP retains the original bytes of all 12 verified files from the three-job,
five-attempt Docker suite. Its stable ZIP metadata makes repeated builds
reproducible. HTML and logs remain available separately in the lab.

## Bounds and trust scope

Inputs must be regular files without symlinks in the evidence path. Limits are
64 MiB per JSON, 1 MiB for TOML, 4 MiB for JUnit, and 256 MiB per handoff. Suites
have at most 100 jobs, 1,000 planned attempts and 100,000 planned case executions;
each repetition has at most 100 attempts. Duplicate JSON keys, non-finite
numbers, XML DTDs and entities are rejected.

Candidate path strings and durations remain reported metadata. They are
bounded and checked for internal consistency where applicable, but cannot be
reconstructed from the handoff. Original HTML, logs, audit summaries,
trajectories and source programs are outside the verified inventory.

This checks record consistency, not independent business-state grading or
producer authentication. A coordinated fabrication can be internally
consistent. Re-run trusted grading when execution evidence is required.

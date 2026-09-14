# Verify received evaluation evidence

EvalArc 0.7 adds a read-only handoff check. A customer or CI job can recompute a
report's claims without installing Node, contacting Docker, locating the
original candidate or executing its command.

```bash
evalarc verify received/evaluation.json --json
evalarc verify received/repetition --json
evalarc verify received/comparison --json
```

An evaluation can have any filename. For a repetition, keep `repetition.json`
with `attempts/0001/evaluation.json`, `0002/evaluation.json`, and so on. For a
comparison, keep `comparison.json`, `baseline.json` and `current.json` together.
Pass either the summary file or its directory. A directory must contain exactly
one supported report type.

The result includes a SHA-256 and byte length for every JSON file actually
checked. These hashes identify the handoff bytes, including historical package
versions. It does not rewrite reports or execute commands embedded in metadata.

| Evidence | Recomputed checks |
| --- | --- |
| Evaluation v2 | Case/check counts, dimensions, weighted score, validity and resolution |
| Repetition v1 | Exact attempt inventory, input identities, all aggregate counts, scores and variance |
| Comparison v1 | Matching task/runtime/grader/cases, score delta, individual regressions and improvements |

Malformed or contradictory evidence exits **2**, with `verified: false` in JSON
mode. Default exit **0** means the records are internally consistent, even if
the recorded candidate failed or had an environment error.

To require full resolution as well:

```bash
evalarc verify received/repetition --json --require-resolved
```

This exits **0** for valid, fully resolved records, **1** for valid but unresolved
records, and **2** for invalid records or a verification error. For a comparison,
full resolution refers to its current evaluation; `has_regressions` is also
reported separately. This flag is not a replacement for a suite's custom gates.

Suite manifests, custom gate decisions, JUnit, audit summaries and trajectories
are not currently standalone supported inputs. For a suite, verify each
`jobs/<id>` repetition directory; this checks its attempts but does not verify
the suite-level gate decision. The published site additionally checks the
featured suite against its original configuration and JUnit.

Input files must be regular files without symlinks in the evidence path.
Reads are limited to 64 MiB per JSON and 256 MiB per handoff. Repetitions contain
at most 100 attempts. Duplicate JSON keys and non-finite values are rejected.
Original HTML, logs and source programs are outside the verified inventory.

This is record consistency, not an independent rerun of the business-state
grader or authentication of the report's producer. A coordinated fabrication
can be internally consistent. Re-run trusted grading on the candidate when
execution evidence is required.

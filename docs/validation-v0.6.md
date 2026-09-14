# Validation record · v0.6.0 · 2026-09-14

Checks ran locally on Linux with Python 3.12.3 and local Node.js 22.23.2.
The release adds candidate templates and independent controls around the
existing evaluators. No model API was invoked.

| Check | Observed result |
| --- | --- |
| Python tests in an isolated Git worktree | 205 passed, including 33 new template/protocol tests |
| Repository Ruff lint and formatting | Passed |
| JavaScript durable reference and declared defects, Docker | Reference resolved 15/15 cases; all 8 faults detected in their declared dimensions |
| JavaScript support reference and declared defects, Docker | Reference resolved 4/4 cases; all 7 faults detected in their declared dimensions |
| Local JavaScript controls, seed 17 | Both references resolved; all 15 declared faults detected |
| Generated JavaScript references, seeds 41 and 97 | Both tasks resolved every case |
| Local protocol edge cases | Large integers, integer/float distinctions, signed zero, exponent spellings, nested objects, property-order independence, special keys, malformed JSON, rejected batches |
| Persistence edge cases | Values and CAS survive SIGKILL; write failures produce no acknowledgement; duplicate-key corrupt snapshots are not silently reset |
| Initialization | Python default bytes retained; no runtime needed for scaffolding; existing destinations protected; partial writes cleaned up |
| Installed wheel outside the development checkout | Generated workspaces, doctor, explicit-image Docker suite, starter failures, repeat, and JavaScript audit worked |
| Installed-wheel mixed-language Docker suite | 3/3 gates accepted and jobs fully resolved; 34 case executions; JUnit has 3 tests, 0 failures, 0 errors |
| Installed-wheel JavaScript starters | Both correctly fail to resolve; coding score 0, support score 0.35 from preserved-state checks |
| Installed-wheel JavaScript support repetition | 2/2 resolved attempts, no observed variable checks |
| Historical Python comparison | Matching v0.4/v0.6 coding records have identical grading/case/runtime metadata, score delta 0, and no regression |
| Container cleanup | No EvalArc containers remained after validation |

The [JavaScript audit records](../examples/javascript-audits/README.md) contain
167 total case executions: 135 coding and 32 support cases across references and
faulty controls. The [mixed-language suite](../examples/multilanguage/run/index.html)
preserves another 34 cases from the installed wheel, bringing the Docker
validation total to 201. It retains the original TOML, JUnit, every attempt,
per-job reports, and progress events.

The Node image used by both audits and the JavaScript suite jobs is
`sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5`.
The Python suite job uses the existing image
`sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea`.
These IDs identify the local resolved images; future pulls of mutable tags may
resolve differently.

The documented suite is parsed by a regression test after generating its
workspaces. Its runtime settings use `[jobs.runtime]` tables, as required by
the existing strict configuration schema. All three commands are preflighted
before the first suite job starts.

Final packaging includes all four JavaScript sources, runtime notes, and the
new template module. Wheel sources/assets are checked against the installation
used above. The source distribution retains the new suite configuration and
audit/suite evidence, including JSONL and JUnit XML. Documentation links and
standalone report links are checked against the final tree.

Task contracts, grading source files, and evidence schemas did not change.
Node-specific protocol tests are additional development checks, not new
published grader cases. Existing promotion pages and historical records retain
their original provenance. Docker CI is configured for both tasks and both
languages; this record describes local execution, not a hosted CI run.

These controls establish observed conformance and detection of named defects.
They do not establish production database durability, resistance to arbitrary
reward hacking, model reliability, or TypeScript/Rust SDK support.

## Publication integration

The completed local change was merged with the separately verified HF
Casebook publication. The combined tree passed 210 Python tests, lint and
formatting. A fresh mixed-language Docker suite again resolved all three jobs;
the archived JavaScript audit evaluations were independently validated.

The casebook keeps its original 167 audit cases, six repeated attempts and
three suite jobs from earlier versions. It does not relabel those records as
v0.6 language comparisons. Site and dataset artifacts share the guarded
publication workflow; the Docker matrix now audits both languages and tasks.

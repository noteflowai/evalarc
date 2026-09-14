# Validation record · 2026-09-14

Validation was repeated after the EvalArc rename on a Linux host with Python
3.12.3, using a fresh virtual environment. The configured GitHub Actions jobs
have not been executed on a remote repository.

| Check | Observed result |
| --- | --- |
| `pytest -q` | 21 passed |
| `ruff check .` | Passed |
| `ruff format --check .` | Passed |
| Editable installation, CLI and module entrypoints | `evalarc --help` and `python -m evalarc --help` passed; package metadata and imports use `evalarc` |
| Positive/negative control audit in Docker, seed 17 | Reference passed all 15 cases; 8/8 intended faults detected |
| Built wheel installed in a separate virtual environment, CLI executed outside the checkout | Public default seeds 17, 41, 97; reference passed all 45 cases; 8/8 intended faults detected |
| Wheel and source distribution build | Completed successfully |
| Research JSON, SVG syntax and local documentation links | Parsed successfully; 38 local links resolved |

The automated tests cover positive/negative behavioral controls; malformed or
non-finite responses; timeout and output limits; stderr flooding; unsolicited
stdout; rejection of candidate-reported scores; snapshot fingerprints and
symlinks; explicit local trust; overwrite protection; duplicate seeds;
checkpoint regressions, invalid times and incomparable inputs; and HTML escaping.

The final Docker audit is archived in [examples/audit](../examples/audit/index.html)
with its [complete JSON](../examples/audit/audit.json).
The positive control is a SQLite implementation. Negative controls are source
variants of that implementation. The report contains no actual model experiment.

Container image ID:

```text
sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
```

Grading-code SHA-256 for the recorded Docker run:

```text
0df4121148191aa931187fbe7b17021a3a748929d301e8eccf5dd06f699951b6
```

The local wheel check used the same grading-code fingerprint and task
implementation with three seeds. The Docker audit used one seed to validate the
actual isolation/execution path. Runtime JSON's `python` and `platform` fields
describe the host grader; the image ID identifies the candidate runtime.

The Docker run used `EVALARC_DOCKER='sudo -n docker'`, exercising the renamed
environment variable through the installed CLI. The archived report was
regenerated from that run and uses the `evalarc` schema namespace. Its task
version, generated-case fingerprint, reference-candidate fingerprint and
dimension weights match the earlier seed-17 audit; the grading-code fingerprint
changed with the rename. All recorded control evaluations and the separately
installed wheel match the current grading source fingerprint.

Python 3.11 and 3.13 are included in the CI matrix but were not installed and
tested in this local session. No real agent API, RL trainer, Harbor adapter,
Windows host, GPU workload, human baseline, or hardened multi-tenant deployment
was tested. Docker disk quotas and power-loss/concurrent-writer behavior are
outside this implementation's tested contract.

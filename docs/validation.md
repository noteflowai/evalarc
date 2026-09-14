# Validation record · v0.2.0 · 2026-09-14

Validation ran locally on Linux with Python 3.12.3 and Node.js v22.23.2.
The wheel was installed into a separate fresh virtual environment and executed
outside the checkout. The public
[GitHub Actions run](https://github.com/noteflowai/evalarc/actions/runs/34797722807)
also passed Python 3.11–3.13 tests, both Docker audits, browser checks and
deployment to GitHub Pages and Hugging Face.

| Check | Observed result |
| --- | --- |
| `pytest -q` | 43 passed, including the independent Node policy and site artifact checks |
| `ruff check .` | Passed |
| `ruff format --check .` | Passed |
| Editable installation and task registry | Package/module version 0.2.0; CLI lists both built-in packs |
| Coding audit in Docker, seed 17 | Reference passed all 15 cases; 8/8 intended faults detected |
| Support audit in Docker, seed 17 | Reference passed all 4 episodes; 7/7 intended faults detected |
| Installed wheel, coding audit outside checkout | Default seeds 17, 41, 97; reference passed 45 cases; 8/8 intended faults detected |
| Installed wheel, support audit outside checkout | Default seeds 17, 41, 97; reference passed 12 episodes; 7/7 intended faults detected |
| Installed wheel, independent JavaScript policy | Default seeds 17, 41, 97; all 12 support episodes passed |
| Wheel and source distribution build | Completed successfully |
| JSON, SVG syntax and local documentation links | Parsed and checked for missing targets |
| Evidence explorer in Chromium | All 17 implementations and 167 cases checked at 1440 px and 390 px |
| Public GitHub Pages and actual Hugging Face iframe | Same browser checks passed, with no page errors or horizontal overflow |
| Hugging Face publication | All 12 bundle files read back anonymously and matched to the tested artifact |

The automated tests cover positive/negative behavioral controls; malformed or
non-finite responses; timeout and output limits; stderr flooding; unsolicited
stdout; rejection of candidate-reported scores; snapshot fingerprints and
symlinks; explicit local trust; overwrite protection; duplicate seeds;
checkpoint regressions, invalid times and incomparable inputs; and HTML escaping.
New coverage includes manifest snapshots, argument boundaries, executable modes,
runtime failures, detached observations, idempotency conflicts, action budgets,
unrelated state changes, invalid audits, and command-sensitive checkpoints.

The Docker reports are archived in [coding](../examples/audit/index.html) and
[support](../examples/support-audit/index.html), with complete JSON beside each.
Coding uses a SQLite positive control; support uses a scripted tool policy.
Negative controls are declared source variants. No actual model experiment or
provider API call was performed.

Container image ID:

```text
sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
```

Grading-code SHA-256 for the recorded coding run:

```text
52caa3136434569f96097860bc9bf85eb7ada5f7f9890c0540db81afb441871d
```

Grading-code SHA-256 for the recorded support run:

```text
2dced2a842369299e6e924db626fedc120071d5731cd9b79202dba7395b90255
```

Every recorded control and the installed-wheel run match the current source
fingerprint for their pack. The JavaScript policy shares the support grader
fingerprint. The coding case fingerprint and all eight control scores match
the earlier v0.1 seed-17 run; command/provenance changes do not change its task
contract. Snapshot hashes change because v0.2 includes executable permission.

Docker audits used one seed each and `EVALARC_DOCKER='sudo -n docker'`.
Wheel audits used three seeds and explicitly trusted local execution. Runtime
JSON's `python` and `platform` describe the host grader; image IDs identify the
candidate container. Node was checked in local mode, not in Docker.

Python 3.11 and 3.13 passed on GitHub-hosted runners; the local session used
Python 3.12. The Node policy test copies the example and uses the absolute
runtime path installed by CI, because local candidate processes deliberately
receive the system search path rather than the grader's full environment.
The earlier assumption that CI's Node would be on that system path was corrected.

The independently installed release wheel also passed the support audit and
JavaScript policy on seeds 17, 41 and 97 outside the checkout. Site publication
does not alter either task's grading code or the recorded audit JSON.

No real agent API, RL trainer, Harbor adapter,
Windows host, GPU workload, human baseline, or hardened multi-tenant deployment
was tested. Docker disk quotas and power-loss/concurrent-writer behavior are
outside this implementation's tested contract. No TypeScript SDK or Rust worker
was implemented or tested. The new service is a simulation, not a real helpdesk
integration.

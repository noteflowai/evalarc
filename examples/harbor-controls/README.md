# Harbor answer reward versus delivered-program acceptance

Recorded 2026-09-19 with Harbor 0.23.0 and task version 0.2.0.
Three scripted controls execute in a non-root, no-network Docker environment;
a separate verifier checks eight answer rows. No model generated these programs.

| Control | Answer reward | Program score | Strict acceptance |
| --- | ---: | ---: | --- |
| reference | 1.0 | 1.0 | accepted |
| clock-fault | 0.8 | 0.8 | rejected |
| detached-answers | 1.0 | 0.8 | rejected |

The partial-credit weights are provenance 0.10, coordinates 0.25, clock 0.15,
metrics 0.25, completeness 0.15 and protocol 0.10. All checks must pass for task
completion; independent acceptance requires a valid score of 1.0. The previous
0.1.0 export keeps its binary reward. These modes must not be pooled.

The clock control treats raw sensor ticks as seconds. It passes world-clock
cases and fails clock and derived metrics in four offset-clock cases. In the
detached control, the correct program writes the answer file before it is
replaced by the clock-fault program. The final hashes in the native ATIF match
the collected files. This deliberately tests an answer-only contract; it is not
a Harbor container escape or evidence about unknown reward hacking.

## Reproduce from the EvalArc source checkout

Use an isolated Python environment with Harbor 0.23.0 and Docker access:

```sh
python -m pip install 'harbor==0.23.0' -e .
PYTHONPATH=src:. python scripts/record_harbor_controls.py --output /tmp/new-harbor-controls
PYTHONPATH=src:. python scripts/build_harbor_controls.py \
  --source /tmp/new-harbor-controls --output /tmp/new-harbor-report
PYTHONPATH=src:. python scripts/build_harbor_controls.py \
  --output /tmp/new-harbor-report --verify
```

Output directories must be new. Where Docker requires a local wrapper, pass
`--docker-command /path/to/wrapper` and make the same wrapper available as
`docker` on PATH for Harbor. Do not loosen socket permissions. No GPU, model
account or external API credential is needed.

`harness/` retains the exact pre-run recorder, exporter and control-agent source.
`task/` retains the full exported task and verifier. Native job/configuration,
trajectory, answer and candidate files are retained in `jobs/`; `imports/`
contains independent Docker execution and untouched source result/ATIF copies.
Original absolute runtime paths in these records identify the recording machine;
use the relative links from `summary.json` to inspect this bundle elsewhere.

The full native ATIF schema was validated with Harbor's installed Trajectory
model. The offline bundle verifier checks original file identities, tool linkage,
observed file hashes, answer grading and independent report consistency.
It does not execute downloaded candidate code. The upstream reward and EvalArc
program score use the same declared dimensions but inspect different artifacts.
No claim of independent grader authorship or held-out evaluation is made.

The preliminary launch failed before any Harbor trial because the recorder used
an unsupported CLI flag. Its process log and command are in `attempts/`.
The corrected run used `--env docker`; there were no automatic trial retries.

Authorship: AI-assisted engineering and deliberately constructed controls.
Code MIT; source recording data retains the supplied Apache-2.0 notice.

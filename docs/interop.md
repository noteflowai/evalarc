# Harbor, ATIF and public-session handoff

`robot-evidence-review` checks a numerical report against attributed Robot Reel
source records. It includes unit/axis/origin transforms, source clocks, missing
observations and six independent fault controls. Derived representations are
not additional physics recordings.

```sh
evalarc init candidate --task robot-evidence-review --reference
evalarc audit --task robot-evidence-review --seeds 17 41
# JavaScript controls use the Node image.
evalarc audit --task robot-evidence-review --language javascript --image node:22-slim
python scripts/export_harbor_task.py harbor-task
```

The exporter targets Harbor 0.23.0 task schema1.4. Its agent container has no
network, runs as UID65534, and writes a fixed answer artifact. A separate verifier
container reads those answers without executing candidate code. The actual oracle
reward1 and NOP reward0, plus failed startup attempts, are retained in
`examples/research/harbor-native`.

```sh
evalarc import-harbor harbor-job/trial --candidate candidate --seeds 41 97 --output runs/import
# Export an actual recorded model trial, then inspect its bounded envelope/linkage.
evalarc atif trial.json --export-trial --output runs/trajectory.atif.json
evalarc atif runs/trajectory.atif.json
```

The caller chooses the candidate. Import cannot prove those files are the program
used by the upstream agent. Original result bytes and upstream reward remain
separate from EvalArc's independently graded score, validity and acceptance.
Default acceptance requires a valid evaluation and score1.0. ATIF exports use1.8;
all33 skill/handoff records were also checked with the installed upstream Harbor
`Trajectory.model_validate_json`. EvalArc's envelope/linkage inspector is narrower
than that upstream schema and must not be described as full schema validation.

## Docker timing and images

A trusted `/bin/sh` prelude announces readiness before executing the candidate.
`--startup-timeout` defaults to30 seconds; response timing starts after readiness.
The existing total-case limit still bounds both phases. Images must provide a
POSIX shell, as the documented Python and Node images do. A missing shell or
readiness failure is an environment error, not evidence of a wrong candidate.
The nine first-profile candidates were regraded after the timing fix, with every
score unchanged. Raw regrades and original reports are retained with the experiment.

## Funes: one explicit public session

```sh
# In a separate environment with pyarrow25.0.1:
python scripts/export_funes_trace.py --trial trial.json --output public-session.parquet
```

The exporter accepts a named public-development trial, not a home directory.
Funes1.3.0 indexed that Parquet into31 chunks and retrieved four hits. It treats
serialized message strings as text; dedicated tool-result blocks are not rebuilt.
`scripts/record_handoff.py` supplies the fixed recall and prior candidate to a fresh
Qwen3-4B session, with matched no-memory trials. All six score87.5%; no accuracy
gain is observed. This exercises two local open-model sessions, not native
Claude/Codex sessions, and never reads personal agent history.

See [methods](research-pilots.md), the [27-trial explorer](https://noteflowai.github.io/evalarc/skill-impact/)
and [versioned downloadable evidence](https://huggingface.co/datasets/glayguo/noteflow-research-pilots/tree/v2026-09-14).

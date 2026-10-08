# Reviewer exercise: find why a better score fails the gate

A timed exercise for roadmap milestone EA-03 ("reviewers understand why a gate
fired", target under ten minutes). It uses a recorded regression from the
released 0.17.7 source archive, so the reviewer needs no source checkout,
Docker, model key or account. Give the reviewer this page only; the facilitator
keeps the [answer key](reviewer-exercise-key.md).

## Before the clock starts

The facilitator prepares a new folder and runs, on Linux with Python 3.11+:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install evalarc==0.17.7
curl --fail --location \
  https://github.com/noteflowai/evalarc/releases/download/v0.17.7/evalarc-0.17.7.tar.gz \
  --output evalarc-0.17.7.tar.gz
echo "3aef77bcd457365b4219c1fb98ab74a4d2eb5c763edb14f3cf44a3b669f44b81  evalarc-0.17.7.tar.gz" | sha256sum --check \
  && tar -xzf evalarc-0.17.7.tar.gz evalarc-0.17.7/examples/results-diff/inspect/baseline.json \
    evalarc-0.17.7/examples/results-diff/inspect/current.json \
  && mv evalarc-0.17.7/examples/results-diff/inspect/*.json . \
  && rm -r evalarc-0.17.7 evalarc-0.17.7.tar.gz \
  && sha256sum baseline.json current.json
```

Each step runs only if the previous one succeeded. If `sha256sum --check`
prints `FAILED`, nothing is extracted; download again before starting.
Expected digests: `baseline.json`
`da31a4be7a6224f653843f28922a1fb2d950a5aba26dd1a51238d780c5c5d255`, `current.json`
`26f02205242868f6cb29f46c10adf994b3af160551aef64ee5129af556ece172`. Do not
extract the rest of the archive or leave it in the folder: its example README
and task source describe the answer. Setup time is not part of the measurement.

## The task

> Two Inspect AI logs from the same evaluation, before and after a change, are in
> this folder. The headline accuracy went up. Decide whether the change should
> pass CI, and if not, name the case and check that block it and the recorded
> output that shows why. You may use `evalarc --help` and any EvalArc command.

## Rules

- **Start** when the reviewer has read the task and the folder holds only
  `baseline.json`, `current.json` and the virtual environment.
- **Stop** when the reviewer states a decision with the blocking case, check and
  recorded output, or at **20 minutes**, whichever comes first.
- The facilitator does not hint. Record wrong turns and questions verbatim.
- Record: elapsed minutes, the decision, each item of the answer key found, and
  commands run. A reviewer who has seen this page's key, the example README or
  `refund_task.py` is not independent; note it and do not count the run.
- Count a run toward EA-03 only if the reviewer did not build, maintain or
  previously review EvalArc. Maintainer dry runs are preparation only.

## Recording a result

Report through the
[first-use form](https://github.com/noteflowai/evalarc/issues/new?template=first-use.yml)
with the elapsed time, what was found and where the reviewer hesitated. No
result has been recorded yet.

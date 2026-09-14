# Contributing

Install with `python -m pip install -e ".[dev]"`, then run `pytest -q`,
`ruff check .`, and `ruff format --check .`. Install Node.js to exercise the
independent JavaScript support policy; that test is skipped if Node is absent.
CI explicitly provisions Node. See [task authoring](docs/task-authoring.md) for
the current built-in registry and evidence contract.

A useful contribution makes an evaluation claim more testable. For a new task
or grader change, include:

1. The observable contract and task version.
2. A known-good implementation independent of the oracle's implementation.
3. Plausible defective implementations and the specific cases that detect them.
4. Reproduction commands, seeds, runtime limits, and data provenance.
5. An explicit description of behaviors not tested.

Changing the semantics of requests, scoring weights, or case generation requires
a task version change. Do not import evaluation-only benchmark data into training
tasks. Cite upstream sources and respect their licenses. Public randomized seeds
are not sufficient evidence of decontamination.

The current tasks are purpose-built and small. Contributions toward harder tasks
should include human calibration and evidence that frontier agents do not
trivially saturate them. New cloud integrations should be validated separately;
do not label an adapter as supported solely because it emits a similar JSON shape.

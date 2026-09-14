# Evaluation suite configurations

From the repository root, initialize the trusted controls in new directories:

```bash
evalarc init workspace/suite-coding --reference
evalarc init workspace/suite-support --task support-routing --reference
evalarc suite examples/suites/acceptance.toml --dry-run
evalarc suite examples/suites/acceptance.toml --output runs/acceptance
```

The defaults use Docker with `python:3.12-slim`, which must already be available.
The acceptance suite executes 23 cases: one 15-case coding attempt and two
4-case support attempts. It should accept both scripted references.

The second configuration demonstrates that task outcomes and gate decisions
are separate. Create the declared faulty support control:

```bash
evalarc init workspace/suite-support-fault --task support-routing --reference
python - <<'PY'
from pathlib import Path
from evalarc.audit import CONTROL_PACKS, mutate
path = Path("workspace/suite-support-fault/main.py")
old, new, _ = CONTROL_PACKS["support-routing"]["new-key-on-retry"]
path.write_text(mutate(path.read_text(), old, new))
PY
evalarc suite examples/suites/partial-progress.toml --output runs/partial-progress
```

This suite intentionally exits with code 1. The defective policy scores 0.9375
and does not fully resolve its task. The permissive gate accepts it, while the
gate protecting every notes check rejects the same candidate. The coding
reference resolves its task and passes the default gate.

Candidate paths are relative to the TOML file. To use trusted local execution,
declare `[jobs.runtime]` with `backend = "local"` within each job, and pass
`--trust-local` at execution. The flag does not override a configured backend.

See the [suite guide](../../docs/suites.md) and
[recorded Docker example](../suite/index.html).

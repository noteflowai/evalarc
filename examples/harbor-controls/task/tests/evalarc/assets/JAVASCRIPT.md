# JavaScript candidate runtime

Use Node.js 22 or newer on Linux. The candidate has no npm dependencies.
`evalarc.toml` declares the exact command; EvalArc does not build or install
dependencies, choose an image from the language, or run an implicit shell.

For Docker, pull `node:22-slim` before evaluation and pass
`--image node:22-slim` to `doctor`, `evaluate`, `repeat`, or `audit`.
In a suite, set `image = "node:22-slim"` under each JavaScript job's
`[jobs.runtime]` table.
The resolved immutable image ID is saved in the evaluation evidence.

For trusted local execution, use `--backend local --trust-local`. Candidates
receive a minimal PATH. If Node is installed through nvm or another version
manager, replace `"node"` in `evalarc.toml` with its absolute executable path.
Keep `"node"` for Docker; host paths need not exist inside the image.
Local JavaScript audits resolve the installed Node executable from the host
PATH and record that absolute path in their candidate command.

Read TASK.md for the protocol. Use stdout only for JSONL responses; send
diagnostics to stderr. The evaluator starts a new process for each case.
The durable service receives a writable state-file path as its first argument;
acknowledged changes must survive a process restart, including SIGKILL.

The durable reference preserves JSON numeric source text using
`JSON.parse` reviver context and `JSON.rawJSON`. A normal JavaScript
parse/stringify round trip can lose large integers and merge `1` with `1.0`,
which changes the task's type-sensitive CAS behavior. Values and object keys
also require recursive comparison independent of object property order.

References are transparent scripted controls, not AI agents or model results.
The durable reference writes a complete snapshot before acknowledging each
mutation. It targets small, single-process task workloads, not production
database performance, concurrent writers, or a power-loss guarantee.
The support reference acts only in the simulated ticket environment.

# Candidate commands

The evaluator selects a task with `--task`; the default remains `durable-kv`.
Candidate configuration cannot choose a task, grader, backend, limits, or image.

To replace a task's default Python entrypoint, put `evalarc.toml` in the
candidate workspace:

```toml
command = ["node", "main.js"]
```

For a differently named Durable KV Python service:

```toml
command = ["{python}", "-I", "-B", "service.py", "{state}/store.db"]
```

The file contains exactly one key, `command`, with 1–64 nonempty string
arguments, totaling at most 8192 characters. EvalArc copies the manifest with
the candidate and reads that copy. The command is passed as an argument array;
EvalArc does not insert a shell, expand environment variables, or execute
command substitutions.

| Placeholder | Docker | Trusted local mode |
| --- | --- | --- |
| `{python}` | `python3` | The grader's Python executable |
| `{workspace}` | `/candidate` | Copied workspace path |
| `{state}` | `/state` | Fresh per-case state directory |

The working directory is the copied workspace. Use relative filenames in the
command. `./agent` can launch a prebuilt executable; executable permission is
preserved and included in the candidate fingerprint. The existing 10 MiB /
1000-file limit still applies. Symlinks are rejected.

Without a manifest, a workspace must contain `main.py`. Durable KV passes it
the database path; support routing uses a Python process with no extra arguments.
The manifest never changes the selected task's JSONL protocol.

## Runtime responsibilities

Choose an image that contains the required runtime using `--image`; the default
image only supplies Python. Dependencies must be prepared before evaluation.
Candidates have no network in Docker. Local subprocesses receive a minimal
environment with the system executable search path; use an absolute executable
path for a runtime outside that path.

The repository validates Python in both backends and the independent JavaScript
support policy with local Node.js. Compiled TypeScript can use the JavaScript
entrypoint, but no TypeScript SDK or compiler integration is provided. Rust
workers, Rust submissions, and Node-in-Docker execution have not been validated
in this release.

Command templates are included in report runtime metadata. A command change
makes checkpoint runs incomparable even if the task and source files match.
For reproduction, archive runtime binaries/dependencies as well as the command;
a command string alone does not identify an interpreter version.

`evaluate`, `audit`, and `repeat` accept `--timeout` for each response and
`--case-timeout` for the complete case (defaults: 10 and 60 seconds). The latter
is shared across Durable KV restarts. A protocol-budget violation is an assessed
agent error; a runtime startup or cleanup failure makes the case unassessed.
See [repeatability and diagnostics](reliability.md) for evidence and exit codes.

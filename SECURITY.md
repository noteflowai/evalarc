# Execution and trust boundaries

The Docker backend runs only the candidate workspace in an unprivileged container
with network disabled, a read-only root filesystem, a read-only candidate mount,
CPU/memory/PID limits, and no Docker socket or grader mount. The host grader owns
the expected responses and final scores. It limits stdout/stderr and enforces a
deadline on each protocol exchange and a total deadline shared across process
restarts within a case. Each case receives a fresh writable state
directory; only restarts within that case share state.

Protocol deadlines use the host monotonic clock. Process startup and elapsed
time between restarts consume the case budget. Final cleanup has separate grace
periods (up to 20 seconds for Docker removal and 5 seconds for the local process).
A Docker cleanup exception still triggers local process and pipe cleanup, and
makes the case unassessed. A deadline is not a hard wall-clock worker termination
guarantee; abrupt host loss or repeated interruption may leave resources behind.

Reports include the last 2048 captured stderr bytes for each process. Treat
these as untrusted diagnostic text. HTML escapes them; progress events contain
host metadata, not candidate output. Review evidence for confidential content
before sharing it. `repeat` snapshots its input once and uses fresh evaluation
workspaces and state; local mode still requires trusted code.

The support-routing service and its authoritative ticket state live in the host
process. Only observations and tool results cross the JSONL boundary. Tool
arguments never invoke a host shell, filesystem operation, or real helpdesk API.
Each episode has an explicit action budget. Final messages are untrusted claims.

Candidate commands come from the snapshotted `evalarc.toml` argument array.
They execute inside the same backend boundary as the original Python entrypoint.
The manifest cannot select the task, verifier, image, or backend. Executable
permission is preserved for candidate binaries and included in their fingerprint.

Docker shares the host kernel. These controls are not a hardened multi-tenant
isolation guarantee. Run hostile submissions on disposable isolated workers
with an appropriate VM boundary. The writable state mount currently has no
portable disk quota: choose a quota-limited worker filesystem for untrusted runs.
Docker image resolution records a local immutable image ID; also archive the
image or pin its registry digest for reproduction on another host.

Local mode requires `--trust-local`. It executes with the host user's filesystem
and network privileges. Clearing the child environment does not provide a
sandbox. Use local mode only for code you trust, such as the bundled audit
controls. The evaluator and the checkpoint recorder themselves are trusted.
SHA-256 digests identify inputs; they do not authenticate whoever produced a
report.

Public generators, reference implementations, and seeds are development
material. Keeping the oracle outside the runtime prevents direct runtime access,
but does not make published cases secret or immune to memorization.

Report a vulnerability privately through your deployment operator or the
repository's private security reporting feature when available. Do not include
credentials or confidential evaluation data in public reports.

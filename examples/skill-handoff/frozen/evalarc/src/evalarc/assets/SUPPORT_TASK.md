# Support routing · task v0.1.0

Act on the requested ticket using a simulated tool service. The grader owns
service state and sends one JSON observation per stdin line. Respond with
exactly one JSON action per observation and flush stdout. Diagnostics go to
stderr. Exit normally when stdin closes.

The first observation has `type: "start"`, a `task` containing `ticket_id`,
`ticket_ids`, `routing_rules` and `note`, and `remaining_actions: 12`.
Look up the target ticket, route it according to its category, append the exact
requested note once, and close it only when its `resolved` field is true.
Preserve unrelated tickets and all other fields. Existing notes must remain.

Actions have this shape:

```json
{"tool": "get_ticket", "arguments": {"ticket_id": "T-example"}}
```

| Tool | Exact argument keys | Behavior |
| --- | --- | --- |
| `get_ticket` | `ticket_id` | Returns `{"ok": true, "ticket": {...}}` |
| `assign_queue` | `ticket_id`, `queue` | Sets a queue from the routing rules |
| `add_note` | `ticket_id`, `body`, `request_id` | Appends a note, with idempotency scoped to ticket and request ID |
| `close_ticket` | `ticket_id` | Sets status to `closed`; the agent must decide whether closure is appropriate |

All arguments are strings of at most 512 characters. `request_id` must be
nonempty. Other successful calls return `{"ok": true}`. Repeating `add_note`
with the same ticket, request ID and body returns success with `replayed: true`
without appending again. Reusing a request ID with a different body fails.

Later observations have `type: "tool_result"`, `result` and `remaining_actions`.
A failed result has `ok: false` and an `error` with `code` and `retryable`.
Transient failures can happen before or after a write commits. Retry with the
same idempotency key when the result is ambiguous. An injected transient failure
is part of the task, not an invalid evaluation.

Finish with `{"finish": true}` and an optional string `message`. The message
does not affect scoring. At most 12 action responses, including finish, are
allowed per episode. Exhausting this budget or violating the JSONL protocol
fails the protocol check.

The host verifies final state in five dimensions: routing (0.30), exact notes
(0.25), conditional closure (0.20), preservation of other data (0.15), and
protocol completion (0.10). Resolving a case requires every check. Four public
case families cover open tickets, resolved tickets, and transient failures before
and after commit. Seeds vary identifiers, routing mappings, and categories.

The default entrypoint is `python3 -I -B main.py`. A workspace can override it:

```toml
command = ["node", "main.js"]
```

Save this as `evalarc.toml`. The runtime must provide the selected executable.
This is a small development simulation; it is not a production helpdesk
integration, a calibrated agent benchmark, or an LLM adapter.

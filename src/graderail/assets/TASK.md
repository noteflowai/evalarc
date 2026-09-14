# Durable KV · task v0.1.0

Build a single-process persistent key-value service in `main.py`, using Python's
standard library. It is started with `python3 -I -B main.py /state/store.db`.
Read one JSON request per stdin line; flush exactly one JSON response per request
to stdout. Diagnostic output belongs on stderr. Input lines contain valid JSON.
Keys are arbitrary strings, including empty and Unicode strings. Values are
finite JSON values. Extra request fields may be ignored.

| Request | Response |
| --- | --- |
| `{"op":"put","key":"a","value":7}` | `{"ok":true}` |
| `{"op":"get","key":"a"}` (present) | `{"ok":true,"found":true,"value":7}` |
| `{"op":"get","key":"missing"}` | `{"ok":true,"found":false}` |
| `{"op":"delete","key":"a"}` | `{"ok":true}`, including absent keys |
| `{"op":"cas","key":"a","expected":7,"value":8}` | `{"ok":true,"swapped":true}` on match |
| Same CAS with absent key or mismatched value | `{"ok":true,"swapped":false}` |
| `{"op":"batch","operations":[...]}` | `{"ok":true}` if every operation is valid |
| Invalid request | `{"ok":false,"error":"invalid_request"}` |

CAS requires both `expected` and `value`. It only modifies existing keys.
Equality uses JSON serialization with sorted object keys: booleans differ from
numbers; integers and decimal representations may differ; object key order does
not matter. Batch accepts only `put` and `delete`. It must validate the entire
batch before changing state or roll back every change if any operation is
invalid. Empty batches succeed. Nested batches are invalid.

Invalid requests include non-object values, unknown operations, non-string
keys, missing required fields, and malformed batch contents. They must leave
state unchanged and must not terminate the service.

All acknowledged writes, deletes, successful CAS operations, and batches must
survive normal exit and **SIGKILL after acknowledgement**. The same database
path is passed on restart. SQLite is allowed. Multiple concurrent processes,
power-loss simulation, disk corruption, and interrupted unacknowledged
transactions are outside this version's contract.

Work in three suggested stages: basic service; validation and transactions;
durability and recovery. Previous behavior must continue to work after each stage.
The grader evaluates the complete contract at every checkpoint.

Only the candidate workspace is mounted into its container. Grading requests
arrive over stdin. The candidate cannot submit its own score. All tasks,
generators, and default seeds in this repository are public development material.

This is an integration task for auditing graders. Its human completion time and
difficulty for frontier agents have not been calibrated.

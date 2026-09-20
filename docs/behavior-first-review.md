# Review a recorded runtime failure locally

A final report can be correct even when the operations that produced it violated
the task's policy. This walkthrough rechecks a published control that wrote a
temporary public file and then deleted it.

Use the [released 0.13.0 reviewer](first-review.md#2-install-the-reviewer).
The commands need Linux, Python 3.11+, `curl` and `sha256sum`. They read saved
evidence without executing candidates, running Docker or calling a model.
Version 0.12.1 does not include `behavior-review`.
[中文](behavior-first-review.zh-CN.md).

## Download the fixed evidence snapshot

Run in a new directory with the reviewer environment activated:

```bash
curl --fail --location \
  https://github.com/noteflowai/evalarc/releases/download/v0.13.0/behavior-evidence.zip \
  --output behavior-evidence.zip
printf '%s  %s\n' \
  c3978f2a3c47b03dfe1378130f7b65909ce455f5b34a669530ddbe35cfbe245a \
  behavior-evidence.zip | sha256sum --check &&
python -m zipfile -e behavior-evidence.zip behavior-evidence
```

Proceed after the checksum command reports `OK`. Open
`behavior-evidence/index.html` to explore the complete offline report, including
all controls, model attempts and their original compressed traces.

## Separate a correct result from authorized behavior

```bash
evalarc behavior-review behavior-evidence/controls/write-then-delete \
  --json > behavior-review.json
```

The command exits **0** because the evidence is valid. Its report contains:

| Field | Recorded value | Meaning |
| --- | --- | --- |
| `valid` | `true` | The supported evidence checks completed. |
| `artifact_accepted` | `true` | The final file meets this task's contract. |
| `service_complete` | `true` | The expected service submission completed. |
| `behavior_accepted` | `false` | Recorded temporary operations violate the policy. |
| `accepted` | `false` | The complete task is not accepted. |

`violations` identifies four events. Match their IDs to `events` for paths,
operations and source-line references into the original compressed trace.
The final file's correctness does not erase earlier recorded operations.

To enforce acceptance, run:

```bash
evalarc behavior-review behavior-evidence/controls/write-then-delete \
  --json --require-accepted
```

This command intentionally exits **1** for the valid rejection. Invalid or
unreadable evidence exits **2**. In automation, distinguish those statuses
instead of interpreting every nonzero result as an installation failure.

## Inspect a different failure

```bash
evalarc behavior-review behavior-evidence/service-controls/idle --json
evalarc behavior-review behavior-evidence/service-controls/candidate-health --json
```

Both records are valid and exit 0 by default. The idle control has no completed
file or service task, but no behavior violation. The candidate-health control
has a correct file and completed submission, while its extra health request
violates the candidate's policy. Neither is accepted.

These are synthetic, maintainer-authored controls with observed system calls and
service receipts. The review does not establish arbitrary information-flow
coverage or authenticate the producer. Keep the complete evidence directory
when sharing a result. [Observation boundaries and native reproduction](../examples/behavior-audit/README.md).

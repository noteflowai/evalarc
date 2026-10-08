# Answer key: reviewer exercise

Facilitator only. Do not show this page to the reviewer before the run.

Source identity: `evalarc-0.17.7.tar.gz` (SHA-256
`3aef77bcd457365b4219c1fb98ab74a4d2eb5c763edb14f3cf44a3b669f44b81`),
`examples/results-diff/inspect/baseline.json`
(`da31a4be…c5d255`) and `current.json` (`26f02205…ece172`), produced by
Inspect AI 0.3.268 with scripted replies (two epochs, `mockllm/model`).

Expected commands (any equivalent is fine):

```bash
evalarc diff baseline.json current.json --output review
evalarc verify review --json
```

`evalarc diff` exits **1**; `verify` exits **0**.

| Item | Expected finding |
| --- | --- |
| Decision | Do not pass. The gate fails although `match accuracy` rises from 0.625 to 0.8125 |
| Blocking case | `refund-duplicate` regresses on `match` and `includes`, from 2/2 to 0/2 attempts |
| Recorded output | The current revision answers `refund:1003:12` (a second refund) where the target is `reject:1003` |
| Secondary signal | `cancel-pending` / `match` drops from 2/2 to 1/2 (`cancel:1006:queued` on one epoch); it is marked within sampling noise, but the gate still counts it |
| Evidence location | The blocking rows are in the CLI output, `review/summary.md` and `review/index.html`; the recorded output `refund:1003:12` appears in `review/index.html` (Current evidence) and `review/diff.json` (`current_detail`), not in `summary.md`. Byte-identical input copies are in `review/` |

Full credit needs the decision, the blocking case and check, and the recorded
output. Mentioning that the headline improvement does not clear the gate is
expected but not required.

## Maintainer dry run · 2026-10-08

The maintainer ran the setup and the two commands with `evalarc==0.17.7` from
PyPI outside the source checkout and obtained every item above. This confirms
the exercise is solvable and the key is correct. It is not an independent
measurement: the maintainer wrote the tool and the key. EA-03 timing remains
open until an independent reviewer completes the exercise.

# Decision coverage: held-out error at an abstention threshold

Suppose a probabilistic decision component answers only when its confidence is
at or above a threshold t. Then two questions matter: how often does it answer
(coverage), and how often is it wrong when it does (selective error)?
`evalarc decision-coverage` answers both questions offline from saved, labelled
choice decisions. It chooses t on **calibration** records only and reports that t
on **held-out** records. Invalid responses are counted separately from abstentions.

```sh
evalarc decision-coverage docs/assets/decision-coverage-synthetic.json \
  --max-error 0.2 --output runs/decision-review
xdg-open runs/decision-review/index.html
```

The bundled file is **authored synthetic data**. It exits 1 with the state
`exceeded`: t=0.66 meets 0.20 on calibration, but held-out error at that t
is 0.25. The baseline t=0 happens to give 0.20 on held-out data. With a small
calibration set, a chosen threshold is not guaranteed to generalize.

## Input: `evalarc.decision-records.v1`

```json
{
  "schema_version": "evalarc.decision-records.v1",
  "provenance": {"kind": "recorded", "description": "Saved grasp decisions, run 2026-09-20"},
  "model": {"id": "my-choice-component", "revision": "2026-09-20"},
  "questions": {"grasp": {"type": "choice", "options": ["top", "side", "pinch"]}},
  "records": [
    {"id": "r1", "question": "grasp", "split": "calibration", "label": "top",
     "response": {"distribution": {"top": 0.8, "side": 0.2}}},
    {"id": "r2", "question": "grasp", "split": "held_out", "label": "side",
     "response": {"error": "rate limited"}}
  ]
}
```

- `provenance.kind` is `synthetic` or `recorded`. The report shows it.
- Only `choice` questions are supported, each with 1–8 unique non-empty options.
- `split` is `calibration` or `held_out`. Both splits need at least one record.
- `response` is exactly `{"distribution": {...}}` or `{"error": "non-empty text"}`.
- An option missing from a distribution counts as p=0. Confidence is the largest
  probability. The prediction is the option with that probability; ties go to the
  option declared first.

## Rejected files versus invalid rows

The **whole file is rejected** (exit 2, nothing written) in these cases:

- the file is unreadable, not UTF-8 JSON, over 4 MiB or over 10000 records
- it has duplicate JSON keys or NaN/Infinity
- the schema version, provenance kind or model id/revision is wrong
- a question is not `choice` or has bad options
- a record is not an object, has an empty id or a duplicate id, names an unknown
  question or split, or has a label outside its options
- a split has no records
- `--max-error` is not a finite number in 0..1
- the output directory already exists

A **single record becomes an invalid row**, with its reason shown, when:

- its response is not exactly one `distribution` object or one non-empty `error`
  string (for example a list, both keys, or an empty error)
- it reports a provider error
- it names an undeclared option
- a probability is not a finite, non-Boolean number in 0..1 (`"0.6"`, `true`
  and `null` are invalid)
- its probabilities sum outside 1 ± 1e-6

Invalid rows are never answered and never counted as wrong, but they stay in the
denominator and lower coverage.

## Metrics

For each split and each threshold t, a valid record is **answered** when its
confidence is ≥ t and **abstained** otherwise. The report gives:

- coverage = answered / total
- selective error = wrong / answered (null when nothing is answered)
- wrong rate over all records = wrong / total
- the answered, abstained and invalid counts

The candidates are t=0 (the baseline, which answers every valid record) and every
distinct valid calibration confidence. `decisions.json` holds the full sweep.

## States and exit codes

With `--max-error E`, the chosen t is the smallest candidate that gives at least
one calibration answer and a calibration selective error ≤ E. Held-out labels
never affect the choice.

| State | Meaning | Records classified at | Exit |
| --- | --- | --- | ---: |
| `met` | Held-out selective error ≤ E at the chosen t | chosen t | 0 |
| `exceeded` | Held-out selective error > E at the chosen t | chosen t | 1 |
| `no_heldout_answers` | The chosen t answers no held-out record | chosen t | 1 |
| `no_threshold` | No candidate meets E on calibration data | t=0 | 1 |
| `no_target` | No `--max-error` given | t=0 | 0 |

In CI, exit 1 means the target was not met or could not be validated. Exit 2
means the input or arguments were rejected. `--help` lists both.

## Report

The new output directory contains:

- `input.json`, a byte-identical copy of the input
- `input.json.sha256`
- `decisions.json`, with the full sweep, every record with its outcome and reason,
  the state and the review threshold
- `index.html`, a self-contained report

`index.html` contains:

- a headline naming the state and the threshold
- tiles for held-out coverage, selective error and invalid count
- a threshold table with up to 22 rows: the baseline, the chosen row and up to 20
  evenly spaced candidates
- a record table of up to 1000 rows, ordered wrong, invalid, abstained, correct

The All, Wrong, Abstained and Invalid buttons and the search box filter the
record table. Their counts come from the full data. Without JavaScript, every
rendered row stays visible. The tables scroll horizontally on desktop and stack
into labelled cards below 480px.

## Limits

This command reviews recorded evidence. It does not call Jev, Kev or any other
provider, and it adds no dependencies. Confidence is whatever the component
reported. It is not calibration, and this command does not produce calibration
curves, confidence intervals, or accuracy, latency or cost claims. Thresholds
chosen on small calibration sets are unstable, so treat the results as
descriptive. Synthetic fixtures show that parsing and threshold logic work, not
that any provider is accurate.

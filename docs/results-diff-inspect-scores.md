# Malformed Inspect scores in evalarc diff

`evalarc diff` reads Inspect logs as `.json` files or `.eval` archives. Each sample's `scores` field must be a JSON object that maps scorer names to scores. Here is an example:

```json
"scores": {"match": {"value": "C"}, "includes": {"value": "C"}}
```

## What happens with a malformed value

Sometimes a log is hand-merged, edited or corrupted, and one sample ends up with a `scores` value that is not an object. That value can be a non-empty list, a non-empty string, a non-zero number or `true`. When EvalArc finds such a value, it rejects the whole log. It does not skip the sample, because a skipped sample would make its checks look removed or improved. The output below is illustrative. The sample id and position in your message come from your log.

```text
$ evalarc diff baseline.json current.json --output review
Inspect log sample 'refund-small' at position 0 has scores of type array: expected an object mapping scorer names to scores. A sample whose scores cannot be read would hide its checks from the comparison. Re-export the log from Inspect (inspect log dump) instead of editing it.
$ echo $?
2
```

The message names these things:

- the sample id, in the same form EvalArc uses in other loader errors (Python repr, so a string id appears in single quotes and ids longer than 80 characters are shortened)
- the sample's position in the log's sample list
- the JSON type it received: `array`, `string`, `number` or `boolean`

The command exits with code 2, the same code it uses for other unusable inputs such as a log with no samples. No report folder is written, because loading fails before the comparison runs. The rule is the same for an errored sample, because EvalArc reads its scores whenever the field is non-empty.

In CI, treat exit code 2 as "input unusable". Exit code 1 means the gate found blocking changes, and exit code 0 means the gate passed.

## How to recover

1. Find the sample by the id and position in the message.
2. Export the log again from Inspect, for example with `inspect log dump`, rather than fixing the field by hand.
3. Run `evalarc diff` again.

## What still loads as before

- An object value is read exactly as before.
- A missing `scores` key, `null`, or any empty or false value (`{}`, `[]`, `""`, `0`, `false`) still counts as no scores. An errored sample without scores still records the `sample error` check.

EvalArc does not validate the individual score entries inside a valid `scores` object. promptfoo and JUnit inputs are unaffected.

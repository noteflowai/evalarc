# Result files from Inspect AI, promptfoo and pytest

Each folder holds the actual output of one evaluation tool for two scripted
revisions of a refund-policy reply, plus the configuration that produced it.
The replies are fixed in the source files, so no model was called and the runs
can be repeated without keys. They are demonstration controls for
[`evalarc diff`](../../docs/ci-gate.md), not evidence about any model.

| Folder | Producer | Headline | What the headline hides |
| --- | --- | --- | --- |
| `inspect/` | Inspect AI 0.3.268, `mockllm/model`, 2 epochs | match accuracy 0.625 → 0.8125 | `refund-duplicate` now fails both scorers in both epochs; `cancel-pending` passes `match` in 1 of 2 epochs |
| `promptfoo/` | promptfoo 0.123.1, `echo` provider | pass rate 75% → 75% | the duplicate-refund test now fails both assertions while the large-refund test is fixed |
| `junit/` | pytest 8.4.2 `--junitxml` | no headline metric | the duplicate-refund outcome fails, and a passing check is now skipped |

```bash
evalarc diff examples/results-diff/inspect/baseline.json examples/results-diff/inspect/current.json
evalarc diff examples/results-diff/promptfoo/baseline.json examples/results-diff/promptfoo/current.json
evalarc diff examples/results-diff/junit/baseline.xml examples/results-diff/junit/current.xml
```

Each command exits **1** and names the checks that lost passes.

## How the files were produced

Inspect AI (the solver writes a fixed answer per revision; the current revision
changes one answer on its second epoch):

```bash
cd inspect
inspect eval refund_task.py -T revision=baseline --model mockllm/model \
  --epochs 2 --log-format json --log-dir logs-baseline
inspect eval refund_task.py -T revision=current --model mockllm/model \
  --epochs 2 --log-format json --log-dir logs-current
```

The two logs were renamed to `baseline.json` and `current.json`; their content
is unchanged. The same commands without `--log-format json` write zstd `.eval`
archives, which produce the identical diff under Python 3.14.

promptfoo (the echo provider returns the rendered prompt, and each prompt file
is one revision):

```bash
cd promptfoo
npx promptfoo@0.123.1 eval -c promptfooconfig.yaml --no-cache -o baseline.json
npx promptfoo@0.123.1 eval -c promptfooconfig.yaml -p current.txt --no-cache -o current.json
```

The files were written from `/tmp/evalarc-results-diff/promptfoo`, which
promptfoo records in the prompt paths. The JUnit files likewise come from
`/tmp/evalarc-results-diff/junit`.

pytest:

```bash
cd junit
REVISION=baseline python -m pytest -p no:cacheprovider -c /dev/null --rootdir=. \
  refund_checks.py --junitxml=baseline.xml
REVISION=current python -m pytest -p no:cacheprovider -c /dev/null --rootdir=. \
  refund_checks.py --junitxml=current.xml
```

`-c /dev/null --rootdir=.` keeps the repository's own pytest settings out of the
run, so test class names stay `refund_checks`.

The machine name in each `testsuite` `hostname` attribute was replaced with
`redacted`; nothing else was edited.

| File | SHA-256 |
| --- | --- |
| `inspect/baseline.json` | `da31a4be7a6224f653843f28922a1fb2d950a5aba26dd1a51238d780c5c5d255` |
| `inspect/current.json` | `26f02205242868f6cb29f46c10adf994b3af160551aef64ee5129af556ece172` |
| `promptfoo/baseline.json` | `5a7bdf5ab6ad895ae363831303fe2022ab76ce99c412913ef954c18246ec4d83` |
| `promptfoo/current.json` | `50e8be1caa574b0e0c84b69abd1f15f53a1df749cbd3e0ce5a59056049d838be` |
| `junit/baseline.xml` | `41483f94d990561062cccc0200c86be67135d7ebdd896ef1e4f9b641ae6045b9` |
| `junit/current.xml` | `cee8b2b38f14ae225eed60e19a572abd8febb023806447278377f6b1af5a3b38` |

# Blind judging: check the grader and compare with the baseline

Two offline workflows for the judgment steps that need a person or a separate
judge model. EvalArc prepares the material and scores the answers; it never calls
a model. [中文](judging.zh-CN.md).

| Mode | Question | Practice it implements |
| --- | --- | --- |
| `grader` | Does the recorded grader agree with an independent judge? | Read a sample of graded transcripts before trusting the grader |
| `pairwise` | Is the current output better than the baseline's for the same case? | A blind judge picks the better output without knowing which is the baseline |

Both read Inspect AI or promptfoo results, which record outputs. JUnit reports
carry no outputs and exit 2.

## Grader spot check

```bash
evalarc judge-packet grader examples/results-diff/inspect/current.json --sample 10 --output spot
```

```text
Judging packet: 10 grader item(s) of 32 eligible
Give the judge only: spot/share
Keep private: spot/key.json
```

Attempts are sampled half from each recorded verdict where possible, so rare
failures (or rare passes) are always reviewed. `spot/share/` holds `packet.json`,
a readable `index.html` with each input, expected answer and output, and
`verdicts.template.json`. The grader's verdicts, the sample seed and the source
files stay outside `share/`.

The judge fills in `pass`, `fail` or `unsure` per item and declares who judged
(`"kind": "human"`, or `"kind": "model"` with `"model"`). Then:

```bash
evalarc judge-score spot verdicts.json --min-agreement 0.9 --output spot-score
```

The report gives agreement with a 95% interval, Cohen's kappa, and a confusion
table of **false accepts** (grader passed, judge failed) and **false rejects**,
listing each disagreement. Read those first: a grader bug is the most common
reason an evaluation misleads. Because the sample is stratified, agreement is not
the grader's accuracy on all attempts.

## Pairwise comparison with the baseline

```bash
evalarc judge-packet pairwise baseline.json current.json --sample 40 --seed 7 --output ab
```

Each item shows the same case and attempt from both runs as **A** and **B**, with
the order randomized per item and the mapping kept in `ab/key.json`. Identical
outputs are skipped. The judge answers `A`, `B` or `tie`:

```bash
evalarc judge-score ab verdicts.json --require-current-preferred
```

The report unblinds the answers: current wins, baseline wins and ties, the
current win rate among decisive items with a 95% interval, and state
`current_preferred`, `baseline_preferred` or `no_clear_preference`. It also
reports how often the judge chose position A; an interval excluding 50% is
flagged as **position bias**.

## Running a judge model with `judge-run`

EvalArc does not call the judge itself, but `judge-run` can run your judge
command once per item:

```toml
# judge.toml
command = ["{python}", "{config_dir}/judge.py"]
model = "provider/judge-model"   # recorded in the verdicts; must differ from the tested model
timeout_seconds = 120
```

```bash
evalarc judge-run spot --config judge.toml --output verdicts.json --trust-local
```

The command runs inside `spot/share/` and gets one item on stdin as JSON
(`mode`, `instructions`, `allowed_verdicts`, `item`). It must print
`{"verdict": "..."}` on its last stdout line. It never receives `key.json`.
Placeholders are `{python}`, `{packet}` (path to `share/packet.json`) and
`{config_dir}`. Any failed, timed-out or invalid answer exits 2 and writes no
verdicts. `--repeat N` (up to 10) asks the judge N times per item; `judge-score`
then reports **judge consistency**: the share of items that got the same answer
every round, with an interval, and the items whose answer changed. A judge that
changes its answer on the same input adds noise to every comparison it makes. The command runs on the host with your environment, so `--trust-local`
is required.

## Gates and exit codes

`judge-score` exits 0 after scoring. `--min-agreement A` (grader) and
`--require-current-preferred` (pairwise) exit 1 unless every item is answered,
the judge is not a model under evaluation, and the requirement holds (for
pairwise, also no position bias). Mismatched packets, edited `share/packet.json`,
unknown item IDs or invalid answers exit 2.

A model judge whose name matches a model recorded as under evaluation is flagged
`self_judged`. Use a judge from a different model, and a rubric of checkable
criteria rather than a 1–5 scale.

## Limits

EvalArc cannot see who actually judged or whether they saw the key. Keep
`key.json` away from the judge, record verdicts once, and do not reuse a packet
after its key has been shared. Attempts of one case are not independent, so
intervals are optimistic.

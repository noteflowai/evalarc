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

`judge-packet pairwise --allow-unsure` adds `unsure` to the allowed answers, so a
judge without enough information says so instead of guessing. Unsure answers are
counted (`unsure` in the result) and excluded from the win rate. Grader packets
always allow `unsure`.

## Several annotators: agreement and consensus

A task is well specified when two domain experts reach the same verdict on their
own. Give the same `share/` folder to two or more annotators (people, or separate
judge models through `judge-run`) and score their files together:

```bash
evalarc judge-score spot alice.json bob.json carol.json \
  --consensus majority --min-annotator-agreement 0.8 --min-agreement 0.9 --output panel
```

- **Agreement between annotators.** For every pair: items both decided,
  percent agreement with a 95% interval, and Cohen's kappa; across all
  annotators, Fleiss' kappa over the items every annotator decided. `unsure`
  and unanswered items are excluded.
- **Consensus.** `majority` (default) needs more than half of all annotators on
  the same decisive answer; `unanimous` needs every annotator. `unsure` never
  counts toward a consensus. Items without one are listed as `undecided` and
  left out.
- **Grader or baseline against the consensus.** The usual grader confusion
  table and false accepts/rejects, or the pairwise preference, are computed
  against the consensus answers.
- `--min-annotator-agreement A` also fails (exit 1, gate `reason`
  `annotators_disagree`) unless every item is answered by every annotator and
  every pair agrees on at least A of the items both decided. Low agreement means
  the task or rubric is ambiguous: fix it before trusting the grader comparison.
  With another gate, `judge_gate_passed` keeps that gate's own outcome and
  `passed` requires both.
- Each annotator is listed with its file hash, answered and unsure counts and
  `self_judged`; any self-judging annotator flags the result. Byte-identical or
  repeated files exit 2. `--output` keeps every file as `verdicts-01.json`,
  `verdicts-02.json`, … With one verdicts file, the result is unchanged.

These numbers measure the annotators you used. They become calibration evidence
only for a permitted, labeled corpus and qualified annotators; scripted examples
are not.

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

`judge-score` exits 0 after scoring. `--min-agreement A` (grader),
`--min-annotator-agreement A` (several verdicts files) and
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

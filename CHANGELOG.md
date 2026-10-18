# Changelog

## Unreleased

- `evalarc eval-health --reference RESULT` reads a run of the same evaluation
  with a known-good solution. Checks the reference does not pass on every
  graded attempt raise `reference_fails` (warning) and are triaged
  `task_or_grader_broken`; errored or skipped reference attempts raise
  `reference_unassessed` and recorded cases it lacks `reference_incomplete`
  (both info). A reference sharing no case IDs exits 2. `health.json` gains
  `reference`; the file is copied and verified.
- `evalarc review-inputs --prompt FILE...` warns with `unstated_requirement`
  when a `label`, `json_keys` or `json_schema` case is graded on labels, keys or
  enum values that neither the prompt files nor the case input mention (whole
  words for ASCII terms; anywhere for CJK terms).
  `review.json` gains `prompt_files`.
- `eval-init` graders gain the deterministic checks `regex` (`re.fullmatch` on
  the stripped output; outputs over 100,000 characters fail) and `fuzzy`
  (difflib similarity at least `min_ratio`, default 0.9). `review-inputs`
  validates the pattern and `min_ratio`.
- Case manifests (`evalarc.case-manifest.v1`) and `eval-init` `cases.jsonl`
  accept optional case attributes: `expect_action` (`act` | `abstain`),
  `expect_change` (`fail_to_pass` | `pass_to_pass`), `impact`
  (`critical` | `high` | `normal` | `low`) and `owner`. A manifest may declare
  them without suites.
- `diff --cases` adds `case_attributes`: baseline and current overtriggering
  (failed `abstain` cases) and undertriggering (failed `act` cases),
  fail-to-pass resolved/unresolved and pass-to-pass broken cases, and blocking
  changes ordered by impact with owners. Changed checks carry their case's
  attributes. `--require-f2p` also fails the gate unless every `fail_to_pass`
  case succeeds on every current trial and no `pass_to_pass` case breaks.
- `eval-health --cases` adds `behavior` per file, and `eval-health` and
  `review-inputs` report `one_sided_behavior` (warning), `behavior_imbalance`
  and `behavior_undeclared` (info); `review-inputs` also reports
  `impact_undeclared` (info).
- New examples: `examples/results-diff/inspect/attributes.json` and
  `examples/results-diff/junit/cases.json`.
- `evalarc diff --transcript-metrics` (Inspect) counts each attempt's recorded
  messages and adds `n_turns` (generated assistant messages), `n_tool_calls`,
  `n_messages` and `n_error_retries` to `usage`; `--cost-metric turns` and
  `tool_calls` gate on them with `--max-cost-ratio`. promptfoo and JUnit record
  none, so they stay unknown. The GitHub Action gains `transcript-metrics` and
  accepts the new cost metrics.
- `evalarc eval-health --transcript-metrics` adds per-file `transcripts`
  (mean and maximum turns, tool calls, messages and error retries) and the
  warning `limit_reached` for attempts stopped by a message, time or other
  non-token limit. `--cluster-errors` adds the warning `correlated_errors` when
  one normalized error message recurs in at least 3 cases of one file
  (status and exit codes kept; skips not counted).
- `judge-packet --include-transcript [--transcript-max-chars N]` shows the judge
  each attempt's recorded messages, tool calls and tool errors (text only; no
  scores, metadata or usage), following the hidden A/B order in pairwise
  packets. Packets above 256 MiB now exit 2 before anything is written.
- Output compatibility: without these options, `diff.json`, `health.json`,
  packets, `params.json` and the reports are unchanged from 0.20.1, and
  earlier folders verify. Folders written with them record the option and
  need this version or later to verify.
- `evalarc judge-score PACKET VERDICTS...` accepts two or more verdicts files,
  one per annotator. It reports agreement between annotators (per pair: items
  both decided, percent agreement with a 95% interval, Cohen's kappa; overall:
  Fleiss' kappa), combines answers with `--consensus majority|unanimous`
  (`unsure` never counts; items without consensus are `undecided` and
  excluded), and scores the grader or the pairwise preference against the
  consensus. In panels, any gate fails while an item is `undecided`.
  `--min-annotator-agreement A` fails (exit 1) with reason `incomplete`,
  `self_judged`, `undecided_items` or `annotators_disagree` unless every item is
  answered and decided, no annotator is a model under evaluation, and every
  pair agrees on at least A. `--output` keeps each file as `verdicts-NN.json`.
- `judge-packet pairwise --allow-unsure` adds the answer `unsure`, counted and
  excluded from the win rate.
- Output compatibility: with one verdicts file and default packets, packets,
  `score.json` (key order included), the summary, the page and the console are
  unchanged.

## 0.20.1 — 2026-10-17

- test: EA-02 regression corpus that pins how the diff gate handles missing evidence. tests/test_feature_cb4fe5a9ab91.py adds a synthetic regression corpus for EA-02. It pins what evalarc diff does for each category: control and added checks pass (exit 0). Removed checks, fewer epochs at the same pass rate (less_covered), a JUnit skip as the only change (unassessed) and an incomplete baseline or current run fail (exit 1), and the summary heading names the cause. Malformed samples, duplicate IDs and non-comparable runs are rejected (exit 2) with a message naming the problem. An invariant test checks that no case with missing evidence passes. The corpus found one defect, which is fixed in results_diff.py: an Inspect sample ID repeated with a null, boolean, string or other non-integer epoch, or with an integer epoch mixed with a missing one, used to count as an extra attempt and could hide lost coverage. It now exits 2. Logs where every copy of an ID has no epoch key still load as before. docs/ci-gate.md and docs/ci-gate.zh-CN.md now have a Regression corpus table.

## 0.20.0 — 2026-10-15

- `evalarc hillclimb-review --cases MANIFEST` and the `hillclimb-run` config key
  `cases` read capability/regression suite roles. A step that makes a
  regression-suite case go from succeeding on every trial of the kept result
  to a failed, unassessed or missing trial, or to fewer recorded trials, is
  rolled back
  (`rollback_regression`, reason naming the count) even when both partitions
  improved; `hillclimb-run` restores the workspace as for any rollback. A
  regression case that already failed in the kept result does not block later
  steps. Each step records `regression_suite_broken`, the review gains
  `suites`, and a new recommendation `do_not_merge_regression_suite` (exit 1)
  guards the final result against the baseline. A manifest with no regression
  case exits 2 (for `hillclimb-run`, before the baseline is evaluated).
- Output compatibility: without `--cases`/`cases`, `hillclimb.json`,
  `params.json`, `loop.json` and the reports are unchanged, so earlier folders
  still verify. Folders written with it copy the manifest to `cases.json` and
  need this version or later to verify.

## 0.19.0 — 2026-10-15

- `evalarc diff --cases MANIFEST` reads the capability/regression suite roles of
  a case manifest. Changed checks carry their case's `suite`, and `diff.json`
  gains `suites`: per suite, baseline and current case-level trials with pass@k
  and pass^k on that suite's cases, `regression_failures` (regression cases
  that did not succeed on every current trial: failed, unassessed or missing)
  and `undeclared_cases`. The summary, HTML report and console show the same.
  The default gate is unchanged.
- `--require-regression-suite` (requires `--cases`) also fails the gate unless
  every regression case succeeds on every trial of the current run, including
  failures already present on the baseline.
- The GitHub Action gains the inputs `cases` and `require-regression-suite`,
  the output `regression-failures`, and a warning annotation for each of the
  first 10 failing regression cases.
- Output compatibility: without `--cases`, `diff.json`, `params.json`, the
  summary and the page are unchanged, so earlier folders still verify. Folders
  written with `--cases` copy the manifest to `cases.json`, record
  `require_regression_suite` and need this version or later to verify. A
  manifest that declares no suite exits 2, and so does
  `--require-regression-suite` when no case is in the regression suite.
- Case manifests (`eval-health --cases`, `diff --cases`, `review-inputs`): an
  entry that matches no case as a glob now also matches a case whose ID equals
  it exactly, so pytest IDs such as `test_policy[refund]` need no `[[]`
  escaping. Such entries used to exit 2; entries that matched before match the
  same cases, so earlier folders still verify.
- Console lines of `evalarc diff` replace control characters in case IDs,
  check names, file names and the baseline status with spaces, so a crafted
  value cannot add a console line. The GitHub Action also pauses
  workflow-command processing (`::stop-commands::` with a random token) while
  `evalarc diff` runs, so values printed from the result files cannot issue
  workflow commands such as spoofed annotations. Saved reports are unchanged.

## 0.18.1 — 2026-10-15

- `eval-init` / `review-inputs` accept an optional `suite` (`capability` or
  `regression`) per case in `cases.jsonl` and copy it into the case manifest
  written by `--write-manifest`, so a scaffolded project can use the 0.18.0
  `eval-health --cases` suite findings without hand-editing the manifest.
  Any other value exits 2 with the file and line. When some case declares a
  suite, the review counts suites (`suites` in `review.json`, the console line
  and the page) and reports the info findings `suite_undeclared` and
  `no_regression_suite`, and the case table gains a Suite column. Cases
  files without `suite` produce the same manifest, findings and review page as
  before.

## 0.18.0 — 2026-10-14

- `evalarc eval-health` reports case-level trials with pass@k and pass^k. A
  trial is one recorded attempt of a case (Inspect epoch, promptfoo repeat,
  repeated JUnit testcase). It fails when any recorded check failed; without a
  failure it is unassessed when a check has no outcome, a check recorded on
  another attempt is missing, the Inspect sample recorded an error, or no check
  was recorded. Unassessed trials are listed but excluded from the
  denominators, never counted as passes. For k = 1 to the largest assessed trial count (at most 10),
  `health.json` gains `trials.runs[].by_k` with the unbiased estimators
  `pass_at_k` (at least one of k trials succeeds) and `pass_hat_k` (all k
  succeed), averaged over cases with at least k assessed trials, plus
  per-case counts. The Markdown summary shows k = 1 and the largest k per
  file; the HTML report lists every k.
- The case manifest (`evalarc.case-manifest.v1`) accepts an optional
  `"suite": "capability" | "regression"` per entry. With `--cases`, a
  regression case with a failed or unassessed trial in the last file, or
  missing from it, raises the warning `regression_case_failing`; a capability
  case that succeeded on every one of at least two trials raises the info
  finding `graduation_candidates`. Manifests without `suite` behave as before.
- Output compatibility: new `eval-health` folders record `"trial_metrics": true`
  in `params.json` and contain the `trials` key. `evalarc verify` recomputes a
  folder with the options it recorded, so folders written by earlier versions
  (no `trial_metrics`) still verify unchanged; new folders need this version or
  later to verify. Finding ids, severities and exit codes of existing findings
  are unchanged.
- When two scorers of one Inspect sample map to the same check name (a scorer
  `s/x` beside a dict-valued scorer `s` with key `x`), the attempt's recorded
  verdict in `cases.jsonl` now keeps a failure (then a missing outcome) instead
  of whichever scorer came last. Check tallies were already counted per scorer
  and do not change.

## 0.17.10 — 2026-10-13

- fix: reject Inspect samples without a usable id instead of inventing case None. evalarc diff and load_results now reject Inspect samples that have no usable identity, instead of comparing them under an invented case name or failing with internal error text. This applies to JSON logs and .eval archives. Each sample is checked in recorded order, before any case bookkeeping and before the duplicate-sample guard. A sample that is not a JSON object fails with: 'Inspect log sample at position N is not an object (got TYPE)'. A sample whose id is missing, null, boolean, float, a list or an object fails with: 'Inspect log sample at position N has an invalid id SHOWN (TYPE): expected an integer or a string'. Both messages end with re-export guidance. The CLI prints evalarc: MESSAGE and exits 2. No diff.json, summary.md or index.html is written, and the --markdown file is left untouched. Two null-id samples now get the invalid-id message, not a misleading duplicate-sample error. Integer, string and empty-string ids behave as before, and the shipped example pair gives the same changes, counts and gate_passed. docs/ci-gate.md and docs/ci-gate.zh-CN.md describe the accepted id types, both messages and the re-export command.

## 0.17.9 — 2026-10-11

- fix: reject duplicated promptfoo result rows instead of counting them as attempts. evalarc diff now rejects promptfoo --output files in which the same result row appears twice. Before, the promptfoo loader counted every entry in results.results[] as one more attempt of its test. A row copied in by merging, concatenating or editing a file would inflate the attempt and assessed counts. That could hide lost coverage or make a less reliable check look unchanged. The loader now keys each row by (testIdx, promptIdx, provider). If a key repeats, loading stops with a ValueError, the same rule Inspect logs already follow. The message names the format, the duplicated testIdx, promptIdx and provider, and the test label. The label and provider are escaped and truncated with the existing _shown_id helper. The message also tells the user to re-export with promptfoo eval --output. evalarc diff exits 2 for a duplicate in either the baseline or the current file. It prints the message to stderr and writes no verdict or output folder. A promptIdx that is a list or object is also rejected as malformed input (exit 2), so it cannot crash the loader. Rows without an integer testIdx are not checked. --repeat output, where each repeat gets a new testIdx, still loads as attempts of one test. For valid files, results and exit codes 0 and 1 are unchanged. docs/ci-gate.md and docs/ci-gate.zh-CN.md describe the rule, exit 2 and how to recover.

## 0.17.8 — 2026-10-09

- fix: extend 0.17.7's Markdown summary escaping to the paths it did not cover.
  A carriage return in a harness-leakage hit (file, case or matched text), an
  `eval-health` result file name, or a `judge-score` case, check or judge model
  name could still start a fake `### EvalArc: No check lost passes` heading in
  the rendered summary (GitHub's renderer treats CR as a line ending). Raw HTML
  or link syntax in the bare-text `eval-health` and `judge-score` lines rendered
  as a heading or a live link, and GitHub autolinked a bare URL, `www.` host or
  e-mail address used as a model, file, stop-reason or config value in an
  `eval-health` finding. The leakage table uses the shared CR-safe `_cell`;
  file, case, check and model names and the values embedded in finding text are
  code-formatted (GitHub does not autolink inside code); the rest of the finding
  text goes through a new `markdown_text` helper (single line, Markdown/HTML
  punctuation escaped outside code spans).
- Output compatibility: `diff.json` and the `judge-score` JSON are unchanged. In
  `health.json`, five human-readable text fields now contain the same code-span
  backticks as the summary, for every input: the `message` of `saturated`,
  `self_graded` and `capability_inversion` (for example `` `current.json` passes
  84.4% ``... instead of `current.json passes 84.4%`...), and the item `detail` of
  `truncated_outputs` and `config_not_applied`. Finding ids, severities, values,
  item keys, the raw fields they quote (`runs[].source.name`,
  `graders.self_graded`, `generate_config`, item `file`/`case_id`/`check`), the
  JSON structure, `healthy`, `warnings` and the 0/1/2 exit codes are unchanged,
  and `evalarc verify` still recomputes saved folders. Tools that parse or match
  those message/detail strings should read the structured fields instead.
- Compatibility: a `judge-score` verdicts file declaring a human judge with a
  non-string `model` (for example `{"kind": "human", "model": 123}`) used to
  crash Markdown rendering with an uncaught `TypeError`, so the default output
  exited 1 even when the gate passed (`--json` was unaffected). It now renders
  the value as code and exits by the gate result. Input validation of
  `judge.model` for human judges is unchanged.
- docs: the first-review walkthrough (English and Chinese) and the reviewer
  exercise extract a download only if its SHA-256 check succeeds (`&&`); the
  expected exit-1 steps stay separate commands.

## 0.17.7 — 2026-10-06

- fix: escape untrusted run status and metric name in the Markdown gate summary. evalarc diff now escapes three kinds of untrusted input-file text in its Markdown gate summary (summary.md, the --markdown/--summary target and the GitHub Action job summary): the run-status sentences for an unfinished current or baseline run, the 'Headline metric: ... from the source tool.' sentence, and the case and check identifiers in the change table. A new helper, _inline_code_text, escapes pipes as \|, turns backticks into apostrophes and replaces every line ending (CRLF, CR, LF) with a space. A crafted status, metric name or case_id therefore stays inside one single-line code span. It cannot close the span, add a fake '### EvalArc' heading or make a failed gate look like a pass. Ordinary values render byte-for-byte as in 0.17.6. Table cells and the baseline-incomplete sentence already escaped pipes and backticks; they now also turn a carriage return into a space. Only the rendered Markdown changes. The result dict and diff.json keep the raw recorded values. gate_passed, blocking_changes and exit codes (0 pass, 1 gate failed, 2 unusable input) are unchanged. docs/ci-gate.md Limits describes the escaping.

## 0.17.6 — 2026-10-06

- `review-inputs --random-split F --seed N` holds out a random, source-stratified
  share of cases and records it in `cases.jsonl`; it refuses once `held_out` is
  declared, so the split cannot be reshuffled after results are seen.
- The `eval-init` grader adds `json_schema` (a JSON Schema subset) and `command`
  (an argument array such as a unit-test runner, passing on exit 0) checks,
  validated by `review-inputs`.

## 0.17.5 — 2026-10-05

- fix: reject duplicate Inspect samples instead of counting them as extra attempts. evalarc diff now refuses an Inspect AI log, JSON or .eval archive, that contains the same (sample id, epoch) pair more than once. Before this change the copy was silently counted as an extra attempt, which inflated coverage and could hide a less_covered change. The ids are compared after str(), so an integer 7 and a string '7' in the same epoch also count as a duplicate. A duplicate in either the baseline or the current file makes load_results raise ValueError, and the CLI prints that message to stderr and exits 2 before any comparison. The message names the sample (shown with repr() and cut to 80 characters, so newlines and control characters stay escaped) and the epoch, and tells you to re-export with inspect log dump. Valid multi-epoch logs, logs without an epoch field, the recorded examples, the diff.json schema and the gate logic are unchanged. docs/ci-gate.md and docs/ci-gate.zh-CN.md add this case to the exit-2 list.

- CI tests Python 3.14 alongside 3.11–3.13, and the package declares 3.14
  support. A new test reads zstd-compressed Inspect `.eval` archives directly
  on 3.14 and checks they give the same diff as the JSON logs.
- Dependabot opens weekly grouped update PRs for GitHub Actions and the npm
  browser-check/front-end toolchain.

## 0.17.4 — 2026-10-02

- Add `evalarc view [DIR]`: a read-only, loopback-only local viewer that lists
  every report under a folder with its verdict, following the `inspect view` /
  `promptfoo view` pattern with the standard library only. It rejects foreign
  `Host` headers, path traversal and directory listings. `--write-index` writes
  the same index as a static page.
- Report pages: light and dark themes from the system setting, sticky table
  headers, tabular numbers, sortable columns (WAI-ARIA APG pattern) and a row
  filter on long tables. The enhancement script is a packaged asset inlined and
  allowed by CSP hash; pages remain complete without JavaScript.
- `scripts/check_reports_browser.cjs` now uses axe-core (WCAG 2.2 A/AA, light and
  dark) instead of a custom contrast check, and runs end-to-end reviewer tasks:
  verdict on the first screen, skip link, keyboard sorting, filtering, 320 px
  reflow, no-JavaScript, print, and browsing from the viewer index.
  `@axe-core/playwright` 4.13.0 is a pinned dev dependency.
- The report front end is now TypeScript (`frontend/report_enhance.ts`, strict
  mode), compiled to the packaged `report_enhance.js`. The compiled file is
  committed, so installing EvalArc still needs no Node; CI fails when it is
  stale. TypeScript 7.0.2 is a pinned dev dependency. The Python core is
  unchanged.

## 0.17.3 — 2026-10-01

- fix: fail the diff gate when the baseline run did not finish. evalarc diff and the GitHub Action now fail the gate (exit 1) when the baseline run did not finish. Before this change, an Inspect baseline log with a status other than success could pass, because checks missing from it were classified as 'added', which never blocks. diff.json now records "baseline_incomplete": true. The key is omitted for a finished baseline, so those reports are unchanged apart from created_at and version. Default stdout prints 'The baseline run is incomplete (status error); N check(s) appear only in the current run and were not compared. Rerun the baseline to completion; the gate fails.' summary.md always includes the line below the table: 'The baseline run did not finish (status `error`); the gate fails because checks missing from it cannot be compared. N check(s) appear only in the current run. Rerun the baseline to completion.' Its heading says 'the baseline run is incomplete' only when there are no blocking changes and the current run finished; otherwise the existing blocking or both-incomplete heading appears. index.html shows 'Gate failed' with the reason 'the baseline run is incomplete'. When no blocking rows exist, it tells you to rerun the baseline. evalarc verify recomputes the same result. docs/ci-gate.md and the README CI-gate paragraph document the rule.

## 0.17.2 — 2026-10-01

- Offline HTML reports for `diff`, `eval-health`, `hillclimb-review`,
  `judge-score` and `review-inputs` open with a verdict banner: the decision,
  the reason and the next step, marked with a symbol as well as color. The
  `judge-score` page no longer shows raw Markdown and adds the confusion table.
  All report pages gain a `main` landmark, a skip link, scoped table headers,
  keyboard-focusable scroll regions, two-column summary cards on phones and a
  print style. `scripts/check_reports_browser.cjs` checks these in CI.
- The audit, evaluation, comparison, repetition and suite reports also open
  with a verdict banner and share the landmark, skip link and table
  accessibility. The browser check now covers all ten report kinds and fails on
  text below WCAG 2.2 AA contrast.
- `evalarc verify` now recomputes folders written by `diff`, `eval-health`,
  `hillclimb-review` and `hillclimb-run`. Each folder adds `params.json` (every
  option) and copies scanned harness files to `harness/`, so leakage scans can
  be rerun. The commands and the verifier share one computation.

## 0.17.1 — 2026-10-01

- `hillclimb-review` rolls a step back when a held-out check keeps its pass
  rate on fewer assessed attempts (`less_covered`), and the GitHub Action
  annotates it. The gate uses the shared blocking-kind definition (#56).

## 0.17.0 — 2026-10-01

### Evaluation projects

- Add `evalarc eval-init DIR`: a runnable evaluation project with `cases.jsonl`
  (source, held-out and difficulty per case), an application stub, a
  programmatic grader (`exact`, `contains`, `label`, `json_keys`), an
  evaluation runner that writes Inspect-format logs over several epochs, a stub
  proposer and a `hillclimb.toml` that only lets the loop edit `prompt.md`.
- Add `evalarc review-inputs cases.jsonl`: validates every case, renders an input
  review page before any run, reports held-out, duplicate, size,
  dominant-answer and source findings, and regenerates the split and case
  manifest from the case file. `--require-clean` exits 1 on warnings.
- `hillclimb-run` now completes when every proposal is rejected before
  evaluation, recommending `no_change_kept`.

### Configuration, judge consistency, eval size and cache diagnostics

- Inspect loaders record `model_generate_config` settings (reasoning effort and
  tokens, max tokens, temperature). `eval-health` reports `config_not_applied`
  when extended thinking is requested but every attempt records zero reasoning
  tokens, and lists each file's settings.
- `eval-health` reports the evaluation size (cases × attempts × files, recorded
  duration and cost), estimates a planned run with `--plan-attempts` and
  `--plan-configs`, and with `--output` writes `cases.jsonl` (one line per
  attempt) and a per-case page linking to recorded outputs.
- `judge-run --repeat N` asks the judge N times per item; `judge-score` reports
  judge consistency and the items whose answer changed.
- `diff` reports `usage.cache_read_share` when input and cache-read tokens are
  recorded.

### Run the loop and the judge with your own commands

- Add `evalarc hillclimb-run CONFIG --output DIR --trust-local`. A TOML file
  declares the workspace, the files the loop may edit (`allow`), the held-out
  split, and `evaluate` and `propose` command arrays. Each iteration writes the
  tuning failures of the last kept result (never held-out cases) for the propose
  command, stops if it edits files outside `allow`, rolls back patches that add
  held-out case text (`rollback_leakage`) or paste tuning case text
  (`rollback_pasted_case`) before evaluating, then keeps or rolls back with the
  `hillclimb-review` rules, triages stalls and stops below noise. The workspace
  ends at the last kept version with `original/`, `final.diff`, per-step
  patches and the review report. Exit 0 merge recommended, 1 not, 2 failure.
- Add `evalarc judge-run PACKET --config judge.toml --output verdicts.json
  --trust-local`: runs a judge command once per packet item from `share/`,
  validates each verdict and records the declared judge model.
- `eval-health` adds `model_judge_replaceable` for model-graded checks whose
  outputs are few or JSON, where a programmatic check would do.
- Loaders record which checks are model-graded (Inspect `model_graded_*`
  scorers, promptfoo `llm-rubric`, `factuality`, `g-eval` and similar).
- Add the scripted `examples/hillclimb-run/` workspace, `docs/hillclimb-run.md`
  (+ zh-CN), and a `SECURITY.md` note. EvalArc still makes no model calls.

### Blind judging and case provenance

- Add `evalarc judge-packet grader|pairwise` and `evalarc judge-score`. Grader
  packets sample recorded attempts stratified by verdict and hide the verdict;
  scoring reports agreement with a 95% interval, Cohen's kappa, false accepts and
  false rejects. Pairwise packets show baseline and current outputs of the same
  case and attempt in randomized, hidden A/B order; scoring unblinds and reports
  the current win rate with an interval, position bias and a
  `current_preferred`/`baseline_preferred`/`no_clear_preference` state. The
  judge receives only `share/`; the key stays outside it and is bound to the
  packet by SHA-256. Model judges matching a model under evaluation are flagged
  `self_judged`. `--min-agreement` and `--require-current-preferred` exit 1
  when not met. EvalArc does not call the judge. See `docs/judging.md` (+ zh-CN).
- Loaders keep each attempt's output text (up to 20,000 characters) and its
  per-check verdicts for packets; diff output is unchanged.
- `eval-health --cases MANIFEST` reads an `evalarc.case-manifest.v1` source
  declaration and reports `adversarial_sampling`, `no_real_cases`,
  `mostly_synthetic`, `traffic_only` and `provenance_undeclared`. Add an authored
  `examples/results-diff/inspect/cases.json`.

### `evalarc hillclimb-review`

- New offline command that replays hillclimbing keep/rollback rules over a
  baseline and the saved result after each proposed change, with a required
  held-out split. Each step is compared with the last kept result:
  `rollback_regression` (a held-out check lost passes or a partition fell),
  `rollback_overfit` (tuning improved, held-out did not), `keep` (quality: both
  improved; `--objective cost`: recorded cost fell with neither partition
  falling) or `rollback_no_gain`. After `--stall-after` consecutive rollbacks
  the remaining tuning failures are triaged, and the report says to stop when
  the headroom is below the resolvable change. The final kept result is compared
  with the baseline on held-out cases with 95% intervals: `merge`, `merge_cost`
  (exit 0), or `no_change_kept`, `do_not_merge_regression`,
  `do_not_merge_within_noise`, `do_not_merge_cost`, `do_not_merge_leakage`
  (exit 1); invalid input exits 2. `--output` also writes
  `tuning-failures.json`, which excludes every held-out case.
- Add an authored six-step example with recorded costs and its generator,
  `examples/hillclimb-review/build.py`, and `docs/hillclimb-review.md`
  (+ zh-CN) with a map from each practice in the article to an EvalArc check.

### Grader consistency, truncation and self-grading

- Loaders record a SHA-256 of each attempt's output, its stop reason and the
  grader models. `diff` marks a changed check `same_output_different_verdict`
  when a byte-identical output was graded differently, and reports check pass
  rates with 95% Wilson intervals.
- `eval-health` adds `inconsistent_grading`, `truncated_outputs` and
  `self_graded` findings, intervals, mean duration and cost per run, and a
  failure triage of the last file (`pipeline`, `truncated`,
  `grader_inconsistent`, `regressed`, `never_passes`, `variable`,
  `consistent_failure`).
- `examples/model-upgrade/reports/` is regenerated from the unchanged JUnit
  files to include the intervals.

### Held-out split and harness leakage in `evalarc diff`

- Add `--held-out SPLIT`, reading an `evalarc.case-split.v1` file of held-out
  case IDs or glob patterns. `diff` compares the check-attempt pass rates of the
  tuning and held-out partitions and reports `generalizes`,
  `overfitting_signal` (tuning cases improved beyond sampling noise, held-out
  cases did not), `held_out_regressions`, `held_out_gain_within_noise` or
  `no_measurable_gain`. The split file is copied to `split.json` with its
  SHA-256. Every entry must match a recorded case and at least one tuning case
  must remain.
- Add `--harness PATH ...` to scan prompt, skill and tool-description files for
  recorded case inputs and expected answers copied verbatim (case- and
  whitespace-insensitive, `--leak-min-chars`, default 12). Hits list the file,
  line, case and partition. Negated and code promptfoo assertions are not
  treated as answers.
- Add opt-in `--require-generalization`: exit 1 unless held-out cases improve
  beyond noise and no held-out case text appears in the harness. Without it the
  exit code is unchanged.
- The GitHub Action gains `held-out`, `harness` and `require-generalization`
  inputs, `generalization-state` and `leakage-hits` outputs, and file/line
  annotations for leaks. Add an authored split and leaking prompt to
  `examples/results-diff/inspect/`.

### Cost at equal quality in `evalarc diff`

- `diff.json` gains a `usage` block: mean recorded cost, token and duration
  usage per attempt over cases present in both runs (Inspect `model_usage` and
  working time, promptfoo `cost`, `tokenUsage` and `latencyMs`, JUnit test
  time). Missing values stay unknown and are never counted as zero. Markdown and
  HTML reports show it when cost or tokens were recorded.
- Add opt-in `--max-cost-ratio R` with `--cost-metric auto|cost|tokens|duration`:
  exit 1 unless current mean usage per attempt is at most `R` x baseline, in
  addition to the unchanged quality gate. A metric that is not recorded on every
  matched attempt, or a zero baseline, exits 2. EvalArc does not price tokens.
- The GitHub Action gains `max-cost-ratio` and `cost-metric` inputs and a
  `cost-ratio` output. `examples/model-upgrade/reports/comparison.json` is
  regenerated from the unchanged JUnit files to include the `usage` block.
- `eval-health` now points saturated evaluations to the cost gate.

### `evalarc eval-health`

- New offline command that reads 1–20 saved Inspect AI, promptfoo or JUnit
  result files of one evaluation and reports `saturated`, `always_failing`,
  `flaky_checks`, `unassessed_attempts`, `single_attempt`,
  `noise_exceeds_min_effect` (with `--min-effect`) and `capability_inversion`
  (with `--ordered`, files from weaker to stronger configuration). `--output`
  writes `health.json`, `summary.md`, `index.html` and input copies;
  `--require-healthy` exits 1 on any warning; invalid input exits 2.
  Documented in `docs/eval-health.md` and `docs/eval-health.zh-CN.md`.

### Sampling-noise annotation in `evalarc diff`

- Annotate each changed check with `within_sampling_noise` when both the
  baseline and current sides show observed variation and their 95% Wilson
  intervals overlap, so the recorded number of attempts (Inspect epochs,
  promptfoo repeats, repeated JUnit cases) cannot separate the change from
  repeat-sampling variation. `diff.json` gains a top-level
  `blocking_changes_within_sampling_noise` count and a `sampling_noise_note`.
- Surface the count in the CLI line, `summary.md`, and `index.html`, and mark
  flagged rows in both the Markdown and HTML change tables.
- The flag is descriptive, not a significance test: it never relaxes the gate.
  A flagged regression still exits 1, and a clean all-pass to all-fail swing is
  never called noise. It records whether the evidence is strong enough to trust
  the direction of a change and points reviewers to record more attempts, in
  the spirit of requiring a gain to exceed evaluation noise before acting on it.
  Uses the standard library only; no new runtime dependency.
- Regenerate `examples/model-upgrade/reports/comparison.{json,md}` and
  `index.html` from the unchanged committed JUnit files. Of the ten blocking
  checks, the five `resolved-bug` drops (3/3 → 1/3) are within sampling noise and
  the five `already-closed` drops (3/3 → 0/3) are not; the gate still fails.
  Document the annotation in `docs/ci-gate.md` and `docs/ci-gate.zh-CN.md`.

## 0.14.0 — 2026-09-25

### Results diff for existing evaluation tools

- Add `evalarc diff BASELINE CURRENT` for Inspect AI logs (JSON, or `.eval`
  on Python 3.14+), promptfoo `--output` JSON and JUnit XML. It pairs every
  case and check across all recorded attempts and exits 1 when a check
  regressed, became less reliable, became unassessed or was removed, even
  when the headline score improved. `--output` writes `diff.json`,
  `summary.md`, an offline `index.html` and hashed copies of both inputs;
  `--markdown` appends the summary to a file such as `$GITHUB_STEP_SUMMARY`.
- Add a composite GitHub Action (`action.yml`) that runs the diff, writes the
  job summary, annotates blocking checks and exposes `gate-passed`,
  `blocking-changes` and `report` outputs. CI exercises it on the recorded
  examples.
- Add recorded Inspect AI 0.3.268, promptfoo 0.123.1 and pytest 8.4.2 results
  under `examples/results-diff/`, with the commands that produced them.
  Previously `evalarc compare` accepted only EvalArc's own run format.

### Packaging

- Add a manually triggered workflow that republishes the verified GitHub
  release wheel and sdist to TestPyPI or PyPI through trusted publishing,
  after checking their digests against the release. It does not rebuild.
- Describe the package, add classifiers and keywords, and link the first-use
  guide and changelog from the project metadata.

## 0.13.1 — 2026-09-25

The `evalarc` package and its CLI are unchanged from 0.13.0; this release
publishes new experiment evidence, first-use documentation and stricter
publication checks. Existing 0.13.0 installations need no upgrade to review
the new records.

### Release checks

- Rerender the independent SWE report page, offline review page and methods
  when verifying the bundle. Previously a changed page with a resealed manifest
  still passed; it now fails the site build and dataset publication.
- Require the published SWE dataset methods to match the source methods, and
  verify the SWE report templates in the source distribution.
- Identify EvalArc as a command-line reviewer at the top of both READMEs and
  state that the release wheel is installed from GitHub, not PyPI. Update the
  citation metadata, which still named 0.7.1.

### Independent-source SWE review — 2026-09-20

- Publish all 36 Qwen3-8B attempts comparing four fixed workflows on three public
  SWE-bench Verified tasks. 31 have assessable native reports and five remain
  uncertain because of upstream infrastructure flags; none is accepted. Eight
  attempts produced nonempty patches.
- Retain actual MCP preloads, every failed operation, six native upstream defect
  and fix controls, and a complete offline archive. Publish the attempt rows as a
  separate Hugging Face dataset checked against the native records.
- Show how a declared 95% aggregate rule can accept an unresolved required
  defect. No general skill benefit is claimed.

### Publication verification — 2026-09-20

- Use up to four concurrent anonymous downloads when checking a published Space
  or dataset. Every file, including the manifest, must still match the uploaded
  bundle at its immutable Hub commit.
- Report verification progress and elapsed time without mixing logs into JSON
  receipts. A failed download or checksum cancels queued work and fails publication.
- Stream file checksums to bound memory use during large evidence downloads.

### First local review — 2026-09-20

- Update the English/Chinese installation paths to the released 0.13.0 wheel,
  including its verified SHA-256, so new users can run `behavior-review`.
- Recheck the first-review and AgentCore commands against their unchanged 0.12.1
  evidence snapshots with the 0.13.0 reviewer.
- Add a bilingual, source-free behavior-review walkthrough using the released
  archive: distinguish valid evidence, correct files, completed submissions and
  authorized behavior, including the expected rejection exit code.

### Pinned skill handoff — 2026-09-19

- Continue an explicitly selected public session with its original instruction and bundle hashes, using actual MCP preloads. Reject changed skill versions before starting a new provider session.
- Publish all six Qwen3-4B continuations with separate delivery, retrieval and task outcomes: six successful workflow preloads, six retrieved results, unchanged programs and 0/6 full acceptance. The report includes original receipts, independent grades and a complete offline archive.
- Bind future recorder invocations to their own source checkout. Preserve the recorded cohort’s during-run and post-run package observations with their original timing.
- Include both handoff evidence trees and report templates in source distributions, and verify their recorded bytes before publication.

## 0.13.0 — 2026-09-19

- Add a dedicated isolated runtime observer and read-only `behavior-review` CLI. Report file acceptance, service completion, authorization and evidence validity separately; retain temporary operations, rejected attempts, child-process accesses and incomplete requests.
- Publish 24 file/composition controls, eight service controls and all 12 fixed-source Qwen3-8B attempts with actual MCP deliveries on L40S. No model attempt completes the service submission; one has incomplete HTTP evidence. The model pilot does not establish a skill composition effect.
- Add a filterable report with source-line excerpts, original compressed traces and a complete offline archive. Recompute reviews, check recorded identities, and exercise desktop/mobile, keyboard, offline and installed-wheel paths.

## Strands browser review — 2026-09-16

- Add an install-free review of the native Strands example: filter regressions and improvements, inspect all eight expected/baseline/current state checks, and link to a check identified by both native report files.
- Publish a deterministic offline ZIP containing the complete page, native reports, original EvalArc inputs and file checksums. All evidence remains readable without JavaScript.
- Recheck the displayed native rules against original state during the site build. Keep the native two-rule mean distinct from EvalArc's five-dimension weighted score. This presentation update leaves the Python release at 0.12.1.

## Strands Evals companion example — 2026-09-16

- Recheck notes and closure in four saved Docker cases using Strands Evals 1.3.0 and native environment-state/report APIs. Preserve case/evaluator identities and expose the notes regression despite an improved two-rule mean.
- Keep the optional dependency environment and native reports separate from EvalArc's core and original five-dimension scoring. Add English/Chinese instructions and CI that rejects network attempts, verifies saved results and checks report inventories.
- This example does not execute an agent, run a model or import arbitrary cloud reports. The Python release remains 0.12.1.

## Website and first-use documentation — 2026-09-16

- Lead the English/Chinese README and evidence lab with the recorded regression, with a 30-second annotated UI walkthrough and a direct path to local review.
- Document a source-free install from the released 0.12.1 wheel, recomputation of the comparison and suite acceptance checks, and the bounded AgentCore export workflow.
- Add a first-use feedback form and replace historical version stacks in the HF card and outreach descriptions. This is a presentation and onboarding update; the Python version and released evidence remain unchanged.

## 0.12.1 — 2026-09-16

- Request attachment disposition for judge, suite and research ZIP links with `download=true`. Hugging Face's inline CDN redirects prevented the new ZIP link from triggering a download inside the Hub iframe; the attachment query was verified in the live browser.
- Apply the research-link change only to published presentation HTML and its manifest. Original archives, judgments and metric calculations remain unchanged.
- Add a deployment check in the actual Hub iframe on desktop and mobile: compare the published source commit, download all three archives and an original judgment, verify their bytes and exercise the report filters.

## 0.12.0 — 2026-09-16

- Add offline `trace-stability` and `trace-stability-verify` for repeated saved judgments of one fixed recording. Reject changed execution/configuration/rubrics and duplicate repetition IDs.
- Keep score variation, observed pass/reject disagreement, missing assessments and not-applicable skill targets distinct. Agreement gates do not require task acceptance; all-reject results remain visible.
- Add an interactive homepage matrix, standalone filtered report, preserved-input downloads and deterministic evidence ZIP. Five synthetic controls cover three judgment sets; no new model or AWS evaluation is claimed.
- Extend installed-wheel and desktop/mobile/offline checks. Correct stale casebook counts to the existing 251 audit rows; original research and audit records are unchanged.

## 0.11.1 — 2026-09-15

- Use explicit HTML filenames for published lab navigation. Hugging Face redirects bare directory paths to Hub routes rather than serving each directory index. Cover homepage entries and research/skill-lab return links.
- Reseal only the published lab presentation files; recorded trials, raw JSON and original research archives stay byte-identical. Test navigation with a static server that rejects implicit directory indexes.

## 0.11.0 — 2026-09-15

- Add offline AgentCore Evaluate import, golden-case/rubric comparison and recomputable trace review with responsive standalone reports.
- Keep valid zero, skipped/error, missing results, missed skills and changed bundle identities distinct.
- Publish five synthetic controls and one actual local stdio MCP delivery with no evaluator scores. Imported judgments and caller-declared coverage are separate from independent task verification.
- Update stale Harbor/architecture descriptions and derive homepage task/fault counts from the saved audits.

## 0.10.2 — 2026-09-15

- Bind evidence explorer links to SHA-256 of the actual loaded audit bytes. A changed recording with the same case coordinates no longer reports the original evidence as restored. Display the loaded fingerprint and distinguish content identity from authorship.
- Keep legacy links readable with an explicit missing-identity notice; reject duplicate parameters and preserve report/download access when browser hashing is unavailable. Test changed bytes under an unchanged manifest, fresh links, retry, mobile layouts and clipboard fallback.
- Task contracts, metric calculations and historical audit records are unchanged.

## 0.10.1 — 2026-09-15

- Add a reduced-suite regression that removes `cas-type-sensitivity` from `durable-kv` at seed 17: `boolean-equals-one` survives, the recomputed audit reports 7 of 8 at 0.875, and the weakest margin is 0. The published 0.10.0 wheel already produces these values and includes surviving valid controls in the weakest margin. This release adds the regression and clarifies the explanation; it does not change the metric calculation.
- Correct the explanation of what a margin means, in the code comments, the methodology, both READMEs and the outreach record. Removing a sole detector does not preserve a mutation score of 1.0: a recomputed audit exposes the regression, and only a stale report would still say 1.0. What a perfect score hides is the fragility before a change, not the regression after one.

## 0.10.0 — 2026-09-14

- Add a three-task audit coverage section with direct links from single-case dependencies to recorded fault evidence. Re-render all three reports from unchanged saved JSON, with accessible disclosures and layouts for narrow screens.
- Include assessed surviving faults as zero in the weakest detection margin; environment failures remain unassessed.
- Extend the Hugging Face casebook to all three task packs: 251 case rows, with the parent control's distinct-case detection margin. Preserve the original source records and distinguish reference controls with a null margin.

- Report detection margins beside the mutation score: how many cases caught each declared fault, the weakest margin in the pack, the faults caught by exactly one case, and the cases that are the sole detector of some fault. All three packs score 1.0, and six of their 21 declared faults rest on a single case each; that fragility was previously invisible.
- Count margins over distinct cases rather than case runs, so adding a seed cannot inflate them. Measured margins are identical under the Python and JavaScript references.
- State the relation to the hack-verifiable environments methodology and record both papers as verified primary sources. HVE plants a hack in the environment to measure whether an agent exploits it; an audit here plants a fault in the submission to measure whether the checks catch it. Opposite directions, no equivalence claimed.
- Correct the task-pack count and table in both READMEs: robot-evidence-review shipped in 0.9.0 but was described as if only two packs existed, and the JavaScript reference was said to cover 15 faults rather than 21.

## 0.9.0 — 2026-09-14

- Add the robot-evidence-review task: attributed CUDA source data, coordinate/clock transformations, missing observations, Python/JavaScript references and six independent fault controls.
- Separate trusted Docker startup readiness from candidate response timing. Keep startup and total-case bounds and distinguish environment failure from candidate failure.
- Import Harbor results while independently grading candidate code; export recorded trials to ATIF 1.8. Native Harbor oracle/NOP checks and upstream ATIF validation accompany the examples.
- Publish 27 actual Qwen3-8B trials with every candidate, MCP receipt and independent outcome. Add controlled skill-composition/output auditing and a Funes cross-model handoff pilot. These public development pilots do not establish skill or memory efficacy.
- Add a non-networked, non-root agent workspace and bounded file/tool operations for reproducible model pilots.


## 0.8.0 · 2026-09-14 · Research preview

- Verify whole suite handoffs from the original TOML, plan, every repetition and
  attempt, recomputed custom gates and JUnit failure/error records.
- Add `--require-accepted` for configured suite gates, distinct from record
  consistency and full task resolution. Original candidate paths and timings
  remain reported metadata; no candidate or grader is executed.
- Download the featured suite as a deterministic ZIP from the evidence lab.
  Preserve all 12 original input files and verify the extracted archive offline.
- Check received suites from the installed wheel outside the checkout with an
  empty PATH, including rejection of a modified JUnit record.

Task contracts, scoring rules and historical evidence bytes are unchanged.


## 0.7.1 · 2026-09-14 · Research preview

- Share and restore a specific task pack, control, seed, case and trace step in
  the evidence explorer, including a selectable link when clipboard access is
  denied. Out-of-range links show an explicit fallback.
- Retry failed suite, repetition, comparison or task-pack requests independently.
  Bound network waits and keep a successfully loaded task pack usable when the
  other fails; retrying can restore the originally linked evidence.
- Add section navigation, case-detail focus and return controls, keyboard-readable
  JSON panels, larger buttons and readable mobile evidence text.
- Render the site's preview version from package metadata.

Original reports, task contracts, scoring and CLI behavior are unchanged.

## 0.7.0 · 2026-09-14 · Research preview

- Add `evalarc verify` for received evaluation, repetition and comparison
  records. Recompute summaries and source identities without candidate
  execution, a source checkout, Docker or the original interpreter.
- Return machine-readable results and hashes of every checked JSON input.
  Separate consistency success from `--require-resolved` acceptance.
- Bound input sizes and attempt inventory; reject duplicate keys, non-finite
  numbers, symlinks and special files. Keep historical evidence readable.
- Document unsupported aggregate formats and the distinction between record
  consistency, independent grader execution and producer authentication.

Task contracts, runtime enforcement and scoring rules are unchanged. This
release verifies existing evidence; it does not add new model trials.


## 0.6.0 · 2026-09-14 · Research preview

- `init --language python|javascript` supplies starters and references for both
  tasks. JavaScript workspaces include a portable command manifest, the complete
  task contract, and runtime guidance; Python remains the default.
- An independent Node.js durable service preserves numeric source text, integer
  precision, float/integer distinctions, signed floating zero, nested values,
  and unordered object equality. A complete snapshot precedes write acknowledgement.
- `audit --language javascript` exercises the same eight coding and seven
  simulated-ticket fault models. Local audits resolve Node from the host PATH;
  Docker image selection remains explicit.
- Workspace initialization stages complete files before publishing and removes
  partial output after failures. Existing files and directories remain protected.
- Protocol tests cover values beyond the public task cases, SIGKILL recovery,
  invalid batches, special keys, failed persistence, and corrupt snapshots.
- Docker CI audits now cover both languages and both tasks. The Python package
  includes all JavaScript templates without adding a Python runtime dependency.

Task contracts, grading/runtime source files, and evidence schemas are unchanged.
Comparisons still require matching recorded commands, runtime, grader, and cases;
different-language executions do not become a matched comparison automatically.
No TypeScript SDK, Rust worker, or model-provider adapter is introduced.

## 0.5.0 · 2026-09-14 · Research preview

- `evalarc suite` executes versioned TOML plans across multiple candidates and
  built-in tasks, with per-job seeds, repetitions, runtime limits, and gates.
- `--dry-run` validates configuration and previews workload without starting
  candidates or contacting Docker.
- Every candidate is snapshotted and preflighted before the first job runs.
  Candidate paths resolve relative to the configuration file.
- Gates default to full resolution. Optional score/rate thresholds and required
  dimensions expose partial acceptance without hiding unresolved outcomes.
- Reports preserve individual attempts and task scores, with no cross-domain
  average. JUnit exports one test per gate, separating failures from environment
  errors; other jobs still run after a recorded invalid evaluation.
- Local execution still needs explicit CLI trust. Existing outputs remain
  protected; JSONL progress includes job identity.
- The browser compares permissive and notes-protecting gates applied to the
  same frozen faulty policy. The three-job, five-attempt Docker suite includes
  original TOML, JUnit and every report. Site builds recompute gate decisions
  from the configuration and attempt evidence and verify the JUnit export.

Task contracts, scoring code, runtime enforcement, and evaluation/repetition
schemas are unchanged from v0.4. Matching v0.4/v0.5 evaluations remain comparable.
No new model-provider or browser-agent integration is claimed.

## 0.4.0 · 2026-09-14 · Research preview

- `evalarc repeat` freezes one candidate across fresh attempts, preserves every
  evaluation, and reports case/check pass rates and varying outcomes.
- Invalid attempts and incomplete runs remain explicit; repetition stops after
  the first invalid evaluation. No best-attempt selection or statistical
  population estimate is provided.
- A 60-second default case budget spans protocol exchanges and process restarts,
  alongside the existing per-response timeout.
- Evaluations, audits, and repetitions save host-generated `events.jsonl`;
  `--progress` streams those events to stderr.
- Case evidence includes bounded process diagnostics. Cleanup exceptions still
  release local processes and pipes where possible, and preserve cancellation.
- Bilingual guidance, fresh Docker audits, and a three-attempt scripted
  repetition example accompany the release.
- The browser now exposes six actual Docker attempts across the reference and
  duplicate-write control, per-check counts, every attempt report, and progress
  downloads. Site builds recompute repetition summaries from all attempt records.

Both task contracts remain v0.1.0 and evaluation schema v2 remains readable.
Runtime metadata and grading fingerprints change: re-run candidates under
matching v0.4 conditions before comparing them. The earlier comparison and audit
explorers retain their historical records alongside the new v0.4 repetitions.

## 0.3.0 · 2026-09-14 · Research preview

- `evalarc doctor` checks runtime readiness and candidate configuration without
  executing a candidate.
- Every evaluation now includes a standalone HTML report and its complete JSON.
- `evalarc compare` validates matching records and reports each regressed check,
  including when improvements elsewhere raise the aggregate score.
- CLI outputs use fresh directories and staged publication to preserve earlier
  evidence.
- The evidence lab adds a comparison from 90% to 93.75% with one regressed note
  check and two improved closure checks, plus the downloadable input records.

The task contracts and grading fingerprints are unchanged. Comparisons check
recorded consistency and matched conditions; they do not authenticate the
producer, establish statistical significance, or imply full task resolution.

## 0.2.0 · 2026-09-14 · Research preview

First public EvalArc release.

- Two executable task packs: `durable-kv` for coding artifacts and
  `support-routing` for simulated tool policies.
- Fifteen declared negative controls, known-good references, and recorded
  Docker audits with reproduction metadata.
- Configurable candidate commands, including an independent JavaScript
  support policy using the same host verifier.
- Interactive evidence explorer on GitHub Pages and Hugging Face: compare
  implementations, inspect failures, and step through tool state changes.
- Python 3.11–3.13 CI, Docker audits, desktop/mobile browser checks, and
  verification of the published Hugging Face bundle.

The recorded examples are scripted controls and public development tasks.
No frontier-model ranking, arbitrary reward-hack resistance, human time
horizon or RL training gain is established.

## Local prototype history

The initial GradeRail prototype supplied the durable key-value task. It was
renamed to EvalArc before public release. Support routing and configurable
commands were added during the local 0.2 development cycle. Earlier local
archives are not separate public releases.

## 0.16.1 — 2026-09-29

- fix: fail the diff gate when a check has fewer assessed attempts than the baseline. evalarc diff now fails the gate when a check has fewer assessed attempts in the current run than in the baseline. The new blocking kind is less_covered. A smaller sample can no longer come out as improved or unchanged: 2/2 to 1/1, 1/2 to 1/1, and 2/2 to 1/1 with one unassessed attempt are all less_covered and exit 1. The existing kinds keep precedence. A lower pass rate is still reported as regressed or less_reliable, and a check that passed before and has zero assessed attempts now is still unassessed. The CLI takes its list of blocking kinds from BLOCKING, so it prints ' less_covered: <case> / <check>'. diff.json lists less_covered in counts and changes. summary.md and index.html show a 'less covered' row, marked as failed, with the baseline and current fractions. Comparisons with equal or greater coverage give the same results as before.

## 0.16.0 — 2026-09-28

- review held-out error versus coverage for recorded choice decisions at an abstention threshold. EvalArc has a new offline command, evalarc decision-coverage. It reads one evalarc.decision-records.v1 file of labelled choice decisions, split into calibration and held_out records, each with a probability distribution or a recorded error. It reports held-out error versus coverage at an abstention threshold. Confidence is the largest probability, and ties go to the option declared first. The command tries every distinct calibration confidence plus the baseline t=0. With --max-error E, it picks the smallest threshold whose calibration error is at or below E, using calibration data only, and checks it on held-out data. The result is one of four states: met (exit 0), exceeded, no_threshold or no_heldout_answers (exit 1). Without a target the state is no_target (exit 0), and records are classified at t=0. Malformed responses become invalid rows with a stated reason. They are never counted as wrong but lower coverage. Malformed files exit 2 and write nothing. The new output directory holds a byte-identical input copy with its sha256, a decisions.json with the full sweep, and an escaped, self-contained index.html.

## 0.15.0 — 2026-09-25

- Publish a reproducible Qwen3-8B BF16 / Qwen3.8-27B FP8 configuration comparison with fresh generations, native pytest/JUnit checks and every original answer.
- Add an offline model-upgrade review with case and seed selection, explicit scope, pinned inputs and strict checkpoint-loading diagnostics.
- Retain the mixed result: complete plans match in 15/24 baseline and 19/24 current answers, while ten dependent named checks lose passes and block the upgrade gate.
- Regrade the preserved answers without a model call; retain native JUnit outcomes and declare hostname/report-directory redactions with before/after digests.

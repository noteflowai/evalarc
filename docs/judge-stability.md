# Same recording, repeated judgments

EvalArc 0.12 adds an offline diagnostic for saved **judge repetitions**. It
answers a bounded question: when the supplied execution record and declared
evaluator configuration stay fixed, do the imported values and acceptance
decisions agree? [中文说明](judge-stability.zh-CN.md)

This is separate from `evalarc repeat`, which executes a frozen candidate in
fresh task state. Do not combine agent execution variance and judge disagreement
in one success rate.

```sh
evalarc trace-stability \
  examples/judge-stability/judge-1.json \
  examples/judge-stability/judge-2.json \
  examples/judge-stability/judge-3.json \
  --output runs/judge-review
evalarc trace-stability-verify runs/judge-review
```

Open `runs/judge-review/index.html`. The report is self-contained and works
offline; filter disagreements or incomplete targets, inspect every original
value, and download the preserved inputs. The
[live demonstration](https://noteflowai.github.io/evalarc/judge-stability/index.html)
uses five **synthetic** controls and three authored judgment sets. No model or
AWS evaluation was performed for these controls.

## Collect your own judgments

Each input follows the [Trace Workbench contract](trace-workbench.md):

1. Capture one complete execution record and freeze its dataset, model/prompt/
   tool/skill configuration, sessions, trace/span objects, skill receipts and
   coverage declarations.
2. Re-evaluate that same saved record with the same evaluator configuration.
   Record judge model identity, prompt/configuration and collection details in
   each evaluator's `revision` or additional evaluator fields. Those fields are
   compared exactly. A built-in name alone does not freeze a service version.
3. Save each evaluation as its own trace input with a distinct `run_id`.
   In this command it identifies a **judge repetition**, not a new execution.
   Only `run_id`, `provenance.description` and each case's
   `evaluation_response` may differ. Other provenance metadata is frozen.
4. Preserve the native Evaluate API results in `evaluation_response`, then run
   the command locally. Existing result linkage and rating validation still
   applies. A different recording, configuration or rubric is rejected.

Distinct caller-supplied run IDs are required, but cannot prove separate service
calls or statistical independence. The tool cannot inspect the actual internal
judge configuration, authenticate a producer or establish complete collection.

## Read the results

Every case/evaluator/target has its own observations and denominator. Numeric
zero remains assessed; skipped, missing, error and unassessed judgments remain
unassessed. No scores are averaged across targets or rating scales.

- **Score variation:** at least two assessed numeric values or categorical
  labels differ. For numeric ratings, display the observed values; for
  categorical ratings, compare labels without assigning numeric distances.
- **Gate disagreement:** at least one assessed pass and one assessed rejection.
  It can be observed even with missing repetitions; the report retains both
  findings. The disagreement filter includes such incomplete targets.
- **Same observed gate:** all expected judgments are assessed with no pass/
  reject disagreement. This includes all-reject results. It says nothing about
  future stability or whether the judgments are correct.
- **Incomplete:** at least one expected judgment was not assessed. Zero assessed
  judgments is incomplete, not perfect agreement.
- **Not applicable:** no skill target exists under declared complete coverage.
  These rows are shown but excluded from the coverage denominator.

The overall case gates from each input are retained separately. For example,
judges may all pass while changed skill content makes the case fail acceptance.

Import normally exits 0 for valid data. Add `--require-consistent-gates` to use:

| Exit | Meaning |
| --- | --- |
| 0 | Every required judgment assessed, no observed pass/reject disagreement |
| 1 | Complete judgments with at least one gate disagreement |
| 2 | Incomplete judgments or invalid input |

**This gate does not require task acceptance.** All-reject agreement exits 0;
score changes that stay on the same side of the configured threshold also exit
0. Apply task acceptance using the existing trace/suite gates separately.
For valid data, the report is written before returning a nonzero gate exit.

## Evidence and limits

The report stores each original file byte-for-byte, with hashes and a canonical
identity of the frozen recording. `trace-stability-verify` recomputes all
observations and summaries and rejects mismatches, extra inputs and symlinked
evidence paths. It does not verify HTML, rerun a judge or authenticate who
produced the files. Replacing both inputs and their report is not detected as
forgery without an independently trusted digest.

Limits: 2–20 judgment sets, 4 MiB per input, 16 MiB total input and 32 MiB
canonical report; the Trace Workbench case/span/evaluator bounds also apply.
Output must be a new directory. Nothing is uploaded or executed.

This is descriptive diagnosis, not calibration against human ground truth,
confidence intervals, a ranking or a reproduction of a research benchmark.
Independent calibration sets, live AWS collections and customer PAI
integrations remain future work.

## Research context

The ICML 2026 paper
[Towards a Science of AI Agent Reliability](https://icml.cc/virtual/2026/poster/66364)
separates consistency, robustness, predictability and safety instead of relying
on a single accuracy number. That broader agent-reliability framework motivates
keeping the dimensions separate; this small judge diagnostic does not implement
the paper's twelve metrics.

[AgentCore Evaluations documentation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/evaluations.html)
describes trace-based LLM-as-a-Judge evaluation. This tool analyzes saved
API-shaped results under the documented local contract; it does not invoke
AgentCore or certify compatibility with every collection wrapper.

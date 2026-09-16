# Trace Workbench

`trace-import` turns a bounded export into a local, filterable report. It checks
case/session/trace/span linkage, applies explicitly supplied evaluator scales,
matches Skills Anywhere delivery receipts to reviewed bundle hashes, and keeps
missing results distinct from assessed zero scores.

This is **review of imported judgments**, separate from EvalArc's independent
executable task graders. The importer does not call AWS, run a model, authenticate
the producer or prove that the supplied traces cover every action.

## Start with the authored controls

```bash
evalarc trace-import examples/trace-workbench/current.json \
  --baseline examples/trace-workbench/baseline.json \
  --output runs/trace-review-001
evalarc trace-verify runs/trace-review-001
```

Open `runs/trace-review-001/index.html` directly, including offline. All rendering
and filtering are local. The folder includes exact original input bytes,
optional baseline bytes and a recomputable `review.json`.

The five **synthetic** controls demonstrate an accepted case, assessed zero,
skipped evaluation, missing result and missed required skill. Their placeholder
hashes and authored scores are not cloud/model measurements.

## Prepare a real export

Use the example JSON as the wrapper. Fill in:

| Field | Contract |
| --- | --- |
| `schema_version` | `evalarc.trace-input.v1` |
| `run_id` | Your run identity; one attempt per input |
| `provenance` | `kind: recorded` and a description of collection method and limitations |
| `dataset` | Stable ID, version and ordered cases: `id`, `goal`, `expected_skills` |
| `configuration` | Model identity/parameters, prompt and tool-schema SHA-256, `skills` mapping names to reviewed bundle SHA-256 (or `null` when unknown) |
| `evaluators` | IDs, frozen revision descriptions, target `level`, and explicitly declared rating/gate rules |
| `cases` | Exactly one recording per golden case, in the same order |

A case contains `case_id`, `session_id`, `trace_ids`, `spans`,
`skill_observation_complete`, `skill_calls` and `evaluation_response`.

Copy flat OpenTelemetry spans with `traceId` and `spanId` into `spans`.
Attributes may be a plain object or OTLP key/value array. When `session.id` is
present it must match the case. Every declared trace must have a span. This first
adapter accepts a flat span array, not arbitrary OTLP envelopes or CloudWatch
query output wrappers; extract the native span objects first.

Copy the native AgentCore **Evaluate API** response into `evaluation_response`.
Preserve `evaluationResults` and original fields. Result targets use
`context.spanContext.sessionId`, with `traceId` and `spanId` according to level.
The Workshop CLI's `run.results[].sessionScores` output is a different envelope
and is not accepted by this adapter.

- `session`: one result for this case's session; no trace/span target.
- `trace`: one result for each declared trace; no span target.
- `skill`: one result for each explicitly annotated skill call's trace/span.
  This level intentionally covers skill calls, not arbitrary tool-call evaluators.
- Declare at least one session evaluator so every golden case has an expected
  result even when no skill was called.

Numeric ratings declare `min`, `max`, `pass_at_least`; categorical ratings
declare `labels` and `pass_labels`. Never infer a scale or freeze a built-in
evaluator version from its name alone. Record the configuration and collection
date actually used; the revision field is caller-supplied metadata.

Unknown IDs, duplicate evaluator/target results, wrong sessions and out-of-range
ratings are rejected. Numeric zero is assessed. Error and skipped results are
unassessed even if they carry a raw number; that number remains in `input.json`.
`Skipped` in `errorCode`, or in a label outside a declared categorical scale, is
recognized; this is not a promise that every service uses that spelling.
Other errors retain their code. Empty responses produce missing expected results.

## Associate an actual skill load

Skills Anywhere 0.12+ returns `structuredContent.receipt` from successful
`open_skill` calls. Your collector should preserve the response and annotate its
actual tool span:

```json
{
  "name": "evidence-review",
  "trace_id": "YOUR_TRACE_ID",
  "span_id": "YOUR_TOOL_SPAN_ID",
  "receipt": {"schema": "skills-anywhere-load-1", "...": "copy the complete receipt"}
}
```

The snippet is schematic; use the complete returned object. The receipt's
`bundle_sha256` is available when `include_bundle: true` or
`expected_bundle_sha256` is requested. The wrapper's `configuration.skills` must
contain the bundle hashes reviewed before the run.

This annotation is explicit: the importer does not guess skill names from
arbitrary tool arguments. Set `skill_observation_complete: true` only if your
collector observed all skill loads for the case. Absent required calls are
`not_called` only with declared complete coverage; otherwise they remain
unknown. A matching receipt identifies delivered content, not followed
instructions or completed work. Multiple loads need distinct receipt IDs.

## Compare and verify

For repeated judgments on one fixed recording, use the separate
[Judge Stability diagnostic](judge-stability.md). It requires frozen execution
and evaluator definitions; a new Agent execution is not a judge repetition.

Comparison requires identical complete golden-set contents and evaluator
definitions, including revision and rating rules. It shows configuration changes
and case transitions without pooling evaluator scores or claiming causal gains.
Synthetic and recorded inputs cannot be compared with each other.

`trace-verify` reconstructs the review from preserved bytes and compares all
fields. It detects changed input or summary bytes, but does not authenticate a
producer or verify HTML. It does not execute any imported content.

By default successful import exits 0 even when gates reject cases. Add
`--require-accepted` for CI: 0 = every case accepted, 1 = complete results with
rejected gates, 2 = incomplete results or invalid input. The complete report is
still written for well-formed input with a rejected/incomplete gate.

## Scope and sources

Inputs are bounded to 4 MiB, 200 cases, 512 spans per case, and 32 evaluators.
Duplicate JSON keys, nonfinite numbers and invalid Unicode are rejected. Existing
output folders are preserved. There is no browser file upload, automatic
collection, cloud deployment, judge calibration or statistical significance
calculation in this first release. Review private trace content before sharing.

- [AgentCore Evaluate API](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_Evaluate.html)
- [Evaluation result fields](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_EvaluationResultContent.html)
- [Skill evaluators](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/skill-evaluators.html)
- [Eval-First Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/bdb5c2fd-86cc-4a86-b55f-fbc2a81c001a/zh-CN/010-introduction)

The AWS adapter has been tested against authored API-shaped controls. The
separate MCP recording exercises actual local instruction delivery with missing
evaluator results; no successful live AgentCore evaluation is claimed.

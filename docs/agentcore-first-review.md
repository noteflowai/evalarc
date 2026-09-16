# From an AgentCore export to a local review

This walkthrough connects EvalArc's existing `trace-import` command to your
review process. It starts with published controls, then explains which pieces
to replace with actual records. It does not deploy a cloud agent or collect
AWS data for you.

**Validation scope:** the first half is reproducible with the released 0.12.1
wheel. The five scored controls are synthetic API-shaped inputs. A separate
record contains actual local MCP delivery and no evaluator scores. A live
AgentCore or Strands evaluation has not been validated by these examples.

## Inspect a complete input before collecting data

After [installing the wheel](first-review.md#2-install-the-reviewer), run
these commands in a fresh directory:

```bash
curl --fail --location \
  https://github.com/noteflowai/evalarc/releases/download/v0.12.1/trace-workbench-evidence.zip \
  --output trace-workbench-evidence.zip
python -m zipfile -e trace-workbench-evidence.zip .
evalarc trace-import trace-workbench/input.json \
  --baseline trace-workbench/baseline-input.json \
  --output my-trace-review
evalarc trace-verify my-trace-review
```

Both commands exit **0** for a valid import and consistent evidence. That does
not mean every case was accepted. Open `my-trace-review/index.html` to see the
accepted, zero-scored, skipped, missing-result and missing-skill controls.
The ZIP SHA-256 is
`2e8ea5ba062167e8de5420400e60837a1aae68e465b5cfdf5337686d6fe2be3f`.

The copied `my-trace-review/input.json` and `baseline-input.json` preserve the
original bytes; `review.json` contains the derived review. The report and
filters work offline.

## Replace authored inputs with a recorded export

Use `trace-workbench/input.json` as a structural example. Create your own
wrapper rather than relabeling the demonstration as a real run:

1. Record the golden set, ordered case IDs, intended goals and required skills.
   Set `provenance.kind` to `recorded` and describe how the data was collected
   and what the collection omits.
2. Copy each case's native **AgentCore Evaluate API** `evaluationResults` into
   `evaluation_response`. Keep the service's original fields and matching
   session/trace/span identifiers.
3. Supply a flat array of corresponding OpenTelemetry spans. Extract spans
   from any transport envelope first; arbitrary OTLP envelopes and CloudWatch
   query wrappers are not accepted directly.
4. Explicitly declare the evaluator's target level, revision, rating scale
   and acceptance rule. Keep model/configuration identity and hashes where
   required. An evaluator name does not establish its scale or version.
5. If using Skills Anywhere, preserve actual `open_skill` receipts and
   annotate the matching tool spans. Only assert complete skill observation
   when your collector actually observed all loads.

The AWS workshop CLI's `run.results[].sessionScores` is a different envelope.
Renaming that field is not a conversion. Strands traces alone also do not
provide the required golden cases and judgments. See the
[full input contract](trace-workbench.md#prepare-a-real-export) before adapting
an exporter.

## Review, compare, then gate

```bash
evalarc trace-import recorded-current.json --output recorded-review
evalarc trace-verify recorded-review
```

For a baseline comparison, add `--baseline recorded-baseline.json`. Both
inputs must use the same complete golden set and evaluator definitions;
synthetic inputs cannot be compared with recorded inputs.

Add `--require-accepted` to **trace-import** when a CI step should enforce the
rules. Its exit codes distinguish **0** (every case accepted), **1** (complete
assessments with rejected gates), and **2** (incomplete assessments or invalid
input). A well-formed input still produces its report when a gate rejects or
a judgment is missing. `trace-verify` checks consistency; it is not the gate.

If importing fails, start with the named case/evaluator in the diagnostic.
Check linkage, duplicate targets, explicit scale bounds and expected-result
coverage. A missing or skipped evaluation must not be filled with a fabricated
zero to make the file pass validation.

## Bring back one useful finding

Use the [first-use form](https://github.com/noteflowai/evalarc/issues/new?template=first-use.yml)
to report the exporter/envelope you used, the command and the first point of
friction. A small redacted fixture helps establish whether an adapter is
useful. Do not attach production traces merely to demonstrate interest.

Sources and collection boundaries are documented in the
[Trace Workbench guide](trace-workbench.md#scope-and-sources). EvalArc reviews
imported judgments; it does not independently establish their truth or the
completeness of the supplied execution record.

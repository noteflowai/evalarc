# Equal-length context controls

Twelve recorded Qwen3-8B attempts are published in two separate cohorts. Each pairs relevant robot-recording guidance with unrelated prose at model seeds 17, 41 and 97. Both actual MCP skill-load payloads contain 476 tokens under the pinned Qwen tokenizer, including file and bundle hashes. The payloads share their advertised name and description. Their instruction bodies differ; the unrelated text includes a descriptive sentence that it contains no programming instructions. Inspect the exact text before interpreting the control.

## What was observed

| Cohort | Relevant guidance | Unrelated prose | Fully resolved tasks |
| --- | --- | --- | --- |
| Initial EOF example | Three programs scored 0% | Three programs scored 0% | 0 / 6 |
| Persistent-request follow-up | Three programs scored 87.5% | Three unchanged starter programs scored 0% | 0 / 6 |

All 48 initial cases timed out before receiving a JSON response. The programs buffered stdout; closing stdin in the public example allowed buffered output to appear. A separately executed reference passed under the same Docker image and grader. An unchanged-program diagnostic reproduced the timeout for neutral/02-mcp-17 and received a response when Python -u was added. That single-request diagnostic does not establish that every case or candidate would pass after a transport change.

The follow-up gives both conditions the same public protocol_probe.py and an instruction to flush each response. The probe sends two requests without closing stdin, uses the same Python -I -B launch style as the grader, and checks finite JSON responses. It does not grade numerical correctness. Its three-second response check is a development diagnostic; the independent grader allows ten seconds. The helper is writable in the candidate workspace and its apparent success is never accepted as final task evidence.

All three relevant follow-up programs return JSON but fail the metrics check in the millimetre/sensor-frame and centimetre/offset-clock cases, at both evaluation seeds. All three unrelated-text attempts list and load the skill, then call finish without writing main.py. Complete tool calls, programs and original independent grading remain inspectable. A finish signal, partial score and full task resolution are distinct outcomes.

The follow-up was designed after observing the initial failures. Both plans were saved before their own inference, with all six scheduled attempts retained and no retries. The cohorts have different initial instructions and workspace helpers, so their outcomes are not pooled. Neither cohort is a held-out test, an independent-author evaluation, a general efficacy estimate or a model ranking. The earlier 27-trial pilot uses its own recorded engineering profiles and is separate from these twelve attempts.

## Inspect without model access

From an EvalArc source checkout matching the deployed site's manifest:

```bash
PYTHONPATH=src:. python3 -m scripts.build_context_collection \
  --verify --output examples/context-controls
```

This checks both cohorts, actual skill delivery, the saved initial prompts, token-usage sums, independent evaluations, collected-program hashes, rendered pages and every archived byte. It uses the Python standard library and EvalArc source; it does not execute candidates or call a model. Hash consistency is not producer authentication.

The browser pages contain no executable model code and work from saved records. Each case can be expanded without JavaScript. The complete ZIP includes both cohorts and their individual ZIPs. All model weights remain external.

## Recompute the token count

Use a separate environment with Transformers 5.5.4 and the local tokenizer snapshot from Qwen/Qwen3-8B revision b968826d9c46dd6066d109eabc6255188de91218. Model weights are not needed for this check; preparation/match.json names the tokenizer files and their required hashes.

```bash
PYTHONPATH=src:. python3 scripts/check_context_tokens.py \
  --source examples/context-controls/initial --tokenizer /path/to/pinned-tokenizer
PYTHONPATH=src:. python3 scripts/check_context_tokens.py \
  --source examples/context-controls/protocol --tokenizer /path/to/pinned-tokenizer
```

This invokes the native tokenizer locally and compares all token IDs with the stored receipt. The ordinary bundle verifier checks receipt consistency but does not implement a tokenizer. Both checks concern the JSON tool-result payload, not the whole conversation: subsequent instructions, tool calls, generated programs and total token usage can differ.

## Repeat a recorded cohort

Work in a separate checkout and a fresh output directory. Each cohort's dependencies/source.json identifies the EvalArc checkout base and Skills Anywhere source. Restore the archived record_skill_impact.py, record_context_controls.py and local_model_server.py from its harness/ into that checkout's scripts/; the protocol cohort also requires its archived protocol_probe.py. The original harness snapshots remain byte-for-byte evidence. Do not silently substitute a newer harness and call the result a replay.

The model environment used Qwen3-8B at the revision above, bfloat16 on an NVIDIA L40S, PyTorch 2.11.0+cu130, Transformers 5.5.4 and thinking disabled. Model file identities are in model-files.json. Use a compatible isolated CUDA environment and the pinned local snapshot to repeat inference. Environment annotations collected after execution are labelled separately in dependencies/source.json.

Reconstruct the archived Node provider before starting inference (requires Node and the pnpm version declared in package.json):

```bash
export EVALARC_CONTEXT_EVIDENCE=/absolute/path/to/selected/cohort
export EVALARC_CONTEXT_PROVIDER=/absolute/path/to/new/provider-directory
mkdir -p "$EVALARC_CONTEXT_PROVIDER/examples/skill-impact"
cp "$EVALARC_CONTEXT_EVIDENCE/harness/bridge.mjs" \
  "$EVALARC_CONTEXT_PROVIDER/examples/skill-impact/bridge.mjs"
cp -R "$EVALARC_CONTEXT_EVIDENCE/skill-library" "$EVALARC_CONTEXT_PROVIDER/lib"
cp "$EVALARC_CONTEXT_EVIDENCE/dependencies/package.json" "$EVALARC_CONTEXT_PROVIDER/"
cp "$EVALARC_CONTEXT_EVIDENCE/dependencies/pnpm-lock.yaml" "$EVALARC_CONTEXT_PROVIDER/"
pnpm --dir "$EVALARC_CONTEXT_PROVIDER" install --frozen-lockfile --ignore-scripts
```

Use the copied 0.12.0 library directly; do not rebuild it during this replay. The archived lock matches the installed dependency lock used for the follow-up. The provider receives only the selected public skill pool, with unrelated directory discovery and synchronization disabled by the bridge.

Start the model service in the restored EvalArc checkout with the matching GPU environment:

```bash
PYTHONPATH=src:. python3 scripts/local_model_server.py \
  --model /path/to/pinned-model --model-id Qwen/Qwen3-8B \
  --revision b968826d9c46dd6066d109eabc6255188de91218 --port 47865
```

In another terminal, with Docker available and python:3.12-slim pulled, run the follow-up:

```bash
PYTHONPATH=src:. python3 scripts/record_context_controls.py \
  --prepared "$EVALARC_CONTEXT_EVIDENCE/preparation" \
  --bridge "$EVALARC_CONTEXT_PROVIDER/examples/skill-impact/bridge.mjs" \
  --protocol-check --output /absolute/path/to/new/run
```

For the initial cohort, use its archived harness and omit --protocol-check. runtime-image.json provides the native image ID and registry digest observed after the runs, checked against every recorded evaluation. The archived harness uses python:3.12-slim; in a disposable Docker context, pull the recorded registry digest and make that tag resolve to the recorded image ID before reproducing the exact harness. Stop if the IDs differ; do not silently treat a newer tag as the same environment. The model and candidate use separate processes; candidate commands run in the bounded non-root Docker workspace. Evaluation seeds are 41 and 97, while the public example uses 17. Each trial has twelve model turns, up to 4,096 output tokens per turn, temperature 0.2 and a 600-second harness budget. Report actual measured usage, any infrastructure error and the complete trial denominator.

Code is MIT. The archived Skills Anywhere library retains its own MIT notice. Robot recording data retain ROBOT_DATA_LICENSE.txt and ROBOT_DATA_NOTICE.md inside each cohort. No independent upstream review or adoption is claimed.

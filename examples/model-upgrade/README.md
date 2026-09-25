# Review a model configuration change with original outputs

Eight public support-planning cases, three fresh generations per case and model
configuration. The baseline is `Qwen/Qwen3-8B` in BF16; the current configuration is
`Qwen/Qwen3.8-27B-FP8`. Every completed generation is retained. Plans are not executed.

[Interactive comparison](https://noteflowai.github.io/evalarc/model-upgrade/) ·
[Native check diff](reports/index.html) · [JSON comparison](reports/comparison.json)

This is a small development example, not a model leaderboard. Architecture,
parameter count and quantization differ. Public cases may have appeared in
training material; no decontamination or population accuracy claim is made.

The current configuration matches the complete plan in **19/24** answers,
compared with **15/24** for the baseline, but the upgrade gate **fails**:
five named checks regress and five become less reliable. All five checks for
`already-closed` fall from 3/3 to 0/3 because the current answers omit `actions`.
For `resolved-bug`, they fall from 3/3 to 1/3 because two answers wrap JSON in
Markdown fences. Ten other checks improve and twenty remain unchanged.
The ten blocking checks share these two format/schema failures; they are not
ten independent failure causes. Every answer, including these failures, is retained.

## Recompute the checks without generating answers

From the repository root, install the dev tools and use a new output directory:

```sh
python -m pip install -e '.[dev]'
python examples/model-upgrade/regrade.py --output runs/model-review-001
```

The script runs actual pytest checks for each preserved output and seed, retaining
native JUnit XML and stdout with two explicit metadata redactions: JUnit hostnames
become `redacted`, and absolute report directories in stdout become
`[report-directory]`. `reports/redactions.json` records both native and published
SHA-256 digests. Pass `--private-native-output /private/new-directory` to retain
the unredacted files locally. Model answers and check outcomes are never redacted.
The script concatenates the test suites without changing their test cases;
identical test names become repeated attempts in
EvalArc. It then calls the same comparison code as:

```sh
evalarc diff examples/model-upgrade/reports/baseline.xml \
  examples/model-upgrade/reports/current.xml --output runs/model-diff-001
```

Five checks cover JSON shape, routing calls, note contents and retry keys, closure,
and the complete ordered plan. These checks are not independent: invalid JSON
makes every check for that answer fail. Full plan equality is a narrow contract check,
not proof that a real support task was completed. The three generations are
separate sampling calls; they are not three regrades of one generated candidate
and are not advertised as a general Pass^k estimate.

## Generate a new cohort

`protocol.json` was committed before any completed task output. `protocol.py`
retains explicit expected plans independently of the generated answers.
Both models receive the same policy, case text, sampling settings and seeds.
Do not overwrite the published records. Reproduce the runtime versions listed
in each `recorded/*/identity.json`; the recorded hardware is an NVIDIA L40S.

```sh
python examples/model-upgrade/record.py \
  --model "$BASELINE_MODEL_DIR" --model-id Qwen/Qwen3-8B \
  --revision b968826d9c46dd6066d109eabc6255188de91218 \
  --protocol examples/model-upgrade/protocol.json --output runs/new-baseline

python examples/model-upgrade/record.py --vision --fix-dense-fp8-skip \
  --model "$CURRENT_MODEL_DIR" --model-id Qwen/Qwen3.8-27B-FP8 \
  --revision 017b9c7af6b5689d5dd426a76e0bc077eb5ca20a \
  --protocol examples/model-upgrade/protocol.json --output runs/new-current
```

The second command uses the multimodal architecture with text-only inputs here.
The pinned model-file manifests identify downloaded bytes. The original weights
are not included or altered. The FP8 recorder applies an explicit in-memory
correction: Transformers 5.17.0's regex-prefix matching otherwise treats the
checkpoint's nonexistent dense `mlp.gate` router exclusions as exclusions for
`gate_proj`, discarding its scale tensors. The correction removes those router
entries and requires every checkpoint key to be accounted for. The precise
adjustment and loading report are recorded in the identity, and initialization
failures that produced no completed answer are disclosed in `runtime-failures.json`.

Generation uses seeds 17, 29 and 43, temperature 0.6, top-p 0.9, top-k 20,
thinking disabled and a 512-token output cap. Token counts, timestamps, elapsed
inference time and memory observations are retained per answer. Hardware,
kernel and library changes may change sampled outputs; timings are diagnostic
observations, not a throughput comparison.

The offline download includes original answers, prompts, identities, native
results, the declared checks and reproduction scripts. No API keys, private
customer records or model-generated tool calls are used during review.

## 中文

对照 Qwen3-8B BF16 与 Qwen3.8-27B FP8 的真实输出：8 个公开开发用例，每个配置分别
新生成 3 次，完整保留全部 48 个回答。pytest 检查 JSON、路由、备注与重试键、关闭
条件和完整动作计划；EvalArc 比较原生 JUnit 结果。计划没有执行，模型规模和量化
不同，不能把差异归因于单一因素，也不能据此推算总体模型能力。默认复核无需 GPU。

完整计划匹配从 15/24 提高到 19/24，但升级门禁失败：5 个检查回归、5 个可靠性下降，
另有 10 个改善、20 个不变。10 个阻断检查对应两个用例的格式或结构错误，并非
10 个独立原因。只脱敏原生测试日志的机器名和报告目录，模型回答与检查结果完整保留。

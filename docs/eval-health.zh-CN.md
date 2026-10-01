# 调优之前先检查评测本身

已经饱和、噪声大或部分失效的评测，会奖励对用户没有帮助的改动。`evalarc eval-health`
读取同一评测保存下来的 Inspect AI、promptfoo 或 JUnit 结果，指出应先修复的问题。它完全
离线：不重新运行评测，也不调用模型。[English](eval-health.md)。

```bash
evalarc eval-health examples/results-diff/inspect/baseline.json \
  examples/results-diff/inspect/current.json --ordered --min-effect 0.05 --output health
```

示例报告 1 个警告：32 次已评估检查尝试、84.4% 通过率下，只有大于约 25.2% 的变化才能与
采样噪声区分，高于希望检测的 5%；每次运行约需 811 次已评估检查尝试。`--output` 会新建
目录，写入 `health.json`、`summary.md`、离线 `index.html`，以及 `inputs/` 下的逐字节输入副本。

## 检查项

| 结果 | 级别 | 触发条件 | 应检查什么 |
| --- | --- | --- | --- |
| `saturated` | 警告 | 最佳文件的检查通过率不低于 `--saturation`（默认 95%） | 增加两位领域专家会给出一致判断的更难用例，或改为在质量不变时降低成本与延迟 |
| `always_failing` | 警告 | 某检查项在所有文件的每次已评估尝试中都失败（至少两次） | 先看任务描述和评分器：未写明的要求、歧义任务、评分器缺陷都会表现为永久的能力缺口 |
| `flaky_checks` | 超过 10% 的重复检查时为警告，否则为提示 | 同一文件中某检查项时而通过时而失败 | 任务歧义、同一输出评分不一致、配置不稳定、上一轮遗留状态；可用 [`evalarc trace-stability`](judge-stability.zh-CN.md) 对固定输出重复评分 |
| `unassessed_attempts` | 警告 | 存在错误、超时或跳过的尝试 | 调优前先修复流水线，避免把基础设施故障当成模型表现 |
| `single_attempt` | 提示 | 每个检查只记录了一次 | 记录重复尝试（Inspect `--epochs`、promptfoo `--repeat`） |
| `noise_exceeds_min_effect` | 警告 | 给出 `--min-effect D` 时，该规模的两次运行能分辨的变化大于 D | 增加用例或重复次数；提示中给出大致所需尝试数 |
| `capability_inversion` | 警告；在噪声内为提示 | 给出 `--ordered` 时，后一个（更强的）文件得分更低 | 更强的模型或更高思考强度不应得分更低；检查任务歧义或评分器校准 |
| `inconsistent_grading` | 警告 | 逐字节相同的输出被判为通过和失败（同一文件内或跨文件） | 评分器不确定或已变更；改用确定性检查，或固定评分器后重评 |
| `truncated_outputs` | 警告 | 尝试因 token 上限停止（`max_tokens`、`length`、Inspect token limit） | 提高上限或缩短任务；被截断的回答测的是预算 |
| `config_not_applied` | 警告 | Inspect 日志请求了 `reasoning_effort`（none/minimal 以外）或 `reasoning_tokens`，但每次尝试记录的推理 token 都是 0 | 设置可能没有生效；检查参数名、模型是否支持以及是否被覆盖 |
| `model_judge_replaceable` | 提示 | 模型评分的检查至少有 10 个输出，且不同取值不超过 10 个或全为 JSON | 改用精确匹配、固定标签集或 JSON Schema 校验；开放式输出才用模型裁判 |
| `self_graded` | 警告 | 被测模型同时是裁判：Inspect 模型评分器未设 `model` 选项或 `grader` 角色，或 promptfoo 评分提供方与被测提供方相同 | 指定独立的裁判模型 |

输出按记录内容的 SHA-256 比较（Inspect `output.completion`、promptfoo `response.output`）；
JUnit 不记录输出，因此不评估评分一致性、截断和自评。

## 失败分类

报告对最后一个文件中每个失败用例按首个命中的规则分类，先弄清原因再改动：`pipeline`（有错误、
超时或跳过）、`truncated`（触及 token 上限）、`grader_inconsistent`（同一输出判定不同）、
`regressed`（本文件全失败但早先文件通过过）、`never_passes`（所有文件每次都失败）、
`variable`（部分尝试通过）、`consistent_failure`（单次尝试失败，适合做根因修复）。
每行运行记录还给出 95% Wilson 区间、平均记录时长与成本。

可分辨变化取最后一个文件通过率下 95% 正态近似半宽的两倍，与 `evalarc diff`
[采样噪声标注](ci-gate.zh-CN.md#采样噪声标注)的不重叠规则一致。同一用例的多次尝试并不独立，
因此这是偏乐观的下限。

退出码：**0** 报告已生成；使用 `--require-healthy` 时，存在任何警告为 **1**；输入无法读取或
无法比较、选项无效或输出目录已存在为 **2**。输入必须格式相同；Inspect 还要求任务名相同。

## 规模、计划与逐用例记录

报告会给出最后一个文件的规模：用例数 × 尝试次数 × 文件数，以及每个配置记录的时长与成本。
`--plan-attempts K`、`--plan-configs M` 按记录的每次尝试平均时长与成本估算计划中的运行。
`--output` 还会写出 `cases.jsonl`（每个文件、用例、尝试一行，含判定、输出、停止原因与用量），
`index.html` 列出最后一个文件的每个用例及其通过的检查尝试，并链接到记录的输出。采信评分器之前，
请先读一部分输出。

## 用例来源

保存的结果不会记录用例来自哪里。`--cases MANIFEST` 读取 `evalarc.case-manifest.v1` 文件，按
用例 ID 或 glob（首个匹配生效）声明来源，并可写明难点（`difficulty`）。来源取值：`production`、
`bug_report`、`support_ticket`、`user_traffic`、`manual`、`synthetic`、`model_failure`。
`model_failure` 且未写难点时报 `adversarial_sampling` 警告（只因某模型失败而入选，测的是该模型
而非任务）；没有任何生产、缺陷、工单或用户流量来源时报 `no_real_cases`；超过一半是合成用例时报
`mostly_synthetic`；全部来自用户流量时提示 `traffic_only`（用户多半只发预期能成功的请求）；
有用例未被声明时提示 `provenance_undeclared`。每个条目必须匹配至少一个用例，清单会以
`cases.json` 复制到输出目录。来源由调用方声明、不经核验；使用生产会话前请先确认留存与敏感数据规则。

## 局限

检查结果只提示需要阅读的地方，并不证明存在缺陷；没有警告也不说明用例代表生产流量。
尽量从生产日志、缺陷报告和工单中选取用例，不要只用某个模型的失败案例构建评测集：
那样测到的是该模型的薄弱点，而不是任务本身。

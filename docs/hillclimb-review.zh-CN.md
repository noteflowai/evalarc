# 合并前复核一次爬山调优

爬山调优每次提出一处改动（提示词、技能规则、模型或思考强度），重跑评测，只保留有帮助的改动。
`evalarc hillclimb-review` 用已保存的结果离线重放这一判定：一份基线、每一步改动后的结果，以及
声明好的[留出集](ci-gate.zh-CN.md#留出集改动是否泛化)。它不提出改动、不重跑、不调用模型。
[English](hillclimb-review.md)。

```bash
evalarc hillclimb-review examples/hillclimb-review/results/00-baseline.json \
  examples/hillclimb-review/results/0[1-5]-*.json \
  --held-out examples/hillclimb-review/split.json --objective cost --min-effect 0.05
```

示例的结果和成本由 `build.py` [人工声明](../examples/hillclimb-review/README.md)，并非实测。以降本为
目标时：提示词审计保留；把失败调优工单粘进提示词被判为 `rollback_overfit`（调优 +14.6 pp，
留出 +0.0 pp）；换更新模型并降低思考强度保留（成本 0.463x）；换极便宜模型因留出下降 12.5 pp
被回滚；再换中档模型保留。最终成本为基线的 **0.217x**，建议 `merge_cost`（退出 0）。开始前的
提示说明该评测在留出集上只能分辨约 31% 的变化，所以留出提升本身仍在噪声内。

## 规则

每一步都与**最近一次保留**的结果比较，而不是与基线比较：

| 判定 | 条件 |
| --- | --- |
| `rollback_regression` | 留出检查丢失通过或覆盖，或任一分区通过率下降 |
| `rollback_overfit` | 调优用例提升，留出用例没有 |
| `keep` | 质量目标：两个分区都提升。降本目标：记录的成本下降且两个分区都没下降，或成本不升且两者都提升 |
| `rollback_no_gain` | 其他情况 |

连续回滚 `--stall-after` 次（默认 2）后，对最近保留结果中失败的**调优**用例按根因分类：
`pipeline`（错误、超时、跳过）、`truncated`、`grader_inconsistent`、`regressed`、
`never_passes`、`variable`、`consistent_failure`。只有 `consistent_failure` 才值得再改。
若剩余调优余量小于可分辨变化，报告会建议停止迭代，改为增加用例或重复次数。

最终保留结果与基线在留出用例上比较，并给出 95% Wilson 区间：

| 建议 | 退出码 | 含义 |
| --- | ---: | --- |
| `merge` | 0 | 质量目标：留出提升超出噪声，没有退步 |
| `merge_cost` | 0 | 降本目标：成本比低于 1 且不超过 `--max-cost-ratio`，留出检查没有丢失通过，两个分区都没下降 |
| `no_change_kept` | 1 | 每一步都被回滚 |
| `do_not_merge_regression` | 1 | 最终结果在留出检查或任一分区上差于基线 |
| `do_not_merge_within_noise` | 1 | 质量目标下，留出提升在噪声内 |
| `do_not_merge_cost` | 1 | 成本降幅不够，或没有记录成本 |
| `do_not_merge_leakage` | 1 | `--harness` 在提示词、技能或工具描述中发现留出用例文本 |

输入无效或不可比时退出 2：格式或任务不同、各步用例集合不同、同一文件出现两次，或
`--objective cost` 时并非每次尝试都记录了成本或 token。

`--output` 写出 `hillclimb.json`、`summary.md`、`index.html`、`split.json`、`inputs/` 下的逐字节
副本，以及 `tuning-failures.json`。最后这个文件只包含调优用例的失败，适合交给调优循环读取，
其中没有任何留出结果。

## 文章原则与 EvalArc 的对应

| 原则 | EvalArc |
| --- | --- |
| 前沿模型仍有提升空间，≥95% 时告警 | `eval-health` `saturated` |
| 始终失败的任务往往有歧义或评分有误 | `eval-health` `always_failing`、分类 `never_passes` |
| 方差低；同一输出评分一致 | `eval-health` `flaky_checks`、`inconsistent_grading`；`diff` `same_output_different_verdict`；`judge-run --repeat` 裁判一致性；`trace-stability` |
| 配置引入的波动，如思考强度未生效 | `eval-health` `config_not_applied` |
| 给出评测规模（用例 × 重复 × 模型）与预估时长；每个用例一行记录并附会话链接的结果页 | `eval-health` 规模、`--plan-attempts`/`--plan-configs`、`cases.jsonl`、逐用例页面 |
| 提示词缓存等成本因素 | `diff` `usage.cache_read_share` |
| 链路检查：超时、API 报错、截断 | `eval-health` `unassessed_attempts`、`truncated_outputs`，分类 `pipeline`/`truncated` |
| 裁判不能是被测模型 | `eval-health` `self_graded`；`judge-score` `self_judged` |
| 裁判在不知道哪份是基线的情况下选更优输出 | `judge-packet pairwise` + `judge-run`（你的裁判命令）+ `judge-score`（随机 A/B、位置偏差检查） |
| 输出空间有限时用程序化校验 | `eval-health` `model_judge_replaceable` |
| 抽样阅读打分记录，小批量核验评分器 | `judge-packet grader` + `judge-score --min-agreement`（误判通过与误判失败） |
| 更强模型或更高思考强度应得分更高 | `eval-health --ordered` `capability_inversion` |
| 基线分数带置信区间 | `diff`、`eval-health`、`hillclimb-review` 中的 95% 区间 |
| 首轮前测量噪声，与最小有效提升比较 | `eval-health --min-effect`、`hillclimb-review` 提示 |
| 程序化打分：精确匹配、固定标签、JSON Schema、单元测试 | `eval-init` 评分器：`exact`、`label`、`json_schema`、`command` |
| 首轮迭代前随机拆分训练集与测试集 | `review-inputs --random-split`，只在 `cases.jsonl` 中记录一次 |
| 训练/测试拆分；训练涨、测试不涨则回滚 | `diff --held-out`、`hillclimb-review` `rollback_overfit` |
| 退步回滚；两者都涨才保留 | `hillclimb-review` 规则 |
| 不把失败样例粘进提示词 | `--harness` 泄露扫描；`tuning-failures.json` 不含留出用例 |
| 连续 2–3 轮不涨时分类剩余失败，收益低于噪声则停止 | `hillclimb-review` 停滞分类 |
| 保持质量、降低成本 | `diff --max-cost-ratio`、`hillclimb-review --objective cost` |
| 对比基线出最终报告；增益在噪声内不建议合并 | `hillclimb-review` 建议 |
| 优先使用生产会话、缺陷报告与工单，而非合成用例 | `eval-health --cases` `no_real_cases`、`mostly_synthetic`、`traffic_only` |
| 不要只用某模型的失败案例构建评测集 | `eval-health --cases` `adversarial_sampling` |

运行调优循环和裁判模型由 `hillclimb-run`、`judge-run` 执行你的命令完成（EvalArc 自身不调用模型）：
propose 命令只能看到调优失败、只能修改允许的文件，复制用例文本的补丁会在评测前回滚。

`build-eval` 环节由 `eval-init`（用例、程序化评分器、评测脚本与循环配置）和 `review-inputs`
（运行前的输入审查页）覆盖。挑选用例与制定评分标准仍是你和编码 Agent 的设计工作，EvalArc 负责
检查结果（`review-inputs`、`eval-health`、`judge-packet grader`）。用例是否贴合生产由用例
清单声明，不经核验。

## 局限

判定由保存的结果重放，EvalArc 无法确认这些步骤就是调优循环实际运行的步骤，也无法确认留出结果
对它不可见。通过率合并了检查尝试，而同一用例的尝试并不独立，因此区间偏乐观。成本比来自各一次
运行。请在第一步之前声明拆分，并只在经过审阅的提交中修改。

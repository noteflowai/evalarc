# 在拉取请求中拦截退化的检查项

总分上升时，原本通过的检查项也可能开始失败。`evalarc diff` 读取同一评测的两份
已保存结果，逐个配对用例与检查项；只要某个检查项的通过次数下降或消失，就返回失败。
支持 Inspect AI 日志、promptfoo `--output` JSON 和 JUnit XML（pytest、基于 pytest
的 DeepEval 及多数测试运行器）。它不会重新运行评测，也不调用模型。
[English](ci-gate.md)。

`evalarc diff` 与 GitHub Action 随 0.14.0 发布。如需在 Action 之外运行，请从 PyPI 安装固定版本：

```bash
python -m pip install evalarc==0.14.0
```

## 用已记录的结果试一试

[示例文件](../examples/results-diff/README.md)由 Inspect AI 0.3.268、promptfoo
0.123.1 和 pytest 8.4.2 基于脚本化回复生成，复现时无需模型密钥。在源码目录中运行：

```bash
evalarc diff examples/results-diff/inspect/baseline.json \
  examples/results-diff/inspect/current.json --output inspect-diff
```

命令退出码为 **1**：Inspect 的 match accuracy 从 0.625 升至 0.8125，但当前版本在两个
epoch 中都对重复订单退款（`refund-duplicate` 退化），`cancel-pending` 的精确匹配只在
一半 epoch 中通过（`less_reliable`）。promptfoo 示例的通过率保持 75%，失败的却换成了
另一项测试；JUnit 示例把一个原本通过的检查变成了跳过。

`--output` 会新建目录，写入 `diff.json`、`summary.md`、离线 `index.html` 以及两份输入的
逐字节副本；`diff.json` 记录了它们的 SHA-256，审阅者可以复算同一比较。

## 哪些变化会导致失败

| 变化 | 含义 | 是否失败 |
| --- | --- | --- |
| `regressed` | 以前通过，当前所有尝试都未通过 | 是 |
| `less_reliable` | 通过率下降，但仍有尝试通过 | 是 |
| `unassessed` | 以前通过，当前只有错误或跳过 | 是 |
| `less_covered` | 当前已评估的尝试次数少于基线，通过率不能算作不变或提升 | 是 |
| `removed` | 当前运行缺少该检查项或用例 | 是 |
| `improved` | 通过率上升 | 否 |
| `added` | 当前运行新增 | 否 |

状态不是 `success` 的 Inspect 当前日志同样判为失败。以更少 epoch 重新运行或丢失样本时，
门禁以 `less_covered` 失败，直到尝试次数与基线一致或提交新的基线；通过率下降时仍优先报告
`regressed` 或 `less_reliable`。删除一个失败的检查项也会失败，
否则删掉它就能让门禁变绿。退出码：**0** 无检查项丢失通过，**1** 至少一项丢失，
**2** 文件无法读取或无法比较（格式不同、Inspect 任务名不同、没有样本、格式错误、
Inspect 样本在同一 epoch 中重复）。同一 epoch 中重复出现的样本 ID（整数 `7` 与字符串
`"7"` 视为同一 ID）会以退出码 2 报告并给出样本与 epoch：若把副本算作额外尝试，会夸大覆盖并
掩盖 `less_covered`。这类日志通常来自手工合并、拼接或编辑；请用
`inspect log dump LOG.eval > LOG.json` 重新导出，或重新运行评测。同一 ID 出现在不同 epoch
是正常的重复尝试；没有整数 `epoch` 的样本不做此检查。
2 表示流水线本身有问题，不是退化。

## 采样噪声标注

一次评测只是一次抽样。检查项记录了多次尝试（Inspect epoch、promptfoo repeat、重复的
JUnit 用例）时，若至少一侧出现了通过与失败并存的实际波动，且两侧通过比例的 95% Wilson
区间重叠，`diff` 会把该变化标为**在采样噪声内**：现有尝试次数不足以把它与重复采样波动
区分开。`diff.json` 在对应变化上写入 `within_sampling_noise`，顶层写入
`blocking_changes_within_sampling_noise`；`summary.md`、`index.html` 和命令行输出会重复
这一计数。

这是描述性标注，不是显著性检验，**不会放宽门禁**：被标注的退化仍然退出 1。全部通过
变为全部失败是该尝试次数下最强的信号，永远不会被标为噪声。要确认被标注的变化，请增加
每个检查项的尝试次数（Inspect `--epochs`、promptfoo `--repeat`）。这对应“收益必须超过
评测噪声才值得采纳”的做法。

## 留出集：改动是否泛化

若改动是针对部分评测用例调出来的，仅凭这些用例无法说明它在别处也有帮助。用一个小 JSON
文件声明哪些用例在改动过程中**没有**被查看：

```json
{
  "schema_version": "evalarc.case-split.v1",
  "held_out": ["status-*", "address-change"]
}
```

条目可以是精确用例 ID 或 glob 模式；每个条目必须匹配至少一个用例，且至少保留一个调优用例。
运行 `evalarc diff ... --held-out split.json`，按分区比较检查尝试通过率并给出状态：

| 状态 | 含义 |
| --- | --- |
| `held_out_regressions` | 留出用例中有检查项丢失通过或覆盖 |
| `generalizes` | 留出用例的提升超出采样噪声（95% Wilson 区间不重叠） |
| `overfitting_signal` | 调优用例的提升超出噪声，留出用例没有 |
| `held_out_gain_within_noise` | 留出用例有提升，但现有尝试次数不足以与噪声区分 |
| `no_measurable_gain` | 两个分区都没有超出噪声的提升 |

在已记录的示例中，三个留出用例的通过尝试从 8/12 升到 12/12，12 次尝试不足以判定超出噪声，
状态为 `held_out_gain_within_noise`。拆分文件会以 `split.json` 复制到输出目录，
SHA-256 记录在 `diff.json` 中。拆分的独立性取决于声明本身：EvalArc 无法确认改动者没有看过
留出结果。请把留出用例排除在作者或调优循环读取的文件、日志和失败记录之外，并只在经过审阅的
提交中修改拆分。

## 调度层泄露扫描

`--harness 路径 ...` 在提示词、技能、指令和工具描述文件（或目录；跳过隐藏项和二进制文件）中
查找逐字复制的用例输入与参考答案。匹配忽略大小写和空白，短于 `--leak-min-chars`（默认 12）
的字符串不计。输入取自 Inspect 样本输入与 promptfoo 测试变量；参考答案取自 Inspect target
与正向 promptfoo 断言值（跳过 `not-*` 与代码断言）。JUnit 报告两者都没有，因此不扫描。
改写或编码后的复制无法检测，共用短语也可能是正常的，请逐条审阅。

## 要求泛化

`--require-generalization`（需要 `--held-out`）额外要求状态为 `generalizes`，且调度层中
没有留出用例文本，否则门禁失败。不加该选项时，留出与泄露部分仅供参考，退出码不变。
GitHub Action 对应输入为 `held-out`、`harness`（空格分隔）和 `require-generalization`，
输出为 `generalization-state` 和 `leakage-hits`。调优之前，可先用
[`evalarc eval-health`](eval-health.zh-CN.md) 检查评测本身；要复核调优循环的每一步，请用
[`evalarc hillclimb-review`](hillclimb-review.zh-CN.md)。

## 保质降本

评测接近饱和时，有用的改动往往是质量不变、成本更低：更小的模型、更低的思考强度、更短的提示词
或更好的提示词缓存。`diff.json` 始终包含 `usage` 部分，给出两次运行都存在的用例上、源工具记录的
每次尝试平均用量：`cost_usd`（Inspect `model_usage.*.total_cost`、promptfoo `cost`）、
`total_tokens`/`input_tokens`/`output_tokens`/`cached_input_tokens`/`reasoning_tokens`，以及
`duration_seconds`（Inspect 样本 `working_time`、promptfoo `latencyMs`、JUnit 测试 `time`）。
缺失值保持未知，绝不按零计；每项都注明有多少次尝试记录了它。记录了成本或 token 时，
Markdown 与 HTML 报告会增加“Cost and usage”部分。

`--max-cost-ratio R` 增加一道门禁：当前每次尝试的平均用量不得超过基线的 `R` 倍（`1.0` 表示
不增加，`0.5` 表示至少减半）。质量门禁照常生效，更便宜但丢失检查项的运行仍然失败。
`--cost-metric auto`（默认）优先用记录的成本，否则用总 token；也可指定 `cost`、`tokens`、
`duration`。所选指标在任一匹配尝试上缺失，或基线均值为零时，命令退出 2，而不是猜测。
GitHub Action 对应输入为 `max-cost-ratio`、`cost-metric`，输出为 `cost-ratio`。

EvalArc 不为 token 定价。不同模型的分词器和价格不同，换模型时请优先比较记录的成本。
JUnit 时长测的是测试本身，可能不包含 Agent。比值来自各一次运行，没有区间；差距较小时请重复运行。

Inspect 的 `C`、`true` 或不低于 `--threshold`（默认 1.0）的数值视为通过；`I`、`N`、
`P` 视为未通过。错误与跳过记为未评估。`.eval` 归档使用 zstd，Python 3.14 起可直接读取；
更早版本请使用 `--log-format json`，或运行 `inspect log dump LOG.eval > LOG.json`。

## 使用 GitHub Action

```yaml
- uses: noteflowai/evalarc@v0.14.0 # 或完整的提交 SHA
  with:
    baseline: evals/baseline.json
    current: results/current.json
```

Action 在虚拟环境中安装自身版本的 EvalArc，把摘要追加到作业摘要，并输出
`gate-passed`、`blocking-changes` 和 `report`。输入项、基线来源（提交到仓库的基线或
在同一作业中评测基础分支）以及拉取请求评论的写法见[英文说明](ci-gate.md#use-the-github-action)。

## 局限

比较信任各工具记录的通过/失败与分数，不重新评分，也不认证文件来源。匹配依据记录的
标识：重命名 promptfoo 测试描述或 Inspect 样本 ID 会显示为一项删除和一项新增。默认阈值下，
低于满分的数值都算未通过，因此 0.9 降到 0.6 不会被报告；需要时请降低 `--threshold`。

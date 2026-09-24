# 在拉取请求中拦截退化的检查项

总分上升时，原本通过的检查项也可能开始失败。`evalarc diff` 读取同一评测的两份
已保存结果，逐个配对用例与检查项；只要某个检查项的通过次数下降或消失，就返回失败。
支持 Inspect AI 日志、promptfoo `--output` JSON 和 JUnit XML（pytest、基于 pytest
的 DeepEval 及多数测试运行器）。它不会重新运行评测，也不调用模型。
[English](ci-gate.md)。

> `evalarc diff` 与 GitHub Action 从 **0.14.0** 起提供。发布前可从主分支安装：
> `python -m pip install "evalarc @ git+https://github.com/noteflowai/evalarc@main"`。

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
| `removed` | 当前运行缺少该检查项或用例 | 是 |
| `improved` | 通过率上升 | 否 |
| `added` | 当前运行新增 | 否 |

状态不是 `success` 的 Inspect 当前日志同样判为失败。删除一个失败的检查项也会失败，
否则删掉它就能让门禁变绿。退出码：**0** 无检查项丢失通过，**1** 至少一项丢失，
**2** 文件无法读取或无法比较（格式不同、Inspect 任务名不同、没有样本、格式错误）。
2 表示流水线本身有问题，不是退化。

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

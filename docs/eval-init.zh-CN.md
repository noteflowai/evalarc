# 创建评测项目

`evalarc eval-init` 生成一个可直接运行的评测项目，对应文章 `build-eval` 中可离线完成的部分：
用例、应用桩、程序化评分器、写出 Inspect 格式日志的评测脚本，以及爬山调优配置，并与 EvalArc
的各条命令接好。`evalarc review-inputs` 在任何运行之前把用例渲染成页面供你逐条阅读。
[English](eval-init.md)。

```bash
evalarc eval-init my-eval
cd my-eval
evalarc review-inputs cases.jsonl --output ../review --write-split split.json \
  --write-manifest cases.manifest.json
python evaluate.py ../results/baseline.json --epochs 3
evalarc eval-health ../results/baseline.json --cases cases.manifest.json --min-effect 0.05 \
  --plan-attempts 5 --plan-configs 2 --output ../health
evalarc judge-packet grader ../results/baseline.json --sample 20 --output ../spot
evalarc hillclimb-run hillclimb.toml --output ../climb --trust-local
```

应用桩按 `prompt.md` 中的关键词规则分派工单，因此改动之前每条命令都能运行。请把 `app.py` 的
`respond()` 换成你的模型调用，`cases.jsonl` 换成你的用例，`propose.py` 换成修改 `prompt.md` 的
模型调用。生成的 `README.md` 逐步说明流程。

`cases.jsonl` 每行一个用例：`id`、`input`（写明评分器检查的全部条件）、`check`（`exact`、
`contains`、`label`、`regex`、`fuzzy`、`json_keys`、`json_schema`、`command`；`fuzzy` 可设 `min_ratio`，取值 (0, 1]，默认 0.9）、`expected`、`labels`（`label` 检查需要）、`source`、
`difficulty`（`model_failure` 需要）、`held_out`，以及可选的 `suite`：`capability`（能力用例，起始通过率可以很低）或 `regression`（回归用例，已经能做到，每次试验都应通过），会写入用例清单供 [`eval-health --cases`](eval-health.zh-CN.md#用例来源) 检查；可选的 `expect_action`、`expect_change`、`impact`、`owner`（[用例属性](eval-health.zh-CN.md#用例来源)）也会写入清单。声明了这些属性时，`review.json` 会分别计数，用例表增加 Attributes 列，并报告 `expect_action` 平衡相关发现（`one_sided_behavior`、`behavior_imbalance`、`behavior_undeclared`）以及 `impact_undeclared`（info）。优先使用生产会话（先确认留存与敏感数据规则），
其次是缺陷报告与工单、5–10 个手写用例，最后才是以它们为基础的合成用例。

`review-inputs` 逐行校验（出错时退出 2 并给出行号），生成审查页，并报告 `no_held_out`、
`held_out_share`、`duplicate_inputs`、`few_cases`、`dominant_answer` 以及
[用例来源](eval-health.zh-CN.md#用例来源)相关发现；只要有用例声明了 `suite`，还会统计各套件数量，并在部分用例未声明时提示 `suite_undeclared`、没有任何回归用例时提示 `no_regression_suite`（均为 info），用例表也会多出 Suite 列。`eval-health` 给出 `graduation_candidates` 时，请修改 `cases.jsonl` 中的 `suite` 并重新运行 `--write-manifest`；直接改清单会被覆盖。`--write-split`、`--write-manifest` 由
`cases.jsonl` 重新生成拆分文件与用例清单，用例文件始终是唯一来源；`--require-clean` 有警告时退出 1。`regex` 要求去掉首尾空白后的整个输出匹配 `expected` 中的正则（Python `re.fullmatch`；允许前后有其他文本请加 `.*`），`review-inputs` 会拒绝无法编译或超过 1000 字符的正则；输出超过 100000 字符时判为不通过，而不是截断后再匹配。Python 正则没有超时，请保持简单（避免 `(a+)+` 这类嵌套重复）。`fuzzy` 要求输出与 `expected` 的 difflib 相似度（忽略大小写和多余空白）不低于 `min_ratio`。两者都比 `exact` 更能容忍合理的变体，又保持确定性；连它们都太死板时再用模型裁判。`--prompt FILE...` 指定智能体能看到的提示词、技能或工具描述文件。评分器检查的内容都应在任务中写明：`label` 用例需要提到全部可选标签，`json_keys` 需要提到每个键，`json_schema` 需要提到每个必需键和字符串枚举值；这些词须出现在上述文件或该用例的输入中（不区分大小写）；首尾是 ASCII 字母、数字或下划线的词须以完整单词出现，因此 `generalized` 不算写明了 `general`，而中文、日文、韩文的词出现在句中任意位置都算，否则报 `unstated_requirement` 警告，并列出用例和缺失的词。期望答案本身不要求写出（否则就泄露了答案），`exact`、`contains`、`regex`、`fuzzy`、`command` 用例不做此检查；`review.json` 以 `prompt_files` 记录这些文件的名称和 SHA-256。`--random-split F`（配合 `--seed`）按 `source` 分层随机留出一定比例的
用例，并写入 `cases.jsonl` 的 `held_out`；已声明 `held_out` 时拒绝执行，因此拆分只做一次，看到结果后
无法重新洗牌。`json_schema` 检查输出是否符合 JSON Schema，`command` 把输出通过标准输入交给一条命令
（例如单元测试），退出码为 0 即通过。

挑选有代表性的用例、制定两位专家会给出一致判断的评分标准、为开放式输出编写模型裁判，这些是
设计决策。EvalArc 事后检查它们，但无法替你完成。

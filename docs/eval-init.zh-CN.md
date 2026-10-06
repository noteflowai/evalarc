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
`contains`、`label`、`json_keys`、`json_schema`、`command`）、`expected`、`labels`（`label` 检查需要）、`source`、
`difficulty`（`model_failure` 需要）、`held_out`。优先使用生产会话（先确认留存与敏感数据规则），
其次是缺陷报告与工单、5–10 个手写用例，最后才是以它们为基础的合成用例。

`review-inputs` 逐行校验（出错时退出 2 并给出行号），生成审查页，并报告 `no_held_out`、
`held_out_share`、`duplicate_inputs`、`few_cases`、`dominant_answer` 以及
[用例来源](eval-health.zh-CN.md#用例来源)相关发现。`--write-split`、`--write-manifest` 由
`cases.jsonl` 重新生成拆分文件与用例清单，用例文件始终是唯一来源；`--require-clean` 有警告时退出 1。`--random-split F`（配合 `--seed`）按 `source` 分层随机留出一定比例的
用例，并写入 `cases.jsonl` 的 `held_out`；已声明 `held_out` 时拒绝执行，因此拆分只做一次，看到结果后
无法重新洗牌。`json_schema` 检查输出是否符合 JSON Schema，`command` 把输出通过标准输入交给一条命令
（例如单元测试），退出码为 0 即通过。

挑选有代表性的用例、制定两位专家会给出一致判断的评分标准、为开放式输出编写模型裁判，这些是
设计决策。EvalArc 事后检查它们，但无法替你完成。

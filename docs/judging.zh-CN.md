# 盲评：核验评分器，并与基线对比

两条离线流程，用于需要人工或独立裁判模型的评判环节。EvalArc 只准备材料并统计结果，从不调用
模型。[English](judging.md)。

| 模式 | 回答的问题 | 对应的做法 |
| --- | --- | --- |
| `grader` | 记录的评分器是否与独立裁判一致？ | 采信评分器之前，先抽样阅读已打分的记录 |
| `pairwise` | 同一用例上，当前输出是否优于基线？ | 裁判在不知道哪份是基线的情况下选出更优输出 |

两种模式都读取记录了输出的 Inspect AI 或 promptfoo 结果；JUnit 报告不含输出，退出 2。

## 评分器抽查

```bash
evalarc judge-packet grader examples/results-diff/inspect/current.json --sample 10 --output spot
```

抽样时尽量各取一半已记录的通过与失败，确保少见的判定一定会被复核。`spot/share/` 中有
`packet.json`、可阅读的 `index.html`（每项的输入、参考答案和输出）以及
`verdicts.template.json`；评分器判定、抽样种子和源文件都不在 `share/` 中。裁判逐项填写
`pass`、`fail` 或 `unsure`，并声明身份（`"kind": "human"`，或 `"kind": "model"` 加 `"model"`）：

```bash
evalarc judge-score spot verdicts.json --min-agreement 0.9 --output spot-score
```

报告给出一致率及 95% 区间、Cohen's kappa，以及**误判通过**（评分器通过、裁判判失败）与
**误判失败**的混淆表，并列出每条分歧。请先看这些：评分器缺陷是评测误导人的最常见原因。
由于是分层抽样，一致率不等于评分器在全部尝试上的准确率。

## 与基线成对比较

```bash
evalarc judge-packet pairwise baseline.json current.json --sample 40 --seed 7 --output ab
```

每项把两次运行中同一用例、同一次尝试的输出分别作为 **A**、**B** 展示，顺序逐项随机，映射保存在
`ab/key.json`；输出完全相同的项会被跳过。裁判回答 `A`、`B` 或 `tie`：

```bash
evalarc judge-score ab verdicts.json --require-current-preferred
```

报告揭盲后给出当前胜、基线胜和平局数，当前版本在有胜负项中的胜率及 95% 区间，以及状态
`current_preferred`、`baseline_preferred` 或 `no_clear_preference`。同时统计裁判选择 A 位置的
比例；区间不含 50% 时标为**位置偏差**。

## 用 `judge-run` 运行裁判模型

EvalArc 本身不调用裁判，但 `judge-run` 可以逐项运行你的裁判命令。在 `judge.toml` 中写
`command`（参数数组，占位符 `{python}`、`{packet}`、`{config_dir}`）、`model`（记录在判定中，须与
被测模型不同）和 `timeout_seconds`：

```bash
evalarc judge-run spot --config judge.toml --output verdicts.json --trust-local
```

命令在 `spot/share/` 中运行，从标准输入读取单项 JSON（`mode`、`instructions`、`allowed_verdicts`、
`item`），并在标准输出最后一行打印 `{"verdict": "..."}`；它永远拿不到 `key.json`。任一项失败、
超时或答案无效时退出 2，且不写出判定。`--repeat N`（最多 10）让裁判对每项回答 N 次，
`judge-score` 随后报告**裁判一致性**：每轮答案都相同的条目占比及区间，以及答案变化的条目。
同一输入答案会变的裁判，会给它参与的每次比较增加噪声。命令以你的环境变量在主机上运行，因此需要 `--trust-local`。

## 门禁与退出码

`judge-score` 完成统计后退出 0。`--min-agreement A`（grader）与 `--require-current-preferred`
（pairwise）要求所有项都已作答、裁判不是被测模型且条件成立（pairwise 还要求没有位置偏差），
否则退出 1。数据包不匹配、`share/packet.json` 被改动、未知条目或答案无效时退出 2。
裁判模型名与记录中的被测模型相同时标为 `self_judged`。请使用不同模型担任裁判，并采用可逐条
核验的评分标准，而非 1–5 分量表。

## 局限

EvalArc 无法得知实际由谁评判，也无法确认对方是否看过密钥。请勿把 `key.json` 交给裁判，
判定只记录一次；密钥外泄后不要复用该数据包。同一用例的多次尝试并不独立，因此区间偏乐观。

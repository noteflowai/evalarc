# 用 EvalArc 落实 Agent 评测：文章逐条对照

Anthropic 工程文章 [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
（2026-01-09）介绍了团队如何构建可信的 Agent 评测。本页把文章的建议对应到 EvalArc 的命令、检查项或字段，标出
只部分支持的地方，并明确说明 EvalArc 不覆盖的部分。EvalArc 是离线审查层：读取你的评测框架已经写出的结果（Inspect AI、promptfoo、
JUnit、AgentCore、ATIF），并运行三个内置任务包；它不调用模型，不模拟用户，不驱动浏览器，也不做生产监控。
[English](agent-evals.md)。

## 术语

| 文章 | EvalArc | 说明 |
| --- | --- | --- |
| Task（问题、测试用例） | 用例（case）；内置任务称任务包 | `cases.jsonl` 的一行、一个 Inspect 样本、一个 promptfoo 测试、一个 JUnit testcase |
| Trial（试验） | 尝试（Inspect epoch、promptfoo repeat、重复的 testcase） | 只有所有检查都通过，用例级试验才算成功（[试验](eval-health.zh-CN.md#用例级试验passk-与-passk)） |
| Grader 与 assertion | 检查（scorer、assertion、testcase 结果） | `diff` 逐个用例、逐个检查比较 |
| Transcript（trace、trajectory） | 消息记录；`evaluation.json` 中每个用例的 `trace` | Inspect 消息配合 `--transcript-metrics` / `--include-transcript`；support 与 robot 任务包记录每个用例的动作和状态变化；coding 任务包只评估完成的产物，只记录对话哈希 |
| Outcome（结果） | 由主机核验的最终状态 | 内置评分器读取主机持有的状态；Agent 自称成功不计分 |
| Evaluation harness（评测框架） | 写出结果的工具；内置任务用 `evaluate`、`repeat`、`suite` | EvalArc 读取其输出 |
| Agent harness（脚手架） | 交给 `--harness` 的提示词、技能和工具描述文件 | 扫描用例文本泄露；`hillclimb-run` 在 `allow` 范围内修改 |
| Evaluation suite（评测套件） | 结果文件、TOML suite，或 `capability` / `regression` 套件角色 | 套件角色来自用例清单 |

## 逐条对照

### 评分器

| 建议 | EvalArc 中的做法 |
| --- | --- |
| 字符串匹配：精确、正则、模糊 | `eval-init` 检查 `exact`、`contains`、`label`、`regex`、`fuzzy`（[eval-init](eval-init.zh-CN.md)） |
| fail-to-pass / pass-to-pass 测试 | 用例清单中的 `expect_change`；`diff --cases --require-f2p`（[CI 门禁](ci-gate.zh-CN.md#误触发与漏触发fail-to-pass-与影响程度)） |
| 静态分析：lint、类型、安全 | 每个分析器一个固定名称的测试，用 `diff` 比较（[做法](../examples/static-analysis/README.md)） |
| 结果核验 | 内置任务包对主机持有的最终状态评分；[行为审查](https://noteflowai.github.io/evalarc/behavior-audit/index.html)检查实际提交到服务的内容 |
| 工具调用核验 | 部分支持。support 任务包的主机评分器检查关键的工具效果（备注、关闭、幂等）；导入的运行只能用 `--transcript-metrics` 统计工具调用次数，不检查调用了哪些工具或参数。见[评结果而不是路径](#评结果而不是路径) |
| Transcript 分析：轮次、token | `diff` 的 `usage`；`--transcript-metrics` 增加轮次、工具调用、消息数和错误重试，可用 `--cost-metric turns` 设门禁 |
| 评分细则、自然语言断言、基于参考答案的评判 | 不内置：EvalArc 不运行细则评分器，只导入它们的判定（Inspect `model_graded_*`、promptfoo `llm-rubric`、`g-eval` 等）并按下文检查；`judge-run` 在盲评数据包上运行你的裁判命令，结果记录了期望答案时，数据包会把它作为参考 |
| 每个维度一个独立裁判 | 不强制：每个检查单独评判、单独报告，但 EvalArc 看不到一次裁判调用是否同时评了多个维度 |
| 模型评分器及其校准 | `eval-health` 报 `self_graded`、`model_judge_replaceable`；`judge-packet grader` 用盲评的人工或模型判断衡量评分器（[盲评](judging.zh-CN.md)） |
| 多裁判共识、标注者一致性 | `judge-score PACKET A.json B.json C.json`：两两一致率与 Fleiss' kappa、多数或全体一致共识、`--min-annotator-agreement` |
| 成对比较、A/B | `judge-packet pairwise`：随机隐藏顺序并检测位置偏差 |
| 给裁判留“不确定”的出口 | grader 数据包有 `unsure`；成对数据包用 `--allow-unsure` |
| 领域专家评审、众包评判 | 只提供度量：`judge-score` 可统计任意多位标注者的判定文件；寻找并组织标注者由你完成 |
| 加权、二元或混合计分 | 内置任务的加权维度与完全解决；TOML suite 门禁（[套件](suites.zh-CN.md)） |

### 能力、回归与非确定性

| 建议 | EvalArc 中的做法 |
| --- | --- |
| 能力评测起点低；回归评测接近 100% | 每个用例的 `"suite": "capability"` / `"regression"`；`regression_case_failing`、`diff --require-regression-suite`、`hillclimb` 在回归用例被破坏时回滚 |
| 饱和的能力用例“毕业” | `graduation_candidates` |
| pass@k 与 pass^k | `eval-health` 按文件给出无偏估计；清单声明了套件时，`diff --cases` 还按套件给出 |
| 噪声内的变化 | 95% Wilson 区间、`within_sampling_noise`、`noise_exceeds_min_effect`、`--min-effect` |

### 构建任务集

| 建议 | EvalArc 中的做法 |
| --- | --- |
| 从真实失败中挑 20–50 个任务起步 | `eval-init` 脚手架；不足 20 个时提示 `few_cases` |
| 来源：手动检查、缺陷跟踪、客服工单 | 每个用例的 `source`；`no_real_cases`、`mostly_synthetic`、`adversarial_sampling` |
| 按用户影响排序；归属 | 每个用例的 `impact` 与 `owner`；`diff --cases` 按影响程度列出阻断变化及负责人 |
| 两位专家会给出相同判定的明确任务 | `review-inputs` 审查页逐条阅读；`judge-score` 支持两位及以上标注者 |
| 评分器检查的内容都在任务中写明 | `review-inputs --prompt` 报 `unstated_requirement` |
| 多次试验都是 0% 说明任务有问题；每个任务都有参考解 | `always_failing`、`never_passes`；`eval-health --reference` 报 `reference_fails` 并归类为 `task_or_grader_broken`；内置任务包运行参考解和声明的故障 |
| 平衡的问题集；误触发与漏触发 | 每个用例的 `expect_action`（`act` / `abstain`）；`one_sided_behavior`；`eval-health` 与 `diff --cases` 给出误触发和漏触发 |

### 框架、评分器与长期维护

| 建议 | EvalArc 中的做法 |
| --- | --- |
| 被评测的 Agent 与生产环境一致 | 不检查：请比对记录的配置（`config_not_applied` 只发现请求了思考却没有推理 token 的情况） |
| 每次试验都在干净隔离的环境中运行 | 内置 Docker 运行（[隔离清单](#试验隔离清单)）；`--cluster-errors` 标出多个用例的未评估尝试共有的同一错误信息 |
| 尽量用确定性评分器 | `model_judge_replaceable`、`inconsistent_grading` |
| 部分得分 | 内置任务的加权得分与完全解决分开 |
| 任务与评分器的缺陷 | `capability_inversion`、`always_failing`、`reference_fails`、`limit_reached`、`truncated_outputs`、`config_not_applied` |
| 评分器不能被绕过 | 内置评分器在候选环境之外运行；带声明故障的审计；`--harness` 泄露扫描；`hillclimb-run` 回滚粘贴用例的改动 |
| 读对话记录 | `eval-health --output` 写出 `cases.jsonl` 和输出索引；`judge-packet --include-transcript`；内置用例浏览器 |
| 饱和；问题对模型足够难 | `saturated`、`graduation_candidates`；编写更难的任务由你完成 |
| 开放贡献任务 | [通过拉取请求贡献用例](#通过拉取请求贡献用例) |
| 评测驱动开发与调优 | `hillclimb-run` / `hillclimb-review`，带留出用例和回滚规则 |

## 评结果而不是路径

优先检查 Agent 产出或改变了什么，而不是它走了哪些步骤。Agent 常会找到任务作者没想到的有效做法，检查“按某个顺序
调用了某个工具”会惩罚这种创造性，把正确答案判成失败。在 EvalArc 中：

- 内置任务包对主机持有的最终状态评分：support 任务包检查工单队列、备注和关闭状态，而不是哪些工具调用产生了它们。
- 在 `eval-init` 项目中，对答案评分（`label`、`json_schema`、`command`），不要从对话记录里解析工具名。
- 把对话记录数据当作约束或成本，而不是正确性：例如用 `--cost-metric turns` 设轮次或工具调用预算，或检查没有发生
  被禁止的副作用。
- 只有调用本身就是结果时才检查具体的工具调用，例如退款恰好提交了一次。

## 试验隔离清单

共享状态的试验并不独立：残留文件、缓存、共享数据库或可见的 git 历史会让后面的试验更容易，同一个资源上限也可能让
许多试验同时失败。EvalArc 只在内置 Docker 后端强制隔离（`--network=none`、只读根目录和候选目录挂载、CPU/内存/
进程数限制、每个用例全新的状态目录；见 [SECURITY.md](../SECURITY.md)）。对于在别处产生的结果，请检查：

- 每次试验都从全新的检出或容器开始，没有之前试验留下的 git 历史或文件。
- 缓存、临时目录和数据库每次试验都重置或各自独立。
- Agent 读不到评分器、期望答案或其他试验的输出。
- 资源上限足够高，不会让试验失败；用 `eval-health --cluster-errors` 查看出错或被跳过的尝试是否有同一错误信息。
- 同一用例的各次试验使用相同的预算和配置。EvalArc 只能看到一部分：`limit_reached` 标出因消息数或时间上限停止的尝试，
  `config_not_applied` 标出请求了思考却没有推理 token 的情况。

相关的试验会让 pass^k、区间和噪声估计偏乐观。EvalArc 无法核验外部框架中的隔离，这些检查需要你来做。

## 通过拉取请求贡献用例

最接近用户的人（产品经理、客服、销售）可以在不改动评测框架和评分代码的情况下添加用例。把用例放在 `cases.jsonl` 中：
贡献者新增一行后，在本地运行 `evalarc review-inputs evals/cases.jsonl --prompt evals/prompt.md --write-manifest evals/cases.manifest.json`，
并提交这两个文件；CI 审查每次改动（需要 EvalArc 0.21.0 或更高版本，`--prompt` 自该版本起提供；工作流见
[英文页面](agent-evals.md#contribute-cases-by-pull-request)）。用例无效时退出 2；有任何审查警告时退出 1（例如未写明的要求、
只测单侧行为、重复输入、没有留出用例或没有真实来源）；清单没有重新生成时也会失败。审查者从 `case-review` 产物
（审查失败时也会上传）中打开 `index.html`，逐条阅读新用例。

## EvalArc 不覆盖的部分

| 文章中的层次 | 状态 |
| --- | --- |
| 发布前与 CI 中的自动化评测 | 对已记录的结果和内置任务包做门禁与审查；运行你的 Agent 由你的评测框架完成 |
| 人工阅读对话记录 | 提供盲评数据包、对话记录和用例浏览器；阅读本身由你完成 |
| 系统性人工研究 | 只提供度量（`judge-score` 一致性）；招募和培训评分者由你完成 |
| 真实流量 A/B 测试 | 不覆盖；`judge-packet pairwise` 是离线偏好检查，不是线上实验 |
| 生产监控、用户反馈 | 不覆盖 |
| 模拟用户、浏览器与计算机操作环境 | 不覆盖；请导入它们的结果 |
| 研究型 Agent 的依据性与来源质量 | 没有对应任务包；导入裁判结果并用 `judge-score` 校准 |
| 时延：首 token 时间、每秒输出 token | 不报告；支持的导出格式不含流式时间戳 |

没有哪一层能发现所有问题。把 EvalArc 当作离线门禁和审查层，与生产监控、用户反馈配合使用。

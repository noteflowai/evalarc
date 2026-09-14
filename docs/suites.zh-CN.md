# 评测套件与 CI 验收

`evalarc suite` 用一份 TOML 配置组织多个候选、任务和重复轮次。
每个 job 单独评分、单独验收，所有 job 有效且达到门槛时套件才通过。

可直接使用[示例配置](../examples/suites/README.md)。[已记录的 Docker 示例](../examples/suite/index.html)
展示同一个错误策略如何被宽松门槛接纳，又被保护备注正确性的门槛拒绝；
底层任务结果保持一致。

## 配置与预览

```toml
schema_version = "evalarc.suite-config.v1"
name = "发布验收"

[[jobs]]
id = "support"
task = "support-routing"
candidate = "./workspace/support"
seeds = [17, 41, 97]
attempts = 3

[jobs.runtime]
backend = "docker"
image = "python:3.12-slim"
timeout = 10.0
case_timeout = 60.0
output_limit = 1048576

[jobs.gate]
min_mean_score = 1.0
min_resolution_rate = 1.0
required_dimensions = ["scope", "protocol"]
```

`runtime`、`gate` 表均可省略；默认值如上。轮次默认 **1**，
seeds 默认 `[17, 41, 97]`。候选路径相对于 TOML 文件解析，
`--output` 相对于命令所在目录解析；配置中不展开环境变量、`~` 或 shell 表达式。

```bash
evalarc suite acceptance.toml --dry-run
evalarc suite acceptance.toml --progress --output runs/acceptance-01
```

预览检查配置键、任务、候选目录是否存在、预算和门槛，并打印计划轮次及场景
执行次数。它不打开候选文件、不启动候选、不访问 Docker。候选命令稍后在有
大小限制、只含普通文件的快照中检查；预览不能替代镜像与运行环境就绪检查。

未知键会报错，避免拼错验收规则后静默失效。job ID 是唯一的小写字母、数字、
连字符或下划线组合，以字母或数字开头，最长 64 字符。套件限 1–100 个 job，
每个 job 限 1–100 个不重复整数 seed、1–100 轮；总计最多 1000 轮、
100000 次场景执行。配置文件上限 1 MiB。

## 验收门槛不改写评分

- `min_mean_score`：有效轮次平均分的最低值，默认 `1.0`。
- `min_resolution_rate`：全部检查通过的轮次比例，默认 `1.0`。
- `required_dimensions`：这些维度的所有适用检查必须每轮都通过，默认空列表。

两类数值门槛均须为 0–1 之间的有限数，按记录值比较。维度名称必须属于所选任务。
无论门槛多低，都要求计划轮次全部完成且有效；环境异常不能通过放宽门槛被忽略。

若允许部分进展，需要明确降低相应门槛。此时 job 可能被接纳，但
`fully_resolved` 仍为假，HTML 会明确标注。例如重复备注策略得分 0.9375，
可通过 `min_mean_score = 0.90`、`min_resolution_rate = 0` 的门槛，
却无法通过 `required_dimensions = ["notes"]`。报告保留具体失败的规则和场景。

单次评测原有的 checks、score、resolved 均不改变；套件不跨任务或跨领域平均分数，
不提供排名、统计显著性或通用能力估计。重复评测仍是固定公开场景上的描述性结果。

## 固定输入与执行

第一项任务开始前，先复制全部候选快照并预检查命令、镜像配置。
相同候选路径共用初始快照；执行中修改原始目录不影响后续 job。
每个 job 继续通过 `repeat` 创建各轮独立的工作目录、进程和场景状态。

输出保存原始 TOML、文件指纹、解析后的计划，以及各 job 的实际运行元数据。
临时候选快照会被删除；异地复现需要另行归档候选源码及运行依赖。
执行期间应固定 EvalArc 版本，避免修改评分源码。

配置不能自授本机执行权限或设置 Docker 命令包装器。任何本机 job 都要求 CLI
显式传入 `--trust-local`；该参数不改变配置中的 backend。
Docker 包装器使用 `--docker-command` 或 `EVALARC_DOCKER`。

配置或预检查失败时，不执行候选，也不发布报告。开始执行后，若某轮评测发生
环境异常，该 job 停止剩余轮次，其他 job 继续运行；套件最终拒绝通过。
当前串行执行，不含并行 worker、断点续跑或套件级总超时。

## 交付与 CI

顶层保存 `suite.toml`、`plan.json`、`suite.json`、`index.html`、
`junit.xml` 和 `events.jsonl`。每个 job 的重复汇总和逐轮证据位于
`jobs/<id>/`，可从总报告逐级打开。

JUnit 中一个 testcase 对应一个 **job 验收门槛**：
普通验收拒绝为 `<failure>`，无效或未完成评测为 `<error>`。
`system-out` 记录指标、门槛、完整通过状态和证据路径，不嵌入候选 stderr 或完整轨迹。
导出已通过 XML 解析验证，尚未声称在某个托管 CI 平台完成端到端导入。

退出码：全部门槛通过 `0`；有效但未达门槛 `1`；环境异常或配置错误 `2`；
用户取消 `130`。CI 应以命令退出码决定是否通过，并在失败时也保存整个输出目录；
只导入 JUnit 的报告器可能仅展示结果。

输出须使用新目录，且位于全部候选目录之外。完整报告统一发布；取消或未处理的
运行错误会删除整个未发布套件，包括其中已完成的 job。
若需保留取消前进度，可加 `--progress 2> acceptance.events.jsonl`，
把外部日志放在候选及输出目录之外。

完整字段与 CI 示例见[英文指南](suites.md)，本轮实测范围见[验证记录](validation-v0.5.md)。

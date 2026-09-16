<p align="center"><img src="docs/assets/banner.svg" alt="EvalArc — 分数提高，检查却退步了。" width="960"></p>

# EvalArc

**找出更高评分背后的 Agent 回归。**

查看退步的检查，定位已记录的工具动作，交付他人可以复核的证据。

[**立即查看失败案例 →**](https://noteflowai.github.io/evalarc/#regression) ·
[首次本地复核](docs/first-review.zh-CN.md) ·
[Hugging Face 演示](https://huggingface.co/spaces/glayguo/evalarc) · [English](README.md)

**90% → 93.75%。两项检查改善，一项原本通过的检查却失败了。**
工具已写入备注，却返回错误；策略更换幂等键后重试，多写了一次。
EvalArc 把这次退步展开给你看，帮助判断分数提高是否满足发布要求。

<a href="https://noteflowai.github.io/evalarc/#regression"><picture>
  <source media="(prefers-reduced-motion: reduce)" srcset="docs/assets/first-review.png">
  <img src="docs/assets/first-review.gif" alt="已记录案例的操作演示：分数提高，重试导致重复备注，严格验收规则拒绝结果。" width="960">
</picture></a>

演示回放的是脚本对照在 Docker 中运行后保存的记录，无需安装、账号或模型密钥。
研究预览 · MIT · Python 3.11+ · 本地流程使用 Linux · Python 包无第三方运行时依赖。

## 从一次复核开始

1. **看退步。** [对照两个版本](https://noteflowai.github.io/evalarc/#regression)，
   再在[案例浏览器](https://noteflowai.github.io/evalarc/#explorer)查看 `retry-after-commit`。
2. **看验收。** [比较两条规则](https://noteflowai.github.io/evalarc/#suite)：
   相同的 93.75% 分数，宽松规则接受，严格备注规则拒绝。
3. **本地复算。** [首次复核指南](docs/first-review.zh-CN.md)使用发布的 wheel 和原始记录重建报告；
   复核退出 0 表示一致，对照退出 1 表示发现退步。

在新的虚拟环境安装已发布的复核工具：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install "https://github.com/noteflowai/evalarc/releases/download/v0.12.1/evalarc-0.12.1-py3-none-any.whl#sha256=115f3d8d452dee2b5d3aed12f736880aca69aaf3ea42937ef4f8f222c0b2291b"
evalarc --version
```

离线复核不需要 Docker、Node、GPU 或模型 API。继续按
[下载与对照步骤](docs/first-review.zh-CN.md#3-复算这次退步)生成 HTML 报告，无需克隆源码。

## 用于自己的工作

| 已有材料 | 可以检查什么 | 入口 |
| --- | --- | --- |
| 变更前后的 Agent 评测 | 匹配条件下哪些检查退步 | [运行与对照](docs/workflow.md) |
| Strands Evals 任务的观测状态 | 用原生 SDK 报告复核备注、关闭状态及逐项回归 | [免安装交互报告](https://noteflowai.github.io/evalarc/strands/index.html) · [运行示例](examples/strands-state-review/README.zh-CN.md) |
| AgentCore Evaluate 结果与 spans | 有效零分、跳过、缺失以及技能交付 | [导出到审阅](docs/agentcore-first-review.md) |
| 同一记录上的多次评判 | 分数变化、通过/拒绝翻转及未评判情况 | [中文指南](docs/judge-stability.zh-CN.md) |
| 他人交付的报告 | 原始输入与汇总、验收规则、JUnit 是否一致 | [离线复核](docs/verification.md) |
| 评分器或待执行候选 | 正确实现和刻意缺陷是否被评分器区分 | [运行审计](#运行审计) |

运行记录导入有明确的[受限格式约定](docs/trace-workbench.md)，不直接接受任意云端导出。
带分数的示例为合成数据，独立 MCP 示例是真实本地加载但没有评委分数；未完成实时 AgentCore 评测。

尝试自己的记录后，欢迎[反馈首次使用的卡点或发现](https://github.com/noteflowai/evalarc/issues/new?template=first-use.yml)。
最小脱敏样例即可；安装失败同样有价值。

## 原始证据覆盖什么

| 任务 | 交互场景 | 声明缺陷 | 仅一个用例检出 |
| --- | --- | ---: | ---: |
| `durable-kv` | 代码交付物：响应、事务、重启持久化 | 8 | 3 |
| `support-routing` | 模拟工单：路由、精确备注、关闭与无关状态保护 | 7 | 2 |
| `robot-evidence-review` | 有出处的记录：坐标、时钟与缺失观察 | 6 | 1 |

三个任务包保存的审计检出 **21/21 种声明缺陷**。其中六种各依赖一个检测用例；
移除唯一检测用例后，重新审计的变异分数会下降。覆盖余量用于提前暴露这种依赖，
不代表覆盖未知缺陷。[检查覆盖](https://noteflowai.github.io/evalarc/#coverage) ·
[方法说明](docs/methodology.md) · [251 条审计记录](docs/casebook.md)。

更多工作流：[重复运行](docs/reliability.md)、[TOML 套件与 CI](docs/suites.md)、
[Python／JavaScript](docs/languages.md)、[GPU 研究记录](docs/research-pilots.md)、
[架构](docs/architecture.md)和[论文分析](docs/research.zh-CN.md)。历史更新见 [CHANGELOG](CHANGELOG.md)。

## 运行审计

安装上面的 wheel 后，用 Docker 执行内置 Python 参考实现和八种刻意带错的代码实现：

```bash
docker pull python:3.12-slim
evalarc audit --seeds 17 41 97 --output runs/audit
```

打开 `runs/audit/index.html`。退出 0 表示参考实现通过且所有声明缺陷被检出；
1 表示审计或候选失败；2 表示参数或环境导致结果无效。

对包内可信对照，可以在 CPU 上直接运行：

```bash
evalarc audit --task support-routing --backend local --trust-local --output runs/support-audit
```

本机模式具有当前用户权限；候选隔离使用 Docker，边界见 [SECURITY.md](SECURITY.md)。
重复运行时使用新的输出路径。

## 已实现

- Coding：六个评分维度，每个 seed 15 个验收场景。
- Coding 的八种错误实现：假确认、只存内存、事务部分提交、CAS 总是成功、
  布尔值与数字混淆、漏删、不验证键类型、只在退出时提交。
- 工单：五个维度，每个 seed 四个场景，七种错误策略，包括操作错误工单、
  空口宣称成功、重复备注、关闭未解决工单、放弃重试及重试时更换幂等键。
- 评分逻辑保留在候选容器之外；通过标准输入输出验证真实行为。
- 候选代码、评分器、测试实例的 SHA-256，以及容器镜像 ID、运行限制和随机种子。
- JSON 审计记录和无外部资源依赖的 HTML 报告。
- 检查点分数曲线分析，保留回归，不使用历史最高分掩盖退步。
- 自动化测试、Docker 审计 CI、MIT 许可证和中英文文档。
- `evalarc.toml` 配置候选程序命令；环境故障产生无效报告，不记成智能体零分。

## 用自己的代码智能体完成任务

```bash
evalarc init workspace/durable-kv
# 将 workspace/durable-kv 与 TASK.md 交给代码智能体。
# 完成 main.py 后：
evalarc evaluate workspace/durable-kv --output runs/candidate
```

Coding 场景负责评分交付物，不负责调用模型。Harbor、Prime Intellect 的原生适配，
以及真正困难的多小时任务集，都在路线图中。

## 工具型智能体与 JavaScript

```bash
evalarc tasks
evalarc init workspace/support --task support-routing --reference
evalarc evaluate workspace/support --task support-routing --output runs/support
```

工单策略接收观察，输出工具操作或结束动作。最终评分由宿主端检查业务状态，
不采信策略自报的成功结果。完整协议见[任务说明](src/evalarc/assets/SUPPORT_TASK.md)。

已安装 Node.js 时，可以运行独立的 JavaScript 策略：

```bash
evalarc evaluate examples/support-node --task support-routing \
  --backend local --trust-local --output runs/support-node
```

Python 继续用于任务、评分和研究集成；候选程序通过 JSONL 与评测器解耦。
TypeScript 可编译为 JavaScript 使用这一接口，但当前没有 TypeScript SDK，
也没有已验证的 Rust 实现。详见[命令配置](docs/candidate-commands.md)。

## 项目名称

项目已由本地原型名 GradeRail 更名为 **EvalArc**。仓库、Python 包、
导入路径、CLI、新报告 schema 与环境变量均使用新名称。
具体变化见[迁移说明](docs/migration.md)，原始名称检索记录保留在
[命名复评](docs/naming.zh-CN.md)中。

## 调研结论

我更看好“高质量工程环境的评分器审计”这个切口：有清晰的工程产物，
可与已有平台协作，也能进一步研究评分漏洞和训练迁移效果。
这是一项基于文献与现有项目的方向判断，不是对热度、增长或商业结果的保证。

调研区分已确认顶会论文、近期预印本和官方工程公告。Mechanize 融资公告已核实；
另查到 Business Insider 2026 年 9 月 11 日报道人才交易已完成，最终条款未披露。
“融资后 103 天”对应到最初报道日期，不代表谈判当天才启动。
原始来源和区别见[调研报告](docs/research.zh-CN.md)。

公开 seed 不是隐藏测试；对照全被识别也不代表能防住所有 reward hacking。
[Coding 报告](examples/audit/index.html)和[工单报告](examples/support-audit/index.html)
展示的是评分器审计结果，不能作为模型能力榜单。

<p align="center"><img src="docs/assets/banner.svg" alt="EvalArc — Run agents. Measure outcomes." width="960"></p>

# EvalArc

**面向 AI 智能体的开放任务环境与可审计评测。**

Python 3.11+，Linux 主机，零运行时第三方依赖，MIT 许可证。

[English](README.md) · [中文调研与论文分析](docs/research.zh-CN.md) ·
[架构设计](docs/architecture.md) · [方法说明](docs/methodology.md) · [开发路线](docs/roadmap.md)

EvalArc 关注智能体实际完成的结果，以及支撑评分结论的证据。
通过正确实现和刻意带有缺陷的实现进行对照，
检查它能发现哪些问题，并保存可复查的报告。

**v0.3 已实现 coding 和业务工具两个场景。**

| 任务 | 交互方式 | 验证内容 |
| --- | --- | --- |
| `durable-kv` | 执行代码智能体交付的服务 | 读写、事务、CAS、持久化与异常恢复 |
| `support-routing` | 策略通过工具操作模拟工单 | 路由、精确备注、条件关闭、无关数据保护与协议完成 |

v0.3 新增环境预检查、单次评测 HTML 报告和逐项回归比较，即使总分上升也能指出
退步的检查；输出保护会保留之前的运行证据。详见[使用流程](docs/workflow.zh-CN.md)。

两个场景使用共同的报告元数据，各自定义评分规则。工单环境记录工具调用和
真实状态变化，支持写入前失败、写入后响应失败及幂等重试。
已提供 Python 和 JavaScript 策略；浏览器环境、真实模型 API 适配与 RL 集成
仍在路线图中。具体边界见[架构设计](docs/architecture.md)。

当前版本尚未经过前沿模型、真实人类工时或强化学习收益标定。

## 直接运行

在当前仓库目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
docker pull python:3.12-slim
evalarc audit --seeds 17 41 97 --output runs/audit
```

输出 `runs/audit/audit.json` 和可独立打开的 `runs/audit/index.html`。
对仓库自带的可信对照代码，可以运行更快的本机演示：

```bash
evalarc audit --backend local --trust-local --output runs/local-audit
evalarc audit --task support-routing --backend local --trust-local --output runs/support-audit
```

本机模式具有当前用户的文件和网络权限。Docker 模式的边界见
[SECURITY.md](SECURITY.md)。无模型调用，无 API 费用，无 GPU 依赖。

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

<p align="center"><img src="docs/assets/banner.svg" alt="EvalArc — Run agents. Measure outcomes." width="960"></p>

# EvalArc

**面向 AI 智能体的开放任务环境与可审计评测。**

Python 3.11+，Linux 主机，零运行时第三方依赖，MIT 许可证。

[English](README.md) · [中文调研与论文分析](docs/research.zh-CN.md) ·
[架构设计](docs/architecture.md) · [方法说明](docs/methodology.md) · [开发路线](docs/roadmap.md)

EvalArc 关注智能体实际完成的结果，以及支撑评分结论的证据。
首版先验证评分器的区分能力：用正确实现和刻意带有缺陷的实现进行对照，
检查它能发现哪些问题，并保存可复查的报告。

**v0.1 已实现的场景是 coding：Durable KV 有状态工程任务。**
它覆盖读写服务、原子批处理、CAS、持久化和进程异常终止后的恢复。
浏览器、客服工单、业务工具等属于后续扩展范围，当前尚未实现这些环境或
交互式 agent 执行。多场景架构与下一步验收条件见[架构设计](docs/architecture.md)。

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
```

本机模式具有当前用户的文件和网络权限。Docker 模式的边界见
[SECURITY.md](SECURITY.md)。无模型调用，无 API 费用，无 GPU 依赖。

## 已实现

- 六个评分维度，每个 seed 15 个验收场景。
- 八种错误实现：假确认、只存内存、事务部分提交、CAS 总是成功、
  布尔值与数字混淆、漏删、不验证键类型、只在退出时提交。
- 评分逻辑保留在候选容器之外；通过标准输入输出验证真实行为。
- 候选代码、评分器、测试实例的 SHA-256，以及容器镜像 ID、运行限制和随机种子。
- JSON 审计记录和无外部资源依赖的 HTML 报告。
- 检查点分数曲线分析，保留回归，不使用历史最高分掩盖退步。
- 自动化测试、Docker 审计 CI、MIT 许可证和中英文文档。

## 用自己的代码智能体完成任务

```bash
evalarc init workspace/durable-kv
# 将 workspace/durable-kv 与 TASK.md 交给代码智能体。
# 完成 main.py 后：
evalarc evaluate workspace/durable-kv --output runs/candidate
```

当前版本负责评分交付物，不负责调用模型。Harbor、Prime Intellect 的原生适配，
以及真正困难的多小时任务集，都在路线图中。

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

公开 seed 不是隐藏测试；八个对照全被识别也不代表能防住所有 reward hacking。
示例展示的是评分器审计结果，不能作为模型能力榜单。

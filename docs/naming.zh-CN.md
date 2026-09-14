# 通用智能体评测项目命名复评

调研日期：2026-09-14。**已选定 EvalArc，并完成本地仓库、包和 CLI 更名。**
以下保留命名决策时的候选比较和查询快照，不代表持续更新的可用性检查。

当时的推荐顺序为 **EvalArc → EvalTrail → EvalMark**。GradeRail 是最初的本地原型名。
这里的排名是命名判断；重名与域名状态来自单独的查询记录，不代表传播效果实测。

## 候选比较

| 名称 | 字母数 | 适合表达的定位 | 优点 | 需要考虑的不足 |
| --- | ---: | --- | --- | --- |
| **EvalArc** | 7 | 通用智能体环境、评测与实验流程 | 短；Eval 指向评测；Arc 可表达完整任务过程；可覆盖不同场景 | 可能被联想到 ARC 基准；口头传播可能被拼成 EvalArk |
| **EvalTrail** | 9 | 有证据和轨迹的智能体评测 | 与审计、轨迹、可追溯结果的特色关联最直接 | 容易被理解为观测工具；Trail 与 Trial 拼写接近 |
| **EvalMark** | 8 | 智能体能力测试与评测标准 | 简洁，容易用于论文、报告和工具名 | 容易让人以为是单一 benchmark 或分数标准 |
| GradeRail | 9 | 评分器审计与评估流程 | 当前定位贴切，命令行名称简洁 | Grade 可能让人联想到教育评分；范围表达较窄 |

如果目标是长期建设跨 coding、浏览器、业务工具和研究任务的评测基础设施，
优先考虑 **EvalArc**。如果希望长期突出评分器审计和过程证据，**EvalTrail**
更直接。

AI 领域已有 [ARC Prize](https://arcprize.org/) 及 ARC 相关评测品牌，因此
EvalArc 这个名字可能引发相关联想。这是命名上的潜在歧义；若采用，应使用
`EvalArc` 的大小写和清楚的通用智能体副标题，不暗示与 ARC 项目有关联。

采用的品牌展示：

> **EvalArc**
>
> Open environments and evaluations for AI agents.
>
> Run agents. Measure outcomes.

该品牌表达项目方向；v0.1 实现 coding 场景，v0.2 加入工单模拟评测。
具体实现范围见[架构设计](architecture.md)。原始名称查询快照不随版本更新重写。

## 查询快照

| 名称 | GitHub 精确同名公开仓库 | PyPI / npm 精确包名 | `.com` | `.ai` / `.dev` |
| --- | --- | --- | --- | --- |
| EvalArc | 未检出；5 个包含该字符串的结果均非精确同名 | 均未检出 | RDAP 未找到记录 | 均未找到记录 |
| EvalTrail | 未检出 | 均未检出 | 已注册 | 均未找到记录 |
| EvalMark | 未检出 | 均未检出 | 已注册 | 均未找到记录 |
| GradeRail | 未检出；有 1 个近似结果 | 均未检出 | RDAP 未找到记录 | 均未找到记录 |

PyPI/npm 的“未检出”表示精确包接口返回 404。域名“未找到记录”表示 IANA
bootstrap 指定的注册局 RDAP 接口返回 404；实际能否注册、价格及保留规则仍需
以注册商的实时结果为准。域名未解析也不等于未注册。

本轮不包含商标核查、用户记忆测试或完整市场名称排查。通用搜索入口返回了无关
结果，因此未将其用于“无人使用”之类的结论。GitHub 精确名称检查覆盖了各
候选查询返回的全部结果。

原始状态与每项查询地址见
[naming-checks-2026-09-14.json](../research/naming-checks-2026-09-14.json)。

## 已排除的方向

- **AgentRail、ProofRail、RunProof、VeriTrail、AgentMeter**：已发现相邻
  智能体、验证、轨迹或用量领域的发布包。
- **TrialDock**：已有同名[临床研究产品](https://www.trialdock.com/)。
- **EvalMesh**：GitHub 已出现智能体评测或基础设施相关同名项目。

因此，不能仅因为某个 npm 或 PyPI 包名没有发布，就认定一个名字没有冲突。

## 主要查询来源

- GitHub Repository Search API：公开仓库名称与项目描述。
- PyPI JSON API、npm Registry：精确发布包查询。
- [IANA RDAP bootstrap](https://data.iana.org/rdap/dns.json)：确认各后缀的注册局查询入口。
- Verisign、Google Registry、Identity Digital 的 RDAP 接口：域名注册记录。

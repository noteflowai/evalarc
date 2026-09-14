# 从 Mechanize 到代码智能体评测：调研与开源项目选择

**调研日期：2026 年 9 月 14 日。推荐方向：代码智能体工程环境的评分器审计。
本地项目：GradeRail。**

这份调研的目标是找到一个值得做、能够交付、可以接入现有生态的开源切口。
“最热”无法事先保证；本文用论文贡献、现有产品能力、近期官方更新和实现可行性
作判断依据。项目定位是研究与工程起点，尚不构成一个经标定的前沿 benchmark。

检索方式为公司官网、arXiv 摘要和版本记录、论文 HTML 的相关方法章节、作者仓库、
官方项目文档，以及新闻 RSS 定位后的原始媒体报道。重点阅读了 R2E-Gym 的
verifier 分析、SWE-smith 的方法与局限、SWE-EVO 的 Fix Rate 定义。
这是定向调研，不是穷尽性系统综述。技术判断依赖论文与作者/官方材料；
交易情况区分公司公告、媒体报道及尚未披露的条款。

## 1. 新闻中哪些信息已核实？

| 用户材料中的说法 | 本次核验结果 | 依据与解释 |
| --- | --- | --- |
| 2026-04-24 融资 910 万美元、投后估值 5 亿美元 | 官方确认 | [Mechanize 融资公告][s1]直接列出日期、金额、估值和三位投资人 |
| “今年 4 月初”完成同一融资 | 与公告不一致 | 公告日期为 4 月 24 日 |
| 2025 年 4 月创立 | 官方时间线支持 | [公司公告列表][s2]列出 2025-04-17 的成立公告 |
| 聚焦软件工程 RL 环境和评测 | 官方确认 | [公司首页][s3]描述环境、grader 及训练用途 |
| GBA 模拟器、24 小时工程任务 | 官方产品支持 | 首页及 [GBA Eval][s4]；另有[作者仓库][s5] |
| Google 洽谈超过 15 亿美元的技术授权和团队交易 | 找到 2026-08-05 原始报道 | [Business Insider][s16]援引知情人士，描述人才引入及非独家技术授权洽谈；当时交易细节仍可变 |
| 截至今天仍“正在洽谈” | 已有后续媒体进展 | [2026-09-11 后续报道][s17]根据公开任职资料称人才交易已完成；最终条款未披露，不能确认最终支付金额 |
| 融资后 103 天启动磋商 | 应改成相隔 103 天出现报道 | 4 月 24 日至 8 月 5 日相差 103 天；原文称此前数周已在讨论，不支持将报道日当作谈判启动日 |
| 46 人、第三次同类交易、Mercor/Deeptune 收购、2500 个环境 | 本次未逐项建立原始来源证据 | 不作为本项目立项论据，不据此宣传行业规模 |

截至本次调研，应该表述为：**Business Insider 已报道人才交易完成，
此前报道的拟议规模为逾 15 亿美元，最终条款未披露**。
这不是公司正式披露的完整并购条款，也不应写成“已经支付 15 亿美元全资收购”。
技术上能确认的是：前沿代码智能体的工程环境和评分器已经有实际产品。
交易报道可以作为研究线索，但不能替代技术需求的证据。
不同交易结构的对价也不能直接作为环境创业公司的统一估值倍数。

## 2. 热点的技术实质

这个方向连接四个环节：可执行工作环境、长程代码智能体、能够区分交付质量的
评分器，以及消费这些信号的训练/评测系统。

已有资料支持三个重要判断：

1. **可执行环境是训练数据的一部分。** SWE-Gym 和 SWE-smith 把仓库、
   环境、任务和验证条件联系起来；只有 issue 文本和代码 diff 不能替代可运行验收。
   [P02][p2]、[P03][p3]
2. **执行测试也需要被评估。** R2E-Gym 的分析表明，测试可能缺乏区分度；
   非执行式 verifier 又可能依赖轨迹中的表达特征。其混合策略有实验依据，但
   不能据此认定任意“LLM judge + 单测”组合都会有效。[P06 方法 §4][p6full]
3. **基准需要持续维护。** Terminal-Bench 4.0 官方记录了资源标定、修复任务、
   移除已饱和或有质量问题的任务；METR TH1.1 也调整了任务集和评估设施。
   因此版本、运行条件和评分器质量都会影响结果。[S09][s9]、[S12][s12]

另一个直接的需求信号是 Terminal-Bench 于 2026-04-19 发布的
[Leaderboard Integrity Update][s15]：官方说明已发现作弊与 reward hacking，
并要求通过的试验提供轨迹。它支持“评分与证据链需要审查”的判断，但不代表
GradeRail 当前八种功能缺陷对照就能检测这些真实攻击。

这给小团队的启示是：先交付一个能证明评分可信度的具体工具，比构建完整云平台
更容易形成可验证价值。这是本调研的产品判断，不是文献已经证明的商业结论。

## 3. 顶会基石论文与前沿论文

“已确认顶会”只用于查到会议依据的条目。仅核实到 arXiv 的论文保留其检索状态，
不表示它一定未在其他地方发表。不要把各论文的历史成绩当作 2026 年实时榜单。
完整结构化记录见 [papers.json](../research/papers.json)。

| 优先级 | 论文 | 本次确认的发表信息 | 核心贡献 | 对 GradeRail 的具体启发 |
| --- | --- | --- | --- | --- |
| A | **SWE-Gym** — Training Software Engineering Agents and Verifiers with SWE-Gym | ICML 2025；arXiv 首版 2024-12 | 可执行 SWE 训练环境；训练 agents 和 verifiers | 任务、运行环境和验收条件一起版本化；明确训练集与评测集用途。[P02][p2] |
| A | **SWE-smith** — Scaling Data for Software Engineering Agents | NeurIPS 2025 Datasets & Benchmarks Spotlight；以作者仓库确认 | 从真实仓库构造环境并合成破坏既有测试的任务 | 把“错误实现是否被检测”做成可重复的工程过程；其主论文演示是 SFT，不能宣称已经证明 RL 收益。[P03][p3]、[作者仓库][s13] |
| A | **SWE-rebench** — An Automated Pipeline for Task Collection and Decontaminated Evaluation of Software Engineering Agents | NeurIPS 2025；arXiv v2 | 持续采集新任务，关注静态 SWE 评测污染 | 保存来源、时间与版本；不同随机 seed 不等于消除污染。[P04][p4] |
| A | **Measuring AI Ability to Complete Long Software Tasks** | NeurIPS 2025；arXiv v4 修订于 2026-07 | 用人类完成时间刻画智能体在给定成功率下的任务时长 | 区分 agent 运行时间、评测耗时、人类任务时间；不把 checkpoint AUC 命名为 time horizon。[P05][p5] |
| A | **SWE-bench** — Can Language Models Resolve Real-World GitHub Issues? | ICLR 2024 | 仓库级真实 issue 修复与可执行评估 | 作为基本实验范式；新项目必须解释超出单 issue 修复的价值。[P01][p1] |
| A | **R2E-Gym** — Procedural Environments and Hybrid Verifiers for Scaling Open-Weights SWE Agents | 本次核实 arXiv:2504.07164 及作者项目；未确认会议 | 环境合成；执行式/非执行式 verifier 的互补分析 | 最直接的评分器研究依据：测量区分度，增加独立负对照，警惕“成功叙述”影响评分。[P06][p6] |
| A | **SWE-EVO** — Benchmarking Coding Agents in Long-Horizon Software Evolution Scenarios | arXiv:2512.18470，首版 2025-12，v6 为 2026-05 | 基于版本演进的多文件任务；Fix Rate 表示部分完成度 | 持续演进和回归约束值得借鉴；不能用高历史分掩盖后续功能退化。[P08][p8] |
| B | **RE-Bench** — Evaluating frontier AI R&D capabilities of language model agents against human experts | 本次核实 arXiv v2（2025-05）；未确认会议 | 开放式研究工程环境、人类对照、预算敏感分析 | 以后做多小时任务时，应有真实人类基线并固定比较预算。[P07][p7] |
| B | **SWE-agent** — Agent-Computer Interfaces Enable Automated Software Engineering | 本次核实 arXiv v3（2024-11）；此处不补写未核实会议信息 | agent-computer interface 对任务表现的影响 | 评测必须记录 scaffold/工具和运行配置，不能只记录模型名称。[P09][p9] |
| B | **τ-bench** — A Benchmark for Tool-Agent-User Interaction in Real-World Domains | 本次核实 arXiv:2406.12045；未确认会议 | 最终数据库状态验收和重复尝试可靠性度量 | 对有状态任务，检查实际状态结果；pass^k 与 pass@k 不可混用。[P10][p10] |

建议阅读顺序是 **SWE-Gym → R2E-Gym → SWE-smith → SWE-EVO → METR**，
再按训练数据、污染控制或智能体接口补读其余论文。

### 三处容易误读的实验结果

- **R2E-Gym 的多候选筛选结果不应与单次 pass@1 直接并列排名。**
  论文方法明确包含多条候选轨迹与 verifier 筛选。比较时必须统一尝试次数、
  总推理预算和选择流程。[P06 §4][p6full]
- **SWE-EVO 的 Fix Rate 不是单纯“通过测试的比例”。**
  v6 定义中，PASS_TO_PASS 测试有回归时，该实例的严格 Fix Rate 为零；
  GradeRail 目前采用维度加权分和单独的完整通过标志，并未复现该指标。
  [P08 评分方法][p8full]
- **METR 的时长不等于让模型跑多久。**
  TH1.1 还明确区分实际测得与估算的人类时间；不能把一个未标定的 demo
  称为“8 小时能力评测”。[S12][s12]

## 4. 当前开源竞争格局

这是 2026-09-14 的官方能力快照。重点比较功能，不将 GitHub star 数当作技术质量。

| 项目/产品 | 已有能力或关注点 | 新 repo 的合理关系 |
| --- | --- | --- |
| Mechanize / GBA Eval | 具体的高难工程交付评测；已有公开 GBA 评测项目 | 学习任务深度；复刻一个同类模拟器基准需要明确增量。[S03–S05][s3] |
| Terminal-Bench / Challenges | 终端工程任务；Challenges 已覆盖长程、大型代码交付 | 长程任务本身已有竞争；可贡献评分质量工具。[S08][s8] |
| Harbor | 环境、agent 执行、训练/评估流程；当前文档已有 multi-step 和 separate verifier | 计划做原生适配，避免重复基础设施；当前尚未接入。[S10][s10] |
| Prime Intellect / verifiers | 环境与 RL/eval 生态，已有 Environments Hub | 潜在的任务分发与训练集成对象；不是项目合作方。[S11][s11] |
| SWE-smith / SWE-Gym / R2E-Gym | 可执行数据构造、训练、verifier 与推理预算研究 | 借鉴方法；公开训练数据与公开评测数据要分别处理。[P02–P06][p2] |
| SWE-rebench / SWE-EVO | 新鲜任务来源、污染控制、真实软件演进 | 借鉴数据治理与长程验收设计。[P04][p4]、[P08][p8] |
| Daytona | 运行 AI 生成代码的沙箱基础设施 | 属于执行层；不是本项目要重新建设的核心。[官方仓库][s14] |

尤其要避免过时定位：**截至本次检索，“支持多步骤”和“隔离 verifier”
已经不是一个新 repo 独有的差异化**。Terminal-Bench 4.0 的公告甚至已经把
后续 verifier 改进列入里程碑。[S09][s9]、[S10][s10]

## 5. 为什么选 GradeRail？

| 备选方向 | 机会 | 主要阻力 | 选择 |
| --- | --- | --- | --- |
| 通用 RL 环境商城/平台 | 上限大，覆盖广 | 需要算力、分发和长期生态，已有平台 | 首版不选 |
| 再做 GBA/编译器级大型基准 | 技术传播直观 | 重复建设风险高，验证成本大 | 不以此起步 |
| 长程任务运行器 | 使用面较广 | Harbor 等已具备大量基础功能 | 集成现有生态 |
| **工程环境评分器审计** | 产物明确；故障对照可复现；能用于任务评审 | 需要证明跨任务与真实模型失败的迁移价值 | **推荐切口** |

**GradeRail：Test the grader before you train the agent.**

首批目标用户是 RL 环境作者、代码智能体评测维护者、研究实验室的任务审查者。
他们需要回答的具体问题是：这个奖励是否会放过“只返回成功、实际没有提交事务”
之类的实现？评分规则变更后是否误伤了正确解？某个已知缺陷究竟由哪个测试识别？

这不是在宣称发明了 mutation testing。其拟探索的价值，是把行为负对照、
状态恢复验收、评分维度、版本化证据和 agent 实验记录形成易用工作流，
再验证这种审计是否能改善未见工程任务上的评测或训练效果。

## 6. 已落地的首版与边界

首版在本地仓库实现了一个原创 Durable KV 任务，每个 seed 有 15 个场景，
覆盖基础功能、输入验证、事务、CAS、持久化和已确认写入后的进程崩溃恢复。
评分器使用内存 oracle，正确对照使用 SQLite；候选容器不挂载评分器代码。

提供八种行为缺陷对照、JSON 与独立 HTML 报告、代码/评分器/测试实例指纹、
容器镜像 ID、检查点分数面积与回归记录、自动化测试和 CI。
实际验证记录在 [validation.md](validation.md)，示例在
[examples/audit](../examples/audit/index.html)。

当前未实现模型调用、云训练平台、通用任务插件、Harbor/Prime 原生适配、
自动化 RL 训练、真实 frontier leaderboard 或经人类标定的多小时任务。
公开的案例与 seed 不能声称抗污染；八个缺陷被检测到也不能证明任意作弊都能被阻止。

## 7. 怎样才有机会成为专业、有研究价值的项目？

接下来的优先级应是证据质量：

1. **独立性。** 让另一位任务作者提供正确解和未知缺陷；避免评分器只会检测
   自己预先设计的八种错误。
2. **任务深度。** 扩展到存储迁移、持久任务队列、协议兼容性等三个任务家族，
   明确每个版本的需求和回归条件，随后做人类工时标定。
3. **真实失败。** 固定预算收集不同代码智能体的实际错误，检验对照缺陷覆盖了多少。
4. **严格实验。** 对比普通测试、经过审计的 grader、加入私有验收的 grader；
   测量误接受、误拒绝和跨任务表现，而不只展示 reward 上升。
5. **生态接入。** 先完成一个能在真实 Harbor 环境运行的适配，再扩展分发/训练。

可考虑的论文问题是：**对可执行评分器做独立行为审计，能否降低未见任务的
错误接受率，并改善基于其奖励训练的智能体的真实交付质量？**
这是假设，不是首版已经验证的结论。

专业开源形象应来自可重复的结果、准确的范围说明、少量高质量任务、清楚的贡献入口。
项目是否流行，还要看实际使用反馈和维护质量；收购新闻无法替代这些工作。

[s1]: https://www.mechanize.work/mechanize-raises-9-1m/
[s2]: https://www.mechanize.work/press-releases/
[s3]: https://www.mechanize.work/
[s4]: https://gbaeval.com/
[s5]: https://github.com/mechanize-work/gba-eval
[s8]: https://www.tbench.ai/news/terminal-bench-challenges
[s9]: https://www.tbench.ai/news/terminal-bench-4-0
[s10]: https://harborframework.com/docs/task-format
[s11]: https://www.primeintellect.ai/blog/environments
[s12]: https://metr.org/blog/2026-1-29-time-horizon-1-1/
[s13]: https://github.com/SWE-bench/SWE-smith
[s14]: https://github.com/daytonaio/daytona
[s15]: https://www.tbench.ai/news/leaderboard-integrity-update
[s16]: https://www.businessinsider.com/google-mechanize-deal-talent-tech-ai-coding-2026-8
[s17]: https://www.businessinsider.com/google-completes-deal-for-ai-agents-startup-mechanize-2026-9
[p1]: https://arxiv.org/abs/2310.06770
[p2]: https://arxiv.org/abs/2412.21139
[p3]: https://arxiv.org/abs/2504.21798
[p4]: https://arxiv.org/abs/2505.20411
[p5]: https://arxiv.org/abs/2503.14499
[p6]: https://arxiv.org/abs/2504.07164
[p6full]: https://arxiv.org/html/2504.07164v1
[p7]: https://arxiv.org/abs/2411.15114
[p8]: https://arxiv.org/abs/2512.18470
[p8full]: https://arxiv.org/html/2512.18470v6
[p9]: https://arxiv.org/abs/2405.15793
[p10]: https://arxiv.org/abs/2406.12045

# EvalArc launch materials

## Customer description · 中文

EvalArc 是面向 AI 智能体的开源评测与评分器审计工具，帮助团队检查“高分”
背后是否仍存在关键交付缺陷。当前提供代码服务和业务工具两个任务环境，
通过正确实现与 15 种已声明缺陷进行对照，验证事务、异常恢复、工具重试、
幂等写入及最终业务状态。在线演示可逐步查看调用、失败检查和状态变化，
并下载带有运行配置与指纹的原始证据。v0.5 新增 TOML 评测套件、自定义验收规则
和 JUnit 导出：同样是 93.75%、没有完全通过的尝试，宽松规则可允许部分进展，
要求备注检查全部通过的规则则拒绝。页面分别展示任务完成情况和规则决策，
并保留重复评测、版本回归与全部运行证据，适合 PAI 智能体创新场景的评测设计、
验收验证与技术交流。HF Casebook 进一步提供可筛选、可用 Python 读取的公开
证据表，分别保留 167 条用例、6 次重复尝试和 3 项验收作业及其原始记录。
当前为研究预览版，演示使用脚本对照，尚未给出真实大模型
性能或强化学习收益结论。

## English

EvalArc audits the graders behind AI-agent evaluations. Its two executable task
packs compare known-good implementations with 15 declared faults, then preserve
the checks, state changes and reproduction metadata. In the evidence lab, a
support policy scores 93.75% while duplicating a write; a coding artifact scores
92.5% while violating compare-and-swap. Explore why each fails acceptance,
compare the reference, and download the full audit. MIT licensed, CPU-friendly,
and currently a research preview with scripted controls, not model rankings.
Version 0.3 adds runtime readiness checks, standalone evaluation reports, and
matched revision comparisons. Its new showcase exposes a regressed note check
even as two closure improvements raise the score from 90% to 93.75%.
Version 0.4 preserves every attempt of a frozen candidate, with explicit
assessed/invalid denominators, case deadlines and progress events. The browser
exposes six recorded Docker attempts: the reference resolves 3/3; the faulty
policy resolves 0/3 despite three 93.75% scores. No check variation was observed,
and repeated public cases do not establish general model reliability.
Version 0.5 coordinates multi-task TOML suites with explicit per-job gates and
JUnit exports. The new recorded showcase keeps scores and full resolution
separate from configurable acceptance: the same faulty policy meets a
permissive threshold but fails a gate requiring every notes check. Three jobs,
five attempts and the complete configuration remain inspectable. No hosted
CI importer or model-provider integration is claimed.

The Hugging Face Casebook makes 167 audit cases, six repeated attempts and three
suite jobs filterable and readable from Python as separate development
configurations. Each row retains a pointer and hash for its original source
record. This is a tabular view of existing evidence, not additional model trials.

## Entry points

- Source: https://github.com/noteflowai/evalarc
- Demo: https://huggingface.co/spaces/glayguo/evalarc
- Web mirror: https://noteflowai.github.io/evalarc/
- Releases: https://github.com/noteflowai/evalarc/releases
- Data: https://huggingface.co/datasets/glayguo/evalarc-casebook

For each community, write a description appropriate to its rules and audience.
Disclose maintainer affiliation. Do not present pending editorial submissions
as an endorsement or listing.

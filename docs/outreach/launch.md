# EvalArc launch materials

## Customer description · 中文

EvalArc 是面向 AI 智能体的开源评测与评分器审计工具，帮助团队检查“高分”
背后是否仍存在关键交付缺陷。当前提供代码服务和业务工具两个任务环境，
通过正确实现与 15 种已声明缺陷进行对照，验证事务、异常恢复、工具重试、
幂等写入及最终业务状态。在线演示可逐步查看调用、失败检查和状态变化，
并下载带有运行配置与指纹的原始证据，适合 PAI 智能体创新场景的评测设计、
验收验证与技术交流。当前为研究预览版，演示使用脚本对照，尚未给出真实大模型
性能或强化学习收益结论。

## English

EvalArc audits the graders behind AI-agent evaluations. Its two executable task
packs compare known-good implementations with 15 declared faults, then preserve
the checks, state changes and reproduction metadata. In the evidence lab, a
support policy scores 93.75% while duplicating a write; a coding artifact scores
92.5% while violating compare-and-swap. Explore why each fails acceptance,
compare the reference, and download the full audit. MIT licensed, CPU-friendly,
and currently a research preview with scripted controls, not model rankings.

## Entry points

- Source: https://github.com/noteflowai/evalarc
- Demo: https://huggingface.co/spaces/glayguo/evalarc
- Web mirror: https://noteflowai.github.io/evalarc/
- Releases: https://github.com/noteflowai/evalarc/releases

For each community, write a description appropriate to its rules and audience.
Disclose maintainer affiliation. Do not present pending editorial submissions
as an endorsement or listing.

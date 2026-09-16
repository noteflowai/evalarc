# EvalArc launch materials

## Customer description · 中文

EvalArc 帮助 Agent 开发团队找出更高评分背后的关键退步：对照变更前后的检查，定位已记录的工具动作，并交付可离线复核的验收证据。公开演示中，分数从 90% 提高到 93.75%，重试却多写了一条备注；用户可以直接查看原因，再用发布的 Python wheel 在本机复算。适合 PAI 智能体场景的评测设计、发布复核与技术交流。当前为 MIT 研究预览，展示案例来自脚本对照，不代表客户生产效果或模型排名。

## English

EvalArc helps agent developers find regressions hidden by a better average
score. Compare changed checks, follow recorded tool actions, and hand off
evidence another developer can verify offline. In the public example, the
score rises from 90% to 93.75% while a retry duplicates a note. Explore the
failure without installing anything, then recompute the comparison using the
published Python wheel. MIT research preview; the featured case is a scripted
control, not a customer incident or a model ranking.

## One useful invitation

Have two agent revisions you need to review? Try one comparison and tell us
where the first review helped or got stuck. A minimal redacted example is
enough. Installation failures and unsupported export formats are useful
feedback too.

Use the [first-use form](https://github.com/noteflowai/evalarc/issues/new?template=first-use.yml).
An invitation is not evidence of independent adoption.

## Entry points

- [Recorded regression](https://noteflowai.github.io/evalarc/#regression)
- [First local review](https://github.com/noteflowai/evalarc/blob/main/docs/first-review.md)
- [首次本地复核](https://github.com/noteflowai/evalarc/blob/main/docs/first-review.zh-CN.md)
- [Hugging Face Space](https://huggingface.co/spaces/glayguo/evalarc)
- [Source](https://github.com/noteflowai/evalarc)
- [Release files](https://github.com/noteflowai/evalarc/releases/tag/v0.12.1)

Use one relevant finding for each audience. Maintain the existing weekly,
HelloGitHub and HF introductions instead of appending a release chronology.
Disclose maintainer affiliation, follow channel rules, and distinguish pending
editorial review from acceptance.

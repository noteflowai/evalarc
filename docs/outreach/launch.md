# EvalArc launch materials

## Customer description · 中文

0.7.1 把证据讨论定位到具体案例和步骤：接收者打开同一观察点，键盘可从详情返回列表；某个分区加载失败时单独重试，其余记录继续可用。已验证桌面、手机和 320 像素窄屏，便于客户现场演示与远程复核。

新版 0.7 增加独立交付复核：收到单次、重复或前后对照报告后，可在不执行候选
程序、不连接 Docker 的情况下重算已记录结果，并列出输入文件指纹。
“报告内部一致”与“任务全部通过”分别判断，适合团队交接、客户复核和 CI 证据检查。
这是对已记录检查的验证，不替代重新运行评分器，也不认证报告发布者。


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
支持生成 Python／JavaScript 候选，并通过独立实现验证同一任务约定，
可在统一套件中为不同语言明确指定运行镜像。
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

Version 0.6 supplies Python and JavaScript starters and independent references
for both tasks. The Node audits exercise the same declared faults, and a
mixed-language suite retains three resolved jobs. Shared task contracts do not
establish a language ranking.

## Entry points

- Source: https://github.com/noteflowai/evalarc
- Demo: https://huggingface.co/spaces/glayguo/evalarc
- Web mirror: https://noteflowai.github.io/evalarc/
- Releases: https://github.com/noteflowai/evalarc/releases
- Data: https://huggingface.co/datasets/glayguo/evalarc-casebook

For each community, write a description appropriate to its rules and audience.
Disclose maintainer affiliation. Do not present pending editorial submissions
as an endorsement or listing.

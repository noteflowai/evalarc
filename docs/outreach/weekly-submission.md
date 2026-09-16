维护者自荐：**EvalArc——分数提高，Agent 就更可靠了吗？**

一个已保存的对照案例中，分数从 90% 提高到 93.75%，两项检查改善，但重试多写了一条备注。EvalArc 可以并排查看退步的检查、逐步定位工具动作，并下载原始证据在本机复算。

**先看一个问题，再决定是否适合自己的项目：**

1. [打开免安装演示](https://noteflowai.github.io/evalarc/#regression)，查看 `retry-after-commit`。
2. 检查相同分数为什么通过宽松规则、却被严格备注规则拒绝。
3. 按[首次复核指南](https://github.com/noteflowai/evalarc/blob/main/docs/first-review.zh-CN.md)安装发布的 wheel，重建对照报告；无需 Docker、GPU 或模型密钥。

适合需要复查 Agent 变更与发布验收的开发者。已有自己的记录时，可比较 EvalArc 评测，或按照受限格式导入保存的 AgentCore Evaluate 结果。欢迎反馈首次使用的卡点，不需要提供私有数据。

项目：https://github.com/noteflowai/evalarc
Hugging Face：https://huggingface.co/spaces/glayguo/evalarc

![分数提高，记录中的检查却退步](https://raw.githubusercontent.com/noteflowai/evalarc/main/docs/assets/first-review.gif)

本账号为维护者，项目与 AI 结对开发，MIT 许可，处于研究预览。此案例是已保存的脚本 Docker 对照，不是客户事故或模型排名；离线复核不认证生产者或重新运行评分器。云端导入示例采用合成评分，未完成实时 AgentCore 评测。

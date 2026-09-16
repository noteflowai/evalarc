### 项目地址

https://github.com/noteflowai/evalarc

### 类别

人工智能

### 项目标题

找出更高评分背后的 Agent 回归

### 项目描述

EvalArc 是开源的 Agent 评测复核工具。交互案例展示分数从 90% 升到 93.75%，重试却多写了一条备注。可对照失败检查、定位工具动作，并下载证据在本机复算。适合检查 Agent 变更和验收规则；演示免安装，本地复核无需 Docker、GPU 或模型密钥。当前为研究预览，示例来自脚本对照。

### 亮点

- 用一个具体失败解释分数、验收与任务完成的区别。
- 发布 wheel 与原始记录，可按中英文指南复算结果。
- 可以比较自己的 EvalArc 评测，或按受限格式导入保存的运行记录。

### 首次体验

[查看失败案例](https://noteflowai.github.io/evalarc/#regression) ·
[首次本地复核](https://github.com/noteflowai/evalarc/blob/main/docs/first-review.zh-CN.md) ·
[Hugging Face](https://huggingface.co/spaces/glayguo/evalarc)

按指南安装并解压记录后：

```sh
evalarc verify evalarc-evidence-explorer/comparison --json
# 退出 0：记录一致。
evalarc compare evalarc-evidence-explorer/comparison/baseline.json \
  evalarc-evidence-explorer/comparison/current.json --output comparison-review
# 退出 1：一项检查退步，即使总分提高。
```

### 截图或演示视频

![分数提高，记录中的检查却退步](https://raw.githubusercontent.com/noteflowai/evalarc/main/docs/assets/first-review.gif)

本账号为维护者，项目与 AI 结对开发，MIT 许可。此案例是脚本 Docker 对照，不是客户效果或模型排名；离线复核不认证生产者或重新执行评分器。云端导入样例采用合成评分，未完成实时 AgentCore 评测。

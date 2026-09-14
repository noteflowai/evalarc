### 项目地址

https://github.com/noteflowai/evalarc

### 类别

人工智能

### 项目标题

分享具体失败证据，检查智能体评分器的盲点

### 项目描述

EvalArc 是面向 AI 智能体的开源评测与验收工具。支持 Python／JavaScript 候选、TOML 套件、JUnit 和离线报告复核，保留每轮原始记录。交互实验室展示高分仍违反关键业务约束的案例；新版可分享到具体任务、用例与调用步骤，并独立重试加载失败的分区。提供可筛选 HF Casebook 和中英文文档，现有演示为脚本对照。

### 亮点

- **把讨论定位到同一步**：0.7.1 的 Copy evidence link 保存任务、对照实现、种子、案例与 trace 步骤。接收者打开同一观察点，键盘可从详情返回案例列表；受限剪贴板有手动复制入口。
- **失败可恢复**：suite、重复尝试、前后比较和任务包可以分别重试；一个任务包不可用时仍可检查另一个。页面经过 320／390／1440 像素与键盘路径验证。
- **高分不代表完成**：工单策略得 93.75% 却重复写备注；代码实现得 92.5% 却混淆 JSON true 与 1。可检查全部 15 种声明缺陷，以及三项 suite 作业、六条重复尝试和 167 条审计用例的数据表。
- **可复核交付**：`evalarc verify` 不执行候选代码，重算单次、重复和对照报告；`--require-resolved` 另行要求完整通过。Python／JavaScript 参考实现共享任务约定。

本账号为维护者，项目与 AI 结对开发，采用 MIT 许可，处于研究预览阶段。现有展示来自已保存的公开开发任务和脚本 Docker 对照，不提供真实大模型排名或 RL 收益结论。离线一致性校验不等于重新运行评分器；suite 级规则和 JUnit 暂不在 verify 的核验范围。

### 示例代码

安装发布的 Python wheel 后，核对收到的重复评测目录，无需 Docker 或 Node：

```sh
evalarc verify received/repetition --json

# Also require valid, fully resolved results:
evalarc verify received/repetition --json --require-resolved
```

### 截图或演示视频

在线体验：https://huggingface.co/spaces/glayguo/evalarc
版本：https://github.com/noteflowai/evalarc/releases/tag/v0.7.1

![分享具体失败证据，检查智能体评分器的盲点](https://github.com/noteflowai/evalarc/raw/main/docs/assets/suite-lab.png)

维护者自荐：**evalarc**。EvalArc 是面向 AI 智能体的开源评测与验收工具。支持 Python／JavaScript 候选、TOML 套件、JUnit 和离线报告复核，保留每轮原始记录。交互实验室展示高分仍违反关键业务约束的案例；0.8.0 可下载完整套件证据，并离线复算原始配置、执行计划、验收规则和 JUnit；浏览器可分享到具体调用步骤。提供可筛选 HF Casebook 和中英文文档，现有演示为脚本对照。

在线体验：https://huggingface.co/spaces/glayguo/evalarc

- **把讨论定位到同一步**： Copy evidence link 保存任务、对照实现、种子、案例与 trace 步骤。接收者打开同一观察点，键盘可从详情返回案例列表；受限剪贴板有手动复制入口。
- **失败可恢复**：suite、重复尝试、前后比较和任务包可以分别重试；一个任务包不可用时仍可检查另一个。页面经过 320／390／1440 像素与键盘路径验证。
- **高分不代表完成**：工单策略得 93.75% 却重复写备注；代码实现得 92.5% 却混淆 JSON true 与 1。可检查全部 15 种声明缺陷，以及三项 suite 作业、六条重复尝试和 167 条审计用例的数据表。
- **可复核交付**：`evalarc verify` 不执行候选代码，重算单次、重复、对照和完整套件报告，包括 TOML、plan、五次尝试与 JUnit；`--require-accepted` 检查配置的验收规则，`--require-resolved` 另行要求任务完整通过。Python／JavaScript 参考实现共享任务约定。

```sh
evalarc verify suite-evidence --json

# Require every configured suite gate:
evalarc verify suite-evidence --json --require-accepted
```

安装发布的 Python wheel，从首页下载 suite-evidence.zip 并解压后，无需 Docker 或 Node 即可核验；默认退出 0 表示证据一致，添加 --require-accepted 退出 1 表示严格备注规则拒绝该结果：

项目：https://github.com/noteflowai/evalarc
版本：https://github.com/noteflowai/evalarc/releases/tag/v0.8.0

![分享具体失败证据，检查智能体评分器的盲点](https://github.com/noteflowai/evalarc/raw/main/docs/assets/suite-lab.png)

本账号为维护者，项目与 AI 结对开发，采用 MIT 许可，处于研究预览阶段。现有展示来自已保存的公开开发任务和脚本 Docker 对照，不提供真实大模型排名或 RL 收益结论。离线一致性校验不等于重新运行评分器，也不认证报告作者；原始候选路径与计时仍是报告元数据。

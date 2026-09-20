# 第一次用 EvalArc 复核

先看一个已记录的失败，在本机复算，再换成自己的证据。下列流程使用已发布的
**0.13.0 复核工具**与原始 **0.12.1 证据快照**。工具和证据分别固定版本，
更新工具时保留记录输入。需要 Linux、Python 3.11+ 和用于下载的 `curl`。
审阅不需要克隆源码、Docker、Node、GPU 或模型密钥。

## 1. 先看问题

[打开版本对照](https://noteflowai.github.io/evalarc/#regression)：分数从
**90% 升到 93.75%**，两项关闭检查改善，但备注检查退步。
选择 `retry-after-commit`，查看多写的那条备注。

这是脚本对照在 Docker 中运行后保存的记录，用于展示评分器与复核流程，
不是客户事故或模型排名。

## 2. 安装复核工具

在新文件夹中运行，避免混用已有下载和输出：

```bash
mkdir evalarc-first-review
cd evalarc-first-review
python3 -m venv .venv
. .venv/bin/activate
python -m pip install "https://github.com/noteflowai/evalarc/releases/download/v0.13.0/evalarc-0.13.0-py3-none-any.whl#sha256=1a3845cb92b594364f83a50307ad6c3b96c4504033a41d41900b9d1390ca803b"
evalarc --version
```

预期输出 `EvalArc 0.13.0`。安装地址固定了发布版本及 SHA-256，
包本身没有第三方运行时依赖；不依赖 PyPI 存在同名包。

## 3. 复算这次退步

```bash
curl --fail --location \
  https://github.com/noteflowai/evalarc/releases/download/v0.12.1/evalarc-evidence-explorer.zip \
  --output evalarc-evidence-explorer.zip
python -m zipfile -e evalarc-evidence-explorer.zip .
evalarc verify evalarc-evidence-explorer/comparison --json
evalarc compare evalarc-evidence-explorer/comparison/baseline.json \
  evalarc-evidence-explorer/comparison/current.json \
  --output comparison-review
```

复核命令退出 **0**，表示记录内部一致；对照命令退出 **1**，表示一项检查退步，
即使总分提高。用浏览器直接打开 `comparison-review/index.html`，可以离线查看。
重复运行时换一个输出文件夹。

此发布 ZIP 的 SHA-256 为
`4ac78211c718dc930a0091227e0d4d9baf0543e05222792d82e05cb44362a073`。
完整校验清单见[发布页](https://github.com/noteflowai/evalarc/releases/tag/v0.12.1)
的 `SHA256SUMS`。

## 4. 检查验收结论

```bash
evalarc verify evalarc-evidence-explorer/suite --json
evalarc verify evalarc-evidence-explorer/suite --json --require-accepted
```

第一条命令退出 **0**，表示证据一致；第二条退出 **1**，因为严格备注规则拒绝了
该策略。整个套件中 **2/3 作业被规则接受，1/3 完全完成**。宽松规则允许部分进展，
不代表所有任务检查通过。

打开 `evalarc-evidence-explorer/suite/index.html` 查看规则。交付时保留原始套件
及 `suite/junit.xml`。此流程复算记录，不重新执行候选程序，也不认证生产者身份；
详见[复核范围](verification.md)。

## 5. 换成自己的证据

| 已有材料 | 下一步 |
| --- | --- |
| 两份 EvalArc 评测 | 替换 `compare` 的输入 JSON；任务、评分器、案例与运行条件必须匹配。[操作指南](workflow.md) |
| Strands Evals 案例与观测状态 | 用原生 SDK 的状态规则和逐项通过结果检查回归。[运行示例](../examples/strands-state-review/README.zh-CN.md) |
| AgentCore Evaluate 结果与运行 spans | 按受限输入约定整理后离线导入，区分拒绝、零分与缺少评判。[导出到审阅](agentcore-first-review.md) |
| 待执行的代码或工具策略 | 使用 Docker 后端执行任务审计或候选评测。[运行审计](../README.md#run-an-audit) |
| 同一记录上的多次评判 | 分别检查分数变化与结论翻转。[中文指南](judge-stability.zh-CN.md) |
| 最终文件正确但运行行为存疑 | 从发布证据包复核临时写入和服务请求。[本地行为复核](behavior-first-review.zh-CN.md) |

欢迎提交[首次使用反馈](https://github.com/noteflowai/evalarc/issues/new?template=first-use.yml)：
你原本要检查什么、在哪一步卡住、结果是否帮助做出决定。安装失败同样有价值。
只需最小脱敏样例，不必提供客户数据、私有提示词或凭证。该入口用于收集反馈，
不代表已经获得独立用户验证。

# 同一份执行记录，多次评判是否一致？

EvalArc 0.12 新增 `trace-stability`，离线比较同一份执行记录的多次评判。
已有的 `evalarc repeat` 会重新执行候选程序；本功能固定执行记录，只比较保存的
评判结果。两者用于检查不同来源的波动，不能混成一个成功率。

```sh
evalarc trace-stability \
  examples/judge-stability/judge-1.json \
  examples/judge-stability/judge-2.json \
  examples/judge-stability/judge-3.json \
  --output runs/judge-review
evalarc trace-stability-verify runs/judge-review
```

打开输出目录的 `index.html`，可筛选结论翻转或证据不完整的目标，查看每次分数、
解释和原始文件。报告不依赖网络。首页展示五个人工构造的案例、三组模拟评判；
它们不是模型或 AWS 服务实测结果。

输入沿用 [Trace Workbench 协议](trace-workbench.md)。每组需要独立的 `run_id`，
在此命令中表示评判次数，而不是新的 Agent 执行。只有 `run_id`、
`provenance.description` 和各案例的 `evaluation_response` 可以变化；其余记录、
模型配置、测试集、评估器定义与版本、技能回执、session/trace/span 都必须相同。
请在评估器 revision 或附加字段记录实际使用的裁判模型、提示词与配置；只写一个
内置评估器名称不能固定服务端版本。调用方声明的 ID 也不能证明调用独立性。

报告逐目标保留分母，不跨评估维度平均分数：

- 分数变化：至少两次已评判的数值或分类标签不同。
- 结论翻转：出现过通过与拒绝；即使还缺少某次结果，也同时保留这个发现。
- 结论一致：所有预期结果都已评判，且通过/拒绝结论一致。三次都拒绝仍然是拒绝。
- 证据不完整：存在未评判的预期结果；全部缺失也不能算一致。
- 不适用：声明完整观测且不存在技能目标时，不计入覆盖分母。

合法输入默认退出 0。使用 `--require-consistent-gates` 时：
0 表示结果完整且无通过/拒绝翻转，1 表示完整但有翻转，2 表示不完整或输入非法。
这个门槛检查评判一致性，不要求任务通过：全部拒绝也退出 0。任务验收应另用
`trace-import --require-accepted` 或 suite 的相应门槛。

原始输入逐字节保留，离线复核会重新计算报告并比对内容和摘要。它不验证 HTML、
作者身份或实际任务结果，也不执行模型或上传数据。没有独立可信摘要时，同时替换
输入和报告不能被当作伪造检测。

限额为 2–20 组、单输入 4 MiB、总输入 16 MiB、规范化报告 32 MiB，另沿用现有
案例与 span 限额。输出必须使用新目录。

该功能提供描述性诊断；人工校准样本、置信区间、AWS 在线实测和客户 PAI 接入
仍需另外完成。研究来源及完整说明见 [英文文档](judge-stability.md)。

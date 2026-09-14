# 运行、查看与比较评测

EvalArc v0.3 完善试用流程，两个任务的协议与评分规则沿用 v0.2。

## 先检查环境

```bash
evalarc --version
evalarc tasks --json
evalarc doctor
```

`doctor` 检查主机与 Docker 镜像是否可用，不拉取镜像，也不启动候选程序。
可以传入与正式运行相同的 `--image`、`--docker-command` 或 `EVALARC_DOCKER`。

本机候选程序还可以检查启动命令：

```bash
evalarc doctor --backend local --task support-routing \
  --candidate examples/support-node --json
```

它检查候选快照、命令配置和可执行文件。Docker 模式只检查镜像，不验证镜像内部
是否存在某个可执行文件，该项会明确显示 `not_checked`。

## 查看单次结果

```bash
evalarc init workspace/support --task support-routing --reference
evalarc evaluate workspace/support --task support-routing --output runs/support-001
```

现在每次评测都会输出 `evaluation.json` 和可独立打开的 `index.html`。
HTML 包含各维度分数、逐项通过／失败结果和可展开的证据；工单场景包含工具调用
及状态变化。环境故障显示为未评估，分数为 `null`。

[查看记录示例](../examples/evaluation/index.html)。

## 检查修改是否造成退步

固定任务、seed 和运行条件，分别保存修改前后的结果：

```bash
evalarc compare runs/baseline/evaluation.json runs/current/evaluation.json \
  --output runs/comparison-001
```

工具先核对任务、评分器、测试实例、运行参数、维度权重和检查覆盖范围，再逐项
比较结果。它也会核对 JSON 内部的分数、通过数和状态是否一致，拒绝矛盾记录、
重复键、非有限数值及超过 64 MiB 的输入。

**总分上升也可能存在回归。** 示例中，分数从 0.9 升至 0.9375，但一个原本通过的
备注检查退步了；比较仍会报告该问题，并返回退出码 `1`。
[查看比较报告](../examples/comparison/index.html)。

比较目录附带前后两份完整证据。没有回归只表示已观察到的检查没有退步，
并不等于所有任务都已完成。校验 JSON 一致性也不能证明数据提供者可信。

## 保留每次运行的证据

`evaluate`、`audit`、`compare` 必须使用新的输出目录；即使目录为空也不覆盖。
重复试验请使用 `runs/support-002` 等新路径。评测输出不能放在候选程序目录中。
`trajectory` 同样拒绝覆盖已有文件。

运行文件先暂存，完整生成后再一起发布。配置错误会清理未发布的结果；任务失败
或环境故障仍会保存完整报告。主机被强行终止时可能留下空目录或暂存文件，
应先检查，再手动清理。

`evaluate`／`audit` 的退出码为：`0` 成功、`1` 评测未通过、`2` 无效运行或配置错误。
`compare` 为：`0` 无检查回归、`1` 存在回归、`2` 输入不兼容或错误。
`doctor` 为：`0` 可检查的项目通过、`1` 有检查失败、`2` 命令参数错误。

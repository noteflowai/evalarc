# 重复评测与执行证据

`evalarc repeat` 固定一份候选快照，在相同公开场景上运行多轮评测。每轮重新创建
工作目录、进程和场景状态；Durable KV 同一场景内的重启仍共享持久化状态。
两个任务包及已有的候选命令配置均可使用。

```bash
evalarc init workspace/repeated-support --task support-routing --reference
evalarc repeat workspace/repeated-support --task support-routing \
  --seeds 17 41 97 --attempts 3 --case-timeout 60 --progress \
  --output runs/repeated-support
```

默认使用 Docker，需预先准备镜像。仓库自带的可信策略也可加上
`--backend local --trust-local`。候选目录在第一轮前复制；轮次间修改原始目录
不会改变后续评测的提交。输出目录必须是新路径。

## 如何读结果

HTML 汇总链接到每一轮的完整 JSON 和 HTML 证据，显示：

- 计划、完成、有效、无效以及全部检查通过的轮数。
- 有效轮次的平均分与分数范围；没有有效轮次时为 `null`。
- 每个场景、每项检查的通过次数、有效观察次数和通过率。
- 同时出现过成功与失败的场景数、检查数。

只要任一场景发生环境异常，该轮就没有有效总分。重复执行在首个无效轮次之后
停止，并保留计划与完成轮数，避免把未执行部分当作成功或失败。
无效轮次中已有效评估的其他场景，仍计入对应场景及检查的分母；整轮不计入
总分均值或完整通过次数。

`all_attempts_resolved` 仅在所有计划轮次都完成且全部检查通过时为真。
不选取“最好的一次”，不自动重试无效轮次，也不支持断点续跑。
同一场景可能每轮都失败，但失败的检查不同，因此还要看 `variable_checks`。

这些是固定公开场景上的描述性结果。多跑几轮不等于扩大任务覆盖；不提供
独立性假设、置信区间、显著性检验或面向未知任务的总体成功率。
脚本参考策略通过，只证明本次功能对照通过。

## 时间预算与诊断

`--timeout` 默认每次协议交换 10 秒；`--case-timeout` 默认每个场景 60 秒，
共享于该场景内的全部进程重启，进程启动及重启间经过的时间也消耗预算。
新场景获得新预算，参数必须为有限正数。

超出协议预算是已评估的智能体错误，检查结果遵循各任务已有评分规则。
清理有独立宽限：Docker 删除最多等待 20 秒，本机进程等待最多 5 秒。
清理异常会让场景变为未评估，并继续尽可能释放本机进程和管道。
预算不是宿主机崩溃、强制杀进程后的资源回收保证。

每个场景的 `processes` 包含退出码、已捕获输出字节数、最后 2048 字节的
已捕获 stderr；UTF-8 不完整片段会替换解码。这是受限诊断，不能代替完整
进程日志。stdout/stderr 的合计输出限制仍按进程会话执行。

## 进度与输出

汇总文件为 `repetition.json`、`index.html`，每轮记录位于
`attempts/0001/evaluation.json`、`attempts/0001/index.html` 等路径。

`evaluate`、`audit`、`repeat` 都保存 `events.jsonl`。加 `--progress` 后，同一批
JSONL 事件实时写入 stderr；终端摘要保留在 stdout。事件由宿主生成，包含时间、
场景、轮次或对照名称及完成状态，不夹带候选的 stdout/stderr。

取消操作会删除尚未发布的输出。若要保留取消前进度，可将 stderr 重定向到
候选目录和输出目录以外：

```bash
evalarc repeat workspace/repeated-support --task support-routing \
  --attempts 3 --progress --output runs/repeat-02 2> repeat-02.events.jsonl
```

正常处理的取消或失败会在外部流中留下 `run_cancelled` 或 `run_error`。
退出码：全部计划轮次通过为 `0`；均有效但存在失败为 `1`；无效或配置错误为
`2`；用户取消为 `130`。强制终止或宿主丢失可能留下临时文件及不完整事件流。

任务合同仍为 v0.1.0，评测证据仍为 v2；运行预算和评分源码指纹已变化。
旧文件可读，但 v0.3 与 v0.4 结果不能直接混合比较，需要在相同版本和配置下重跑。
详见[迁移说明](migration.md)和[本轮验证记录](validation-v0.4.md)。

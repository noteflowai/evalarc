# 用自己的命令运行爬山调优循环

`evalarc hillclimb-run` 驱动 [`hillclimb-review`](hillclimb-review.zh-CN.md) 事后复核的那个循环。
你提供两条命令：一条评测工作区并写出 Inspect AI、promptfoo 或 JUnit 结果；另一条提出改动（通常
用你自己的密钥调用模型）。EvalArc 从不调用模型，只决定每条命令能看到什么、能改什么，以及是否保留
每次改动。[English](hillclimb-run.md)。

```bash
cp -r examples/hillclimb-run /tmp/climb-example   # 循环会修改工作区
evalarc hillclimb-run /tmp/climb-example/hillclimb.toml --output runs/climb --trust-local
```

[示例](../examples/hillclimb-run/README.md)是脚本化的：`propose.py` 回放五条预先声明的改动，
不调用模型。结果依次为：保留、`rollback_pasted_case`、`rollback_overfit`（随后停滞分类）、
`no_change`、保留，最终建议 `merge`。

## 配置

`hillclimb.toml` 中的路径相对于该文件：`workspace`、`allow`（propose 可修改的文件 glob）、
`held_out`（拆分文件）、`evaluate`、`propose`（参数数组，不经 shell，在工作区内以你的环境变量运行）、
`objective`（`quality` 或 `cost`）、`max_iterations`、`stall_after`、`timeout_seconds`，以及可选的
`cost_metric`、`max_cost_ratio`、`min_effect`、`result_suffix`、`format`、`threshold`、
`leak_min_chars`、`paste_check`。占位符：`{python}`、`{workspace}`；evaluate 用 `{output}`；
propose 用 `{failures}`、`{allowed}`、`{iteration}`。

## 每一轮

1. EvalArc 写出 `steps/NN/tuning-failures.json`：最近保留结果中失败的**调优**用例，含输入、参考
   答案、输出、评分依据和根因分类；绝不包含留出用例。
2. 运行 propose。若它改动了 `allow` 之外的任何工作区文件（包括 `.git`；只忽略 `__pycache__` 等
   缓存目录），循环会恢复允许文件、删除它新建的文件并停止（退出 2），列出被改动的既有文件供你恢复；
   命令失败则记为 `propose_failed`。允许路径若被替换为符号链接，会恢复为保留版本的内容。
3. 对允许文件的补丁保存为 `patch.diff`。评测前，若新增行含留出用例文本则 `rollback_leakage`；
   含调优用例文本（粘贴失败样例而非修复根因）则 `rollback_pasted_case`；只检查长度不少于
   `leak_min_chars` 的记录字符串，像 `billing` 这样的短答案不会被发现；补丁为空则 `no_change`。
4. 否则运行 evaluate，按 hillclimb-review 规则与最近保留结果比较：`keep`、`rollback_regression`、
   `rollback_overfit` 或 `rollback_no_gain`；回滚时恢复文件。
5. 连续 `stall_after` 轮未保留时分类剩余调优失败；若调优余量小于可分辨变化，则停止
   （`stopped_below_noise`）。

结束时工作区为最后保留的版本，`original/` 保存初始文件，`final.diff` 为净改动；`hillclimb.json`、
`summary.md`、`index.html` 是对所有已评测结果的复核报告。退出 0 表示建议合并，1 表示不建议，
2 表示配置、命令或安全检查失败。`loop.json` 记录每一步，失败时也会写出。

## 安全

两条命令都以你的权限和环境变量在主机上运行，因此必须加 `--trust-local`。`allow` 检查比较每次
propose 前后的工作区，但不是沙箱：它看不到工作区之外的改动，也无法撤销对既有文件的修改。请在副本或干净的 git 检出上运行，不要把留出数据放进工作区，
合并前审阅 `final.diff`。

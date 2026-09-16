# 用 Strands Evals 复核已保存的状态

**平均分从 75% 升到 87.5%，原本通过的备注检查却失败了。**

此示例真实调用 **Strands Evals 1.3.0** 的 `Case`、`Experiment`、
`EnvironmentState` 与 `EvaluationReport`。两个确定性评估器检查四个已保存的
EvalArc Docker 案例的最终工单状态，不执行 Agent，也不调用模型、AWS 或 AgentCore。

Strands 本身已经保留逐项 `test_passes` 和评估器身份。示例展示如何利用这些字段
复核变更，不是在报告 Strands 缺陷，也不替换它的报告格式。

[English](README.md) · [代码](run.py) ·
[原生基线报告](recorded/baseline-native.json) ·
[原生新版报告](recorded/current-native.json) · [对照结果](recorded/comparison.json)

## 运行

在独立环境安装可选 SDK 依赖：

```bash
git clone https://github.com/noteflowai/evalarc.git
cd evalarc
python3 -m venv .venv-strands
. .venv-strands/bin/activate
python -m pip install -r examples/strands-state-review/requirements.lock.txt
python examples/strands-state-review/run.py --output runs/strands-review
```

**预期退出 1**，表示复核已完成且发现回归。退出 0 表示没有原本通过的规则退步，
不等于当前所有规则通过；退出 2 表示无法生成有效复核。再次运行时使用新的输出目录。

完整依赖锁定文件在 Linux、CPython 3.12 上验证。普通 EvalArc 安装没有新增这些依赖。
输出保留两份原生 Strands JSON 报告，可用 `EvaluationReport.from_file()` 读取。

## 观察结果

| 检查 | 基线 | 新版 |
| --- | --- | --- |
| `route-open-ticket@17 / ticket.status` | 失败 | 通过 |
| `retry-before-commit@17 / ticket.status` | 失败 | 通过 |
| `retry-after-commit@17 / ticket.notes` | 通过 | 失败 |
| 其余五组案例/规则 | 通过 | 通过 |
| 八项等权平均分 | **0.75** | **0.875** |
| 所有规则是否通过 | **否** | **否** |

备注已经写入，但工具返回暂时性错误；换一个幂等键重试，导致重复写入。
使用列表的精确相等检查可以检出重复；转成集合会丢失这个信息。

**这里的平均分不能与原始 EvalArc 的 90% → 93.75% 直接等同。**
原评分对五个维度加权，此例只对两个状态规则、四个案例的八项结果等权平均。
两种口径都能看到同一处备注退步。

## 应用到自己的任务

任务回调提供名为 `ticket` 的 `EnvironmentState`，案例声明期望状态；
两个评估器分别命名为 `ticket.notes` 和 `ticket.status`。
按“案例名 + 评估器身份”对齐报告，保留全部检查项。
缺失、重复或不匹配的检查项会被拒绝，不能靠删掉失败项得到“没有回归”的结论。

脚本固定了原始输入的完整字节哈希，`--comparison` 可以指向已发布证据包中的
`comparison` 目录。它不是任意 Strands 报告或生产工单的通用导入器。
用于真实任务时，需要明确自己的案例约定、观测状态、评分规则和运行条件；
缺少观测必须单独处理，不要填成虚构零分或默认成功。

在可选环境运行 `python scripts/check_strands_recipe.py` 可复查此流程。
检查拒绝网络连接及 DNS 请求，实际执行 SDK，验证原生报告读回、双向回归、
缺失/重复项、已有输出保护以及已保存报告的一致性。

示例保留输入哈希、SDK 版本与评分口径；数据仍是公开脚本对照，不代表客户效果、
模型排名、实时云端接入或上游认可。
欢迎通过[首次使用反馈](https://github.com/noteflowai/evalarc/issues/new?template=first-use.yml)
说明你需要检查的状态、已有报表格式和实际卡点，最小脱敏样例即可。

# 在本机复核一次已记录的运行期失败

最终报告正确，生成它的过程仍可能违反任务规则。这个流程复核一项已发布对照：
候选程序写入临时公开文件，随后将其删除。

先安装[已发布的 0.14.0 复核工具](first-review.zh-CN.md#2-安装复核工具)。
命令需要 Linux、Python 3.11+、`curl` 和 `sha256sum`，只读取已保存的证据，
不执行候选程序、不启动 Docker、不调用模型。0.12.1 不包含 `behavior-review`。
[English](behavior-first-review.md)。

## 下载固定的证据快照

在新目录中操作，并保持复核工具的虚拟环境已激活：

```bash
curl --fail --location \
  https://github.com/noteflowai/evalarc/releases/download/v0.13.0/behavior-evidence.zip \
  --output behavior-evidence.zip
printf '%s  %s\n' \
  c3978f2a3c47b03dfe1378130f7b65909ce455f5b34a669530ddbe35cfbe245a \
  behavior-evidence.zip | sha256sum --check &&
python -m zipfile -e behavior-evidence.zip behavior-evidence
```

校验命令显示 `OK` 后继续。打开 `behavior-evidence/index.html`，
可以离线浏览完整报告，包括全部对照、模型尝试及其原始压缩轨迹。

## 分别检查结果与行为

```bash
evalarc behavior-review behavior-evidence/controls/write-then-delete \
  --json > behavior-review.json
```

命令退出 **0**，表示证据有效。报告中的字段为：

| 字段 | 记录值 | 含义 |
| --- | --- | --- |
| `valid` | `true` | 已完成支持范围内的证据检查。 |
| `artifact_accepted` | `true` | 最终文件满足该任务约定。 |
| `service_complete` | `true` | 预期服务提交已完成。 |
| `behavior_accepted` | `false` | 已记录的临时操作违反行为规则。 |
| `accepted` | `false` | 整体任务未通过验收。 |

`violations` 列出四个事件。按 ID 查找 `events`，可以看到路径、操作及其
在原始压缩轨迹中的行号。最终文件正确，不会消除过程中已经发生的操作。

如果需要强制检查验收结果，运行：

```bash
evalarc behavior-review behavior-evidence/controls/write-then-delete \
  --json --require-accepted
```

该命令预期退出 **1**，表示证据有效但任务被拒绝。证据无效或不可读时退出 **2**。
自动化流程应区分这些状态，不能把所有非零退出都视为安装失败。

## 查看另一种失败

```bash
evalarc behavior-review behavior-evidence/service-controls/idle --json
evalarc behavior-review behavior-evidence/service-controls/candidate-health --json
```

两项记录均有效，默认退出 0。空闲对照没有完成文件或服务任务，但没有行为违规。
候选健康检查对照的文件正确、服务提交完成，但额外的健康请求违反候选程序的规则。
两项都未通过整体验收。

这些是维护者编写的合成对照，保留观测到的系统调用和服务收据。复核不代表覆盖
任意信息流，也不认证生产者身份。交付结果时保留完整证据目录。
[观测范围和原生复现方法](../examples/behavior-audit/README.zh-CN.md)。

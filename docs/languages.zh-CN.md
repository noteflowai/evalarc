# Python 与 JavaScript 候选接入

EvalArc 评测核心仍使用 Python 3.11+。v0.6 为两个任务都打包了 Python 和
JavaScript 起步模板、参考实现与故障审计。候选使用的语言不改变任务契约和评分规则。

| 命令 | Python | JavaScript |
| --- | --- | --- |
| `init` | 默认生成 `main.py`、`TASK.md` | 加 `--language javascript`，同时生成命令清单和运行说明 |
| `init --reference` | SQLite 服务或工单策略 | JSON 快照服务或独立工单策略 |
| `audit` | 默认审计 Python 对照 | `--language javascript`，检查相同的 coding 8 类、工单 7 类故障 |
| `evaluate`、`repeat`、`suite` | 使用默认命令或候选清单 | 执行生成的命令清单，无需再指定语言 |

## 创建并运行

安装 EvalArc 后，在仓库根目录执行：

```bash
docker pull python:3.12-slim
docker pull node:22-slim
evalarc init workspace/kv-python --reference
evalarc init workspace/kv-javascript --language javascript --reference
evalarc init workspace/support-javascript --task support-routing --language javascript --reference

evalarc doctor --candidate workspace/kv-javascript --image node:22-slim
evalarc evaluate workspace/kv-javascript --image node:22-slim --output runs/kv-javascript
evalarc evaluate workspace/support-javascript --task support-routing \
  --image node:22-slim --output runs/support-javascript
```

不加 `--reference` 就会生成待实现的起步代码，它能响应协议，但不能完成任务。
创建模板不需要 Node 或 Docker；目标路径已存在时拒绝覆盖，写入中途失败会清理
不完整工作区。

JavaScript 需要 Node.js 22+。镜像必须显式选择：`--language javascript`
不会自动替换默认 Python 镜像。评测时不安装依赖，证据保存实际使用的不可变镜像 ID。

## 审计并检查证据

```bash
evalarc audit --language javascript --image node:22-slim \
  --seeds 17 --output runs/js-coding-audit
evalarc audit --task support-routing --language javascript --image node:22-slim \
  --seeds 17 --output runs/js-support-audit
```

通过条件包含参考实现完全完成任务，以及每个故障在预定维度被发现。
[已保存的审计记录](../examples/javascript-audits/README.md)保留命令、候选指纹、
镜像、逐项检查及交互轨迹。这些是公开开发任务上的脚本对照结果，不能代替模型评测，
也不能保证评分器不存在其他缺陷。

上面的三个工作区可直接用于混合语言套件：

```bash
evalarc suite examples/multilanguage/suite.toml --dry-run
evalarc suite examples/multilanguage/suite.toml --output runs/multilanguage
```

每项作业独立声明任务、镜像和验收门槛。第一项开始前，所有候选快照和镜像都必须
通过预检查。各任务分数保持独立，JUnit 为每个作业门槛生成一项测试。
[已保存的 Docker 套件](../examples/multilanguage/run/index.html)包含三项作业和
34 次场景执行的完整记录。

`compare` 和检查点曲线仍要求记录中的命令及运行条件一致。
Python 与 Node 的两次运行不会自动成为可配对比较的记录；共同的任务检查可用于
核验契约遵守情况，但不能据此给语言排名。

## 本机与其他语言

可信代码可用 `--backend local --trust-local`。候选子进程只有最小 PATH：
Node 如果位于 nvm 等版本管理器目录，需要把工作区 `evalarc.toml` 中的 `"node"`
改为绝对路径。本机 JavaScript 审计会自行从宿主 PATH 找到 Node，并记录实际命令。
Docker 清单使用容器内命令，通常保留 `"node"`。

TypeScript 可以先编译，再通过命令清单启动产物；当前不提供 TypeScript 编译器
或 SDK。预编译的 Rust 程序可使用通用命令接口，本版尚未提供或验证 Rust 参考实现
及 worker。

## 持久化参考实现的边界

Node 参考实现使用完整 JSON 快照，与 Python SQLite 实现相互独立。
每次变更先写盘、刷新并替换快照，再返回确认。契约检查的是已确认变更在进程崩溃后
仍可恢复，不能将结果扩展为生产数据库性能、并发写入或断电保证。

实现保留 JSON 数字原文，避免大整数精度丢失以及 `1` 和 `1.0` 被合并。
CAS 递归比较嵌套结构，忽略对象属性顺序，但区分布尔值和数字、整数和小数、
浮点正零和负零；数值相同的小数写法可以相等。Map 存储支持 `__proto__` 等特殊键。

[验证记录](validation-v0.6.md)列出额外协议用例、故障检测、容器和安装包检查。
这些测试没有修改公开评分场景或评分器指纹。

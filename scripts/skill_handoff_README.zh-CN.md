# 带着前序 Agent 的固定技能版本继续工作

本包保存一次已公开 Qwen3-8B 会话的六次 Qwen3-4B 接续。前序 Agent 实际通过
MCP 加载过 `robot-recording-review`。接续工作流在两个条件下均通过 MCP
预加载相同的历史 SKILL.md 与 bundle；其中一个条件额外向模型提供 Funes 历史检索工具。

打开 `index.html`，可以依次检查原始加载、工作流预加载、检索片段、交付程序与
独立验收。ZIP 包含全部原始记录、源码、编译后的提供方代码、依赖锁与内部清单，
可离线阅读，也支持关闭 JavaScript。

## 实际结果

- 固定技能、无记忆：3 次；相同技能加 Funes MCP：3 次。公开生成种子为
  17、41、97，按种子轮换条件顺序，保留全部尝试。
- 工作流通过 MCP 成功预加载技能 6 次。该动作由 harness 选择并执行，
  不计作模型自主发现或主动加载。
- 记忆组三次尝试合计成功检索 6 次，保留原始片段、回合坐标与来源。
- __PROGRAM_SUMMARY_ZH__ 技能交付、历史检索、
  Agent 宣布完成与任务通过验收分别报告。

前序会话按时间从已发布开发记录中选择：最早一次实际通过 MCP 加载机器人检查
技能的 Qwen3-8B 会话，其结果在选择时已知。本组与之前未加载额外技能的交接、
预先注入历史文本的实验分开保存。

每次最多 12 次生成、每次 4,096 个输出 token、600 秒交互时间。技能预加载、
记忆启动和最终评分分别计时。两个条件共享权威任务、初始程序、诊断工具与
历史技能字节。前序与接手会话使用不同模型和上下文，不能据此制作模型能力排名
或推断技能的因果收益。

## 复核与来源

使用对应版本的 EvalArc 源码复核已解压目录：

```sh
python -m scripts.build_skill_handoff --verify --output /path/to/extracted/evidence
```

复核器读取记录，检查原始来源、实际 MCP 回执、进入提示的技能正文、交付程序与
评分的一致性、操作计数、六次预定尝试、冻结文件和网页派生内容。它不执行包内
历史程序，也不重新调用模型。内部清单支持解压后检查；托管站点的外层清单另行
关联 ZIP 哈希。这些检查不认证材料生产者身份。

`validation/` 中的脚本对照不计作额外模型尝试。检索、空范围和路径覆盖检查在
模型实验前完成；删除来源的对照及独立基线在实验后采集，时间分别保留。
基线使用当前评分器实际执行未修改的前序程序。版本变动对照记录了一个新 MCP
进程拒绝加载与历史 pin 不符的技能。

本次命令使用共享的 editable Python 环境，实际从主工作目录导入 EvalArc
核心库。运行中及运行后的两次观察确认，54 份核心源码与冻结副本逐字节一致。
记录明确保存采集时间，不将这些观察称为首次生成前完成的运行绑定检查。
后续记录器已增加启动检查，要求使用当前工作树；可通过 `PYTHONPATH=src`
明确选择源码。

## 复现入口

`experiment.json`、`frozen/` 保存代码和依赖身份；`model-files.json` 与两份
memory model 记录保存模型文件身份。模型权重和 Funes 可执行文件需按上游条款
另行取得，不在本包中再分发。

先导出指定公开 trial，仅对该 Parquet 建立独立 Funes memory；再用
`scripts/prepare_skill_handoff.py` 绑定原始会话、程序、导出、memory、历史技能
和提供方许可证。从对应源码目录运行
`PYTHONPATH=src python scripts/record_handoff_mcp.py`，使用明确的模型、来源和
Funes 路径，并将 `--skill-bridge` 指向 Skills Anywhere 的
`examples/skill-impact/bridge.mjs`。历史 pin 会拒绝当前技能版本替代原始字节。

重复命令与重复写入是操作计数，不是无效劳动或人类节省工时的估计。本组不建立
泛化收益、隐藏测试成绩或品牌客户端原生恢复能力，也不索引用户私有历史。

许可与来源见 `LICENSE`、`source/SKILL-LICENSE.txt`、
`source/ROBOT_DATA_LICENSE.txt` 和 `source/ROBOT_DATA_NOTICE.md`。

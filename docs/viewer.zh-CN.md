# 浏览报告

所有带 `--output` 的 EvalArc 命令都会写出自包含的 HTML 报告。`evalarc view` 列出某目录下的
全部报告及其结论，并在浏览器中打开。[English](viewer.md)。

```bash
evalarc view runs            # http://127.0.0.1:7576/，自动打开浏览器
evalarc view runs --port 8000 --no-browser
evalarc view runs --write-index site/index.html   # 为 CI 产物或 Pages 生成静态索引
```

索引按时间倒序列出每个报告目录的结论（✓ 通过、✗ 失败、! 需检查）、类型与摘要，可排序和筛选。

**为什么是本地查看器而非桌面客户端：** 主流评测工具都采用只读本地 Web 服务加用户已有浏览器的
方式（`inspect view`、`promptfoo view`、`mlflow ui`），需要深度集成时提供 IDE 插件，分享时
生成静态包。Electron/Tauri 桌面壳会带来 100 MB 以上运行时或 Rust 工具链，却不提供浏览器没有
的能力，还会破坏 EvalArc 零运行时依赖的安装方式。`evalarc view` 只用 Python 标准库。

**安全：** 只绑定 `127.0.0.1`，只提供该目录内的文件；拒绝非 `127.0.0.1:端口`/`localhost:端口`
的 Host（防 DNS 重绑定）、路径穿越、指向目录外的符号链接和目录列表；只读、无 API。远程机器请用
`ssh -L 7576:127.0.0.1:7576 user@remote` 转发端口，不要直接暴露。

**架构：** 核心（解析、门禁、复核、查看器服务）是零运行时依赖的 Python，与 Inspect AI 相同；浏览器端
代码是 `frontend/` 下的 TypeScript，严格模式类型检查后编译为 `src/evalarc/assets/report_enhance.js`。
编译产物随仓库提交，因此 `pip install evalarc` 不需要 Node；若它与重新编译的结果不一致，CI 中的
`npm run check:frontend` 会失败。修改 `frontend/*.ts` 后请运行 `npm run build:frontend` 并提交两者。

**报告页面：** 先给结论（结果、原因、下一步），支持深浅色、手机、400% 缩放、打印和禁用 JavaScript。
启用 JavaScript 时，表头变为排序按钮（WAI-ARIA APG 可排序表格模式），8 行以上的表格带筛选框。
脚本内联并由页面 CSP 中的 SHA-256 哈希放行，不允许其他脚本、网络请求或远程资源。
`scripts/check_reports_browser.cjs` 在 CI 中用 axe-core（WCAG 2.2 A/AA）和端到端任务检查全部报告
类型与查看器；自动检查不能替代屏幕阅读器实测。

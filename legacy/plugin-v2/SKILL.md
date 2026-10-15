---
name: token-widget
description: 启动 / 停止 / 查看桌面 Token 消耗浮窗。当用户要开启或关闭 token 浮窗、查看 token 消耗、排查浮窗问题时使用。
---

# Token Widget 浮窗

桌面 Token 消耗浮窗：实时显示「当前对话」的 Input / Output token，点击展开完整明细。

## 触发方式
- **自动**：WorkBuddy 启动时由插件 hook（SessionStart）自动拉起，无需手动点击。
- **手动**：用户在对话中说「打开 token 浮窗」等，或在资源管理器双击启动脚本。

## 操作命令
浮窗启动脚本与 Python 宿主位于本插件内，绝对路径：
- 启动脚本：`C:/Users/haida/.workbuddy/plugins/cache/local/token-widget-plugin/1.0.0/scripts/start_widget.sh`
- Python 宿主：`C:/Users/haida/.workbuddy/plugins/cache/local/token-widget-plugin/1.0.0/widget/widget_app.py`
- venv pythonw：见同目录 `config.json` 的 `venvPythonw`

### 启动浮窗（幂等，已运行则跳过）
```bash
bash "C:/Users/haida/.workbuddy/plugins/cache/local/token-widget-plugin/1.0.0/scripts/start_widget.sh"
```

### 停止浮窗
关闭浮窗右上角 ×，或结束 pythonw 进程：
```bash
powershell -NoProfile -Command "Get-Process pythonw -ErrorAction SilentlyContinue | Stop-Process -Force"
```

### 查看状态 / 日志
- 启动编排日志：`C:/Users/haida/.workbuddy/plugins/cache/local/token-widget-plugin/1.0.0/logs/startup.log`
- 运行期错误：`C:/Users/haida/.workbuddy/plugins/cache/local/token-widget-plugin/1.0.0/widget/widget_error.log`（有错时生成）
- 调试日志：`C:/Users/haida/.workbuddy/plugins/cache/local/token-widget-plugin/1.0.0/widget/widget_debug.log`

### 启用 / 禁用
编辑 `config.json` 的 `enabled` 字段（true / false）；亦可在 WorkBuddy 插件设置里启用/禁用本插件。

## 故障排查
1. 无浮窗 → 看 `logs/startup.log`：`FAIL`/`SKIP` 会写明原因（路径不存在 / 已禁用 / 已运行）。
2. 浮窗白底 → 属 WebView2 透明问题，`widget_app.py` 已用 TransparencyKey 修复，需重启。
3. 数字不刷新 → 运行 `extract.py` 重建 `data.js`，或确认 `~/.workbuddy/projects/**/*.jsonl` 可读。

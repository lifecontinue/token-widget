---
name: token-widget
description: 启动 / 停止 / 查看桌面 Token 消耗浮窗。当用户要开启或关闭 token 浮窗、查看 token 消耗、排查浮窗问题时使用。
---

# Token Widget 浮窗

桌面 Token 消耗浮窗：实时显示「当前对话」的 Input / Output token，点击展开完整明细。

## 触发方式
- **自动**：WorkBuddy 启动时由插件 hook（SessionStart）自动拉起，无需手动点击。
- **手动**：用户在对话中说「打开 token 浮窗」等，或双击桌面快捷方式 / `start_widget.sh`。

## 安装（重要）
插件与应用的**唯一权威来源是本仓库**。应用必须装在稳定目录，**不能放在 WorkBuddy 会话工作区里**（会被清理，历史事故）：

```bash
bash workbuddy-plugin/scripts/install.sh            # 装到 ~/.workbuddy/token-widget
bash workbuddy-plugin/scripts/install.sh --autostart --desktop
```

## 操作命令
- 启动脚本：`<插件目录>/scripts/start_widget.sh`（读 config.json 的 engine，幂等）
- 看门狗：`<插件目录>/scripts/watchdog.pyw`（WorkBuddy 起来就拉浮窗，退出就关）
- 应用目录：`config.json` 的 `electronApp`（Electron 引擎）

### 启动浮窗（幂等，已运行则跳过）
```bash
bash "<插件目录>/scripts/start_widget.sh"
```

### 停止浮窗
关闭浮窗 ×（隐藏到托盘，进程常驻）；要真退出用托盘右键「退出」。

### 查看状态 / 日志
- 启动编排日志：`<插件目录>/logs/startup.log`（`FAIL`/`SKIP` 会写明原因）
- 看门狗日志：`<插件目录>/logs/watchdog.log`
- 浮窗运行期日志：`<应用目录>/logs/`（widget_debug.log / widget_error.log）

### 启用 / 禁用
编辑 `config.json` 的 `enabled` 字段（true / false）；亦可在 WorkBuddy 插件设置里启用/禁用本插件。

## 故障排查
1. 无浮窗 → 看 `logs/startup.log`：`engine binary not found` / `app path not found` 都带 HINT，按提示跑 `install.sh`。
2. 日志里每次都是 `FAIL: pythonw not found` → 你在用 v2 旧脚本，跑 `install.sh` 升级到 v3（已改读 config.json 的 engine）。
3. 浮窗白底 → Electron 透明问题，确认 `transparent:true` + `backgroundColor:'#00000000'`，重启。
4. 数字不刷新 → 确认 `~/.workbuddy/projects/**/*.jsonl` 可读；浮窗读 `app/sessions.json` 跟随当前会话。

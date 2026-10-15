# workbuddy-plugin · WorkBuddy 集成层

把 Token Widget 接进 WorkBuddy：**SessionStart 自动拉起浮窗** + 看门狗兜底 + 一键安装。

> 这一层 2026-10-15 之前**不在仓库里**，只散落在插件缓存目录和某个会话工作区中。
> 结果那次会话工作区被清理，浮窗直接消失——所以现在把它纳入版本管理。

---

## 目录结构

```
workbuddy-plugin/
├── config.json                  # 引擎与路径（install.sh 会改写成绝对路径）
├── .codebuddy-plugin/plugin.json
├── hooks/hooks.json             # SessionStart -> start_widget.sh
├── skills/token-widget/SKILL.md # 供 Agent 调用的操作手册
└── scripts/
    ├── start_widget.sh          # 启动入口（v3 重写：读 engine，零硬编码路径）
    ├── watchdog.pyw             # 看门狗：WorkBuddy 起来拉浮窗 / 退出关浮窗
    ├── run_watchdog.vbs         # 看门狗无控制台启动器（开机自通用）
    ├── install.sh               # 一键安装（装到稳定目录）
    └── create_desktop_shortcut.py
```

## 安装

```bash
# 标准安装：源码 -> ~/.workbuddy/token-widget，插件 -> ~/.workbuddy/plugins/cache/local/...
bash workbuddy-plugin/scripts/install.sh

# 常用组合
bash workbuddy-plugin/scripts/install.sh --autostart --desktop   # 开机自启 + 桌面快捷方式
bash workbuddy-plugin/scripts/install.sh --build                 # 额外打包 portable/nsis
bash workbuddy-plugin/scripts/install.sh --skip-npm              # node_modules 已在时

# 自定义位置
TOKEN_WIDGET_HOME=/d/apps/token-widget bash workbuddy-plugin/scripts/install.sh
TOKEN_WIDGET_SRC=/d/src/token-widget bash workbuddy-plugin/scripts/install.sh   # 用本地源码
```

安装完成后**重启 WorkBuddy**，SessionStart hook 会自动拉起浮窗（幂等，重复触发自动跳过）。

## 两条铁律（都是踩过的坑）

1. **应用必须放在稳定目录**（默认 `~/.workbuddy/token-widget`）。
   WorkBuddy 的会话工作区（`~/WorkBuddy/<日期时间戳>/`）是临时目录，会被清理；
   把项目放在里面，某天重启就什么都没了。2026-10-14 的事故正是如此。
2. **路径只认 config.json**。`start_widget.sh` 不写任何绝对路径，
   引擎（electron / pywebview）与可执行文件路径全部来自 `config.json`，
   由 `install.sh` 按本机重写。改路径 = 改 config，不要改脚本。

## 配置说明（config.json）

| 字段 | 说明 |
| --- | --- |
| `enabled` | false 则 hook 直接 SKIP |
| `engine` | `electron`（默认，推荐）/ `pywebview`（旧安装兼容） |
| `electronExe` / `electronApp` | electron 引擎的可执行文件与应用目录 |
| `venvPythonw` / `appEntry` | pywebview 引擎的 pythonw 与 widget_app.py |
| `maxRetries` / `startupGraceSec` / `launchCooldownSec` | 看门狗重试与冷却参数 |

相对路径基于 `TOKEN_WIDGET_HOME`（默认 `~/.workbuddy/token-widget`）解析；
`install.sh` 会统一改成绝对路径。

## 日志与排查

| 日志 | 内容 |
| --- | --- |
| `<插件目录>/logs/startup.log` | hook 编排：`STARTED` / `SKIP` / `FAIL` + HINT |
| `<插件目录>/logs/watchdog.log` | 看门狗动作：拉起 / 关闭 / 重试 |
| `<插件目录>/logs/.widget.pid` | 当前浮窗 PID（幂等锁） |

排查顺序：`startup.log` → `watchdog.log` → 应用目录下运行期日志。
所有 `FAIL` 都带 `HINT`，按提示跑 `install.sh` 即可自愈。

## 2026-10-15 事故复盘（v2 → v3）

| 问题 | 根因 | v3 修法 |
| --- | --- | --- |
| 浮窗彻底消失 | 应用放在会话工作区 `WorkBuddy/2026-08-10-09-11-39/token-dashboard/`，被清理 | install.sh 强制装到 `~/.workbuddy/token-widget` |
| 每次启动 `FAIL: pythonw not found` | `start_widget.sh` 硬编码 pywebview venv 路径，且不读 config 的 engine | v3 读 config.json，双引擎，零硬编码 |
| config 与脚本不同步 | 8/14 切到 Electron 引擎只改了 config，没改脚本 | 单一事实来源 = config.json |
| 集成层无版本管理 | 插件文件只在插件缓存里，仓库只有 overlay | 本目录入库，可随时重装 |

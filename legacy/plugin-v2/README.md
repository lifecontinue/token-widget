# Token Widget Plugin

WorkBuddy 桌面 Token 消耗浮窗插件：**WorkBuddy 打开时自动在桌面显示当前对话的 Input/Output token 实时消耗**，点击展开完整明细。独立进程运行，不依赖宿主内部启动逻辑。

## 目录结构

```
token-widget-plugin/1.0.0/
├── .codebuddy-plugin/
│   └── plugin.json          # 标准插件清单（WorkBuddy 识别的入口定义）
├── hooks/
│   └── hooks.json           # SessionStart 钩子 → 联动触发启动脚本
├── scripts/
│   ├── start_widget.sh      # hook 启动入口（幂等 + 启用检查 + 可读日志）
│   ├── watchdog.pyw         # 看门狗：监听 WorkBuddy.exe，自动拉起/关闭浮窗（联动主机制）
│   ├── run_watchdog.vbs     # 看门狗无控制台启动器（双击即运行）
│   └── install_autostart.py # 注册看门狗到 Windows 启动文件夹
├── skills/
│   └── token-widget/SKILL.md  # slash command 入口（/token-widget，手动调用）
├── widget/                  # 浮窗负载（独立进程）
│   ├── widget_app.py        #   pywebview 宿主（透明键色 + 胶囊裁剪）
│   ├── widget.html          #   单行浮岛 + 详情 popup UI
│   ├── extract.py           #   jsonl → data.js 提取器
│   ├── data.js / chart.umd.js
├── config.json              # 启用/禁用 + 路径配置
├── logs/                    # 运行日志（startup.log）
└── install.sh               # 一键建独立 venv（自包含分发用）
```

## 安装（已在本机完成）

1. 插件位于 `~/.workbuddy/plugins/cache/local/token-widget-plugin/1.0.0/`
2. 已注册到 `~/.workbuddy/plugins/installed_plugins.json`（marketplace key = `local`）
3. 已在 `~/.workbuddy/settings.json` 的 `enabledPlugins` 中启用

## 联动触发机制（看门狗，实测可用）

> 注：插件 hook（`hooks/hooks.json` 的 `SessionStart`）经实测**未触发**——WorkBuddy 插件加载器只认已注册 marketplace + 签名（`manifest.qmsig`）的插件，本地未签名插件会被忽略。联动改用**看门狗**，不依赖插件加载器。

- `scripts/watchdog.pyw` —— 常驻进程，每 3s 轮询 `WorkBuddy.exe`：
  - WorkBuddy 起来且无浮窗进程 → 拉起桌面 token 浮窗
  - WorkBuddy 退出且有浮窗进程 → 关闭浮窗（随宿主同生共死）
- **防重复启动**：命名互斥体单例（只允许一个看门狗）+ 每轮扫描实际浮窗进程（父+子都算），有浮窗在跑就不重拉。
- **启动失败重试上限**：`config.json` 的 `maxRetries`（默认 3）+ `startupGraceSec`（默认 30s）。连续失败 3 次后停止重试（重启 WorkBuddy 恢复）；浮窗稳定运行超 30s 重置计数。
- **手动关闭不重拉**：浮窗稳定运行后被关闭视为手动操作，本会话不再重拉。
- 已注册到 Windows 启动文件夹（`token-widget-watchdog.vbs`），每次登录自动运行。

**立即生效**：双击 `scripts/run_watchdog.vbs`（或等下次登录）。看门狗检测到正在运行的 WorkBuddy 后立即拉起浮窗。

## 启用 / 禁用

- **WorkBuddy 层**：插件设置里开关，或编辑 `settings.json` → `enabledPlugins` 的 `"token-widget-plugin@local"`
- **插件层**：编辑 `config.json` → `"enabled": true/false`（启动脚本会读取并跳过）

## 日志与错误处理

- 启动编排日志：`logs/startup.log`（每次触发写入 STARTED / SKIP / FAIL + 原因）
- 运行期错误：`widget/widget_error.log`（异常时生成）+ 弹窗提示（不再静默失败）
- 调试日志：`widget/widget_debug.log`

## 兜底方案（不依赖 WorkBuddy 插件加载器）

若 WorkBuddy 未识别本地插件 / hook 未触发，可用 OS 级联动保证自动启动：

1. 打开启动文件夹：`Win+R` → `shell:startup`
2. 放入 `run_widget_on_boot.vbs` 的快捷方式（该脚本轮询 `WorkBuddy.exe` 出现后自动弹浮窗）

## 分发（其他机器）

在目标机器运行 `install.sh`，会：① 创建插件内独立 `.venv` 并安装 pywebview；② 按本机路径重写 `scripts/start_widget.sh` 与 `config.json` 的绝对路径。之后把插件目录放入该机的 `~/.workbuddy/plugins/cache/local/` 并注册即可。

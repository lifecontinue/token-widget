# Token Widget

> **一个常驻桌面的「token 消耗透视镜」** —— Cluely 式透明置顶浮窗，实时把你当前对话在 WorkBuddy 里花掉的 In / Out tokens 摊在屏幕上。不抢焦点、不吃内存、不联网，**关掉它只是隐藏到托盘，不是退出**。

---

## 这是什么 / 为什么做

用 AI 助手越深，越容易「不知不觉烧 token」。WorkBuddy 的数据都在本地 `~/.workbuddy/` 下，但散在无数 `.jsonl` 对话日志里，人肉看不了。

Token Widget 把这个数据「拉到桌面上」：

- 一条 **透明胶囊** 常驻屏幕（默认屏幕中央，可拖到任意角落）；
- 实时显示 **当前对话** 的 `In xx · Out xx`（输入 / 输出 token）；
- 点击数字区展开 **详情面板**：KPI 总览 + 按模型拆分的消耗明细；
- 关掉浮窗 ≠ 退出进程 —— 它缩到 **系统托盘** 常驻，内存从 ~100MB 压到 ~45MB；
- 默认开启 **防截屏**，截图 / 录屏里浮窗区域变黑，token 数据不会被截走。

一句话：**让 AI 用量从「看不见」变成「抬头即见」**。

---

## 核心特性

| 特性 | 说明 |
|------|------|
| **透明置顶浮窗** | `BrowserWindow` + `transparent:true` + `alwaysOnTop`，不抢焦点、不进任务栏、全屏应用也压得住 |
| **实时 token 透视** | 轮询本地 `.jsonl`，按 `sessionId` 聚合「当前对话」，1.5s 刷新 |
| **详情面板** | KPI（总量 / 成本估算）+ 按模型明细，Esc / × 关闭 |
| **系统托盘常驻** | 右下角绿色圆点图标，单击切换显隐，右键菜单含「开机自启」「退出」 |
| **单例锁** | 重复双击只唤出已有实例，绝不双开 |
| **优雅退出** | 关窗 = 销毁式隐藏（释放 renderer）；托盘「退出」才真正结束进程 |
| **位置记忆** | 拖动后自动记住坐标，重启 / 重开恢复原位 |
| **开机自启** | 托盘右键勾选，登录 Windows 自动拉起 |
| **防截屏** | `setContentProtection(true)`（Windows `WDA_EXCLUDEFROMCAPTURE`），默认开 |
| **零网络** | 只读本地日志文件，不请求任何远端接口，无遥测、无上报 |
| **轻量** | 自包含，托盘常驻时仅主进程 + 托盘，约 45MB |

---

## 架构（它怎么工作）

```
┌───────────────────────────────────────────────────────────┐
│   WorkBuddy 本地数据  ~/.workbuddy/projects/**/*.jsonl      │
│   （每条对话日志：sessionId / model / usage.inputTokens …） │
└───────────────────────────┬───────────────────────────────┘
                            │  直读（preload 内 fs 扫描）
                            ▼
┌───────────────────────────────────────────────────────────┐
│  Electron Main 进程 (electron-main.js)                      │
│   • 单例锁 requestSingleInstanceLock                        │
│   • 透明置顶窗口  transparent + alwaysOnTop + skipTaskbar    │
│   • 系统托盘 Tray（图标 / 显隐 / 退出 / 开机自启）           │
│   • 位置记忆 + config.json 持久化                           │
│   • 防截屏 setContentProtection                             │
└───────────────────────────┬───────────────────────────────┘
                            │  contextBridge 暴露 window.api
                            ▼
┌───────────────────────────────────────────────────────────┐
│  Renderer (widget.html)                                     │
│   • 单行胶囊：当前对话 · In xx · Out xx                      │
│   • 手动拖拽（mousedown/mousemove + IPC move-to）            │
│   • 点击数字区 → 详情 popup（KPI + 按模型明细）             │
│   • × 按钮 → 隐藏到托盘（destroy 窗口，释放 renderer）       │
└───────────────────────────────────────────────────────────┘
```

**关键设计决策**

- **为什么不用 `app-region: drag` 拖拽？** 在 `transparent:true` 窗口里，该属性会拦截子元素点击，导致 × 按钮失效。改为 **纯 JS 手动拖拽**（监听 `mousedown` 命中胶囊空白区 → `mousemove` 发 IPC `move-to` → 主进程 `setBounds`），× 与数字区点击 100% 生效。
- **为什么关窗是 destroy 不是 hide？** `hide()` 保留 renderer 进程占 ~55MB；`destroy()` 释放它，托盘常驻时只留主进程，内存减半。
- **为什么单例锁 + 托盘？** 这是「像不像正常软件」的分水岭：重复启动不双开、关窗不退出、能从托盘恢复。

---

## 项目结构

```
token-widget/
├── README.md              # 本文档
├── .gitignore
├── scripts/
│   └── gen-icons.py       # 纯标准库生成 tray.png / icon.ico（无需二进制入库）
└── overlay/               # Electron 应用本体（自包含）
    ├── electron-main.js   # 主进程：单例 + 托盘 + 透明置顶 + 位置记忆 + 自启
    ├── preload.js         # contextBridge 暴露 window.api + token 扫描
    ├── widget.html        # 单行胶囊 + 详情面板 UI（透明 body）
    ├── package.json       # electron + electron-builder 配置
    └── assets/            # 运行时生成（tray.png / icon.ico，见 gen-icons.py）
```

> 注：`assets/*.png` 与 `*.ico` 不入库（二进制），用 `npm run gen-icons` 在构建前由 `scripts/gen-icons.py` 重新生成。

---

## 安装与运行

### 方式 A：直接用打包好的 exe（推荐普通用户）

1. 从 Releases 下载 `Token Widget Setup x.x.x.exe`（或 portable 单文件）；
2. 安装 / 解压后双击 `Token Widget.exe`；
3. 屏幕中央出现透明胶囊，右下角出现绿色托盘图标。

> 当前已产出 `dist/win-unpacked/Token Widget.exe`（免安装目录版），可整目录拷贝到任意机器运行。

### 方式 B：从源码运行（开发者）

```bash
cd overlay
npm install                # 安装 electron + electron-builder
npm run gen-icons          # 生成托盘 / 应用图标（prestart 会自动跑）
npm start                  # 启动开发模式
```

---

## 从源码打包独立 exe

```bash
cd overlay
npm run build              # 同时产出 portable 单文件 + NSIS 安装包 → ../dist/
npm run build:portable     # 仅单文件 portable exe（双击即用，免安装）
npm run build:nsis         # 仅 NSIS 安装包（桌面快捷方式 + 开始菜单 + 卸载）
```

**国内网络加速**（electron / electron-builder 二进制走镜像）：

```bash
ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/ \
ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/ \
npm run build
```

打包产物：

- `dist/Token Widget x.x.x.exe` —— portable 单文件
- `dist/Token Widget Setup x.x.x.exe` —— NSIS 安装包（推荐分发）

---

## 配置

配置持久化在 `app.getPath('userData')/config.json`（首次运行自动创建）：

```json
{
  "windowPosition": { "x": 800, "y": 400 },
  "autoStart": false
}
```

| 字段 | 含义 |
|------|------|
| `windowPosition` | 浮窗最后位置，关闭 / 重启后恢复 |
| `autoStart` | 是否开机自启（托盘右键「开机自启」写入） |

**环境变量**

| 变量 | 作用 |
|------|------|
| `TOKEN_WIDGET_NO_PROTECT=1` | 关闭防截屏，便于调试 / 截图反馈 |

---

## 交互一览

| 操作 | 效果 |
|------|------|
| 看胶囊 | 实时显示「当前对话 · In xx · Out xx」 |
| 拖空白处 | 移动浮窗（自动记忆位置） |
| 点数字区 | 展开详情面板（KPI + 按模型明细） |
| 点 × | 隐藏到托盘（进程常驻，不退出） |
| 点托盘图标 | 切换显隐 |
| 托盘右键 | 显示/隐藏、开机自启、退出 |
| 托盘「退出」 | 真正结束进程 |

---

## 隐私与安全

- **纯本地**：只读 `~/.workbuddy/projects/**/*.jsonl`，不发任何网络请求，无遥测、无上报、无第三方 SDK。
- **防截屏**：默认 `setContentProtection(true)`，截图 / 录屏中浮窗区域变黑，token 数据不会被截走。
- **数据范围**：仅聚合 token 计数，不上传任何对话内容。

---

## 故障排查

| 现象 | 处理 |
|------|------|
| 点 × 浮窗不消失 | 确保用最新代码（已改手动拖拽，弃用 `app-region`）；旧版 `app-region` 在透明窗会吞点击 |
| 托盘图标在截图里变黑 / 异常 | 预期行为（防截屏）；调试设 `TOKEN_WIDGET_NO_PROTECT=1` |
| 启动报找不到 `tray.png` / `icon.ico` | 跑 `npm run gen-icons` 生成资源 |
| 打包卡在下载 electron 二进制 | 设上文 `ELECTRON_MIRROR` 镜像后重试 |
| 想彻底退出 | 托盘右键 → 退出（× 只是隐藏） |

---

## 路线图

- [ ] 设置面板 UI（在 popup 内可视化配置刷新频率 / 成本单价 / 主题）
- [ ] 成本估算接入真实模型单价
- [ ] 多会话切换（在多个 WorkBuddy 对话间切换查看）
- [ ] macOS / Linux 托盘适配

---

## 技术栈

- **Electron** `^33`（透明置顶窗口 + 托盘 + 单例）
- **原生 HTML/CSS/JS**（renderer，无框架，极轻量）
- **electron-builder** `^25`（打包 portable / NSIS）
- **Python 标准库**（仅构建期生成图标，无运行时依赖）

---

## License

MIT

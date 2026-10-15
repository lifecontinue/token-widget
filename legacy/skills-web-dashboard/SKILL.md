---
name: token-widget
description: 在 WorkBuddy 内一键启动并展示「Tokens 数据看板」轻量小组件（widget.html）。当用户说"打开 token 看板 / 启动 widget / 看模型消耗 / token dashboard / 显示 tokens 组件"或任何想查看自己在 WorkBuddy 中模型 token 消耗的需求时触发。技能会启动本地静态服务并在右侧结果区预览面板显示实时组件。
agent_created: true
---

# Tokens 数据看板 · 小组件启动技能

把已构建好的 `token-dashboard` 轻量 widget 跑起来，并**显示在当前 WorkBuddy 会话的结果区预览面板**中，实现"在软件内查看、随对话随时唤起"的体验。

## 交付物（只读，不要修改）
- `token-dashboard/widget.html` —— 轻量组件（模型 token 消耗明细 + 占比环图 + 自配/托管占比条），依赖同目录 `data.js` 与 `chart.umd.js`。
- `token-dashboard/index.html` —— 全功能看板（如需完整版可改用此 URL）。
- `token-dashboard/extract.py` —— 从 `~/.workbuddy/projects/**/*.jsonl` 重新抽取数据。

## 启动流程（严格按顺序）

### 1. 定位看板目录
先检查已知路径，再用 Glob 兜底（用户的工作区按日期命名，目录会变）：
```
Glob： C:\Users\haida\WorkBuddy\**\token-dashboard\widget.html
```
取第一个命中目录作为 `DASH`。若已知路径 `C:\Users\haida\WorkBuddy\2026-08-10-09-11-39\token-dashboard` 存在则优先使用。

### 2.（可选）刷新数据
仅当用户明确要求"刷新 / 更新数据 / 重新统计"时执行：
```
cd <DASH>
"C:/Users/haida/.workbuddy/binaries/python/versions/3.13.12/python.exe" extract.py
```
平时直接复用已有 `data.js` 即可，无需每次重跑。

### 3. 启动本地静态服务（若未运行）
先探测端口是否已在监听（Windows PowerShell）：
```
$conn = Get-NetTCPConnection -LocalPort 8899 -ErrorAction SilentlyContinue
if ($conn) { "ALREADY_RUNNING" } else { "NEED_START" }
```
若 `NEED_START`，用**托管 Python** 在后台启动（必须从 `DASH` 目录启动，确保 widget.html/data.js/chart.umd.js 同域可访问）：
```
cd <DASH>
"C:/Users/haida/.workbuddy/binaries/python/versions/3.13.12/python.exe" -m http.server 8899 --bind 127.0.0.1
```
以 run_in_background=true 运行，不要阻塞。

### 4. 在 WorkBuddy 结果区显示
调用 present_files，传入本地服务 URL（会自动在右侧内置浏览器预览面板打开）：
- 轻量组件：`http://127.0.0.1:8899/widget.html`
- 全功能看板：`http://127.0.0.1:8899/index.html`
explanation 写："Tokens 数据看板小组件（模型 token 消耗）"。

## 关键约束（务必遵守）
- **不要**尝试修改 WorkBuddy 原生界面（无此 API）；显示通道只有"结果区预览面板"（即 present_files 的 http URL 预览）。
- 服务绑定 `127.0.0.1`（仅本机），不暴露到公网。
- 端口固定 8899；若被占用，先在 PowerShell 查占用进程并提示用户，不要擅自换端口导致旧实例残留。
- widget 依赖同目录 `data.js` / `chart.umd.js`；务必用 http 服务方式打开，不要直接 `file://` 打开（会因跨域/路径导致 chart 加载失败）。

## 收尾话术
启动成功后告诉用户：
- 在 WorkBuddy 内已打开预览；也可在本机浏览器访问 `http://127.0.0.1:8899/widget.html`。
- 数据口径说明：托管端点（WorkBuddy 自带）不经过用户的自配 API key，因此平台账单只含自配部分；详见 `recon_deepseek.md`。
- 服务是后台进程，本次会话结束会停止；下次说"打开 token 看板"即可再次唤起本技能。

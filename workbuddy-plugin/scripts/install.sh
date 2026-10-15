#!/usr/bin/env bash
# ============================================================
# Token Widget · 一键安装（v3）
# ------------------------------------------------------------
# 目标：把 token-widget 装到【稳定目录】，彻底远离 WorkBuddy 会话工作区。
#
#   应用/源码  TOKEN_WIDGET_HOME  默认 ~/.workbuddy/token-widget
#   插件目录   TOKEN_WIDGET_PLUGIN_DIR
#              默认 ~/.workbuddy/plugins/cache/local/token-widget-plugin/1.0.0
#
# 用法（Git Bash）：
#   bash install.sh                      # 安装：拿源码 -> npm install -> gen-icons -> 部署插件
#   bash install.sh --build              # 额外打包 portable/nsis 到 dist/
#   bash install.sh --skip-npm           # node_modules 已存在时跳过依赖安装
#   bash install.sh --autostart          # 看门狗写进 Windows 启动文件夹（开机自启）
#   bash install.sh --desktop            # 创建桌面快捷方式
#   TOKEN_WIDGET_SRC=/path/to/repo bash install.sh   # 用本地源码，不 clone
#
# 环境变量：
#   TOKEN_WIDGET_HOME / TOKEN_WIDGET_PLUGIN_DIR / TOKEN_WIDGET_REPO / TOKEN_WIDGET_SRC
# ============================================================
set -euo pipefail

REPO_URL="${TOKEN_WIDGET_REPO:-https://github.com/lifecontinue/token-widget.git}"
TW_HOME="${TOKEN_WIDGET_HOME:-$HOME/.workbuddy/token-widget}"
PLUGIN_DIR="${TOKEN_WIDGET_PLUGIN_DIR:-$HOME/.workbuddy/plugins/cache/local/token-widget-plugin/1.0.0}"
# 纯 bash 解析自身所在目录（不依赖 dirname）
_src="${BASH_SOURCE[0]}"
_dir="${_src%/*}"; [ "$_dir" = "$_src" ] && _dir="."
HERE="$(cd "$_dir/.." 2>/dev/null && pwd)"; [ -n "$HERE" ] || HERE="$_dir/.."   # workbuddy-plugin/ 目录

DO_BUILD=0; DO_SKIP_NPM=0; DO_AUTOSTART=0; DO_DESKTOP=0
for a in "$@"; do
  case "$a" in
    --build)     DO_BUILD=1 ;;
    --skip-npm)  DO_SKIP_NPM=1 ;;
    --autostart) DO_AUTOSTART=1 ;;
    --desktop)   DO_DESKTOP=1 ;;
    -h|--help)   echo "用法: bash install.sh [--build] [--skip-npm] [--autostart] [--desktop]"; exit 0 ;;
    *) echo "unknown option: $a"; exit 2 ;;
  esac
done

say(){ printf '\n=== %s ===\n' "$*"; }

# ---------------- 0) Python（install.sh 用它重写路径） ----------------
PY=""
for c in "$HOME/.workbuddy/binaries/python/versions/3.13.12/python.exe" \
         "$HOME/AppData/Local/Programs/Python/Python313/python.exe" \
         "python" "python3"; do
  if command -v "$c" >/dev/null 2>&1 || [ -x "$c" ]; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "FAIL: 找不到 python（安装脚本需要它重写路径）"; exit 1; }
echo "python: $PY"

# ---------------- 1) 获取源码到稳定目录 ----------------
say "1/6 获取源码 -> $TW_HOME"
if [ -n "${TOKEN_WIDGET_SRC:-}" ]; then
  echo "使用本地源码: $TOKEN_WIDGET_SRC"
  TW_HOME="$TOKEN_WIDGET_SRC"
elif [ -d "$TW_HOME/.git" ]; then
  echo "已存在 git 仓库，pull --ff-only"
  git -C "$TW_HOME" pull --ff-only || echo "WARN: pull 失败，使用当前工作副本继续"
elif [ -d "$TW_HOME" ]; then
  # 目录已存在：空则 clone，非空则按已有源码用（纯 bash 判断，不依赖 ls -A）
  shopt -s nullglob dotglob
  _existing=("$TW_HOME"/*)
  shopt -u nullglob dotglob
  if [ "${#_existing[@]}" -gt 0 ]; then
    echo "目录已存在且非空，按已有源码使用: $TW_HOME"
  else
    rmdir "$TW_HOME" 2>/dev/null || true
    git clone --depth 1 "$REPO_URL" "$TW_HOME"
  fi
else
  git clone --depth 1 "$REPO_URL" "$TW_HOME"
fi
[ -d "$TW_HOME/overlay" ] || { echo "FAIL: $TW_HOME/overlay 不存在，源码不完整"; exit 1; }

# ---------------- 2) 依赖与图标 ----------------
say "2/6 依赖与图标"
if [ "$DO_SKIP_NPM" = "1" ]; then
  echo "跳过 npm install（--skip-npm）"
elif ! command -v npm >/dev/null 2>&1; then
  echo "WARN: 找不到 npm，跳过依赖安装。稍后手动执行："
  echo "      cd \"$TW_HOME/overlay\" && npm install && npm run gen-icons"
else
  ( cd "$TW_HOME/overlay" && npm install && npm run gen-icons )
fi

if [ "$DO_BUILD" = "1" ]; then
  say "2b/6 打包（portable + nsis）"
  ( cd "$TW_HOME/overlay" && npm run build ) || echo "WARN: 打包失败，可稍后重试"
fi

# ---------------- 3) 部署插件目录 ----------------
say "3/6 部署插件 -> $PLUGIN_DIR"
mkdir -p "$PLUGIN_DIR"
for item in .codebuddy-plugin config.json hooks skills scripts; do
  if [ -e "$HERE/$item" ]; then
    rm -rf "$PLUGIN_DIR/$item" 2>/dev/null || true
    cp -r "$HERE/$item" "$PLUGIN_DIR/"
  fi
done
# 清理运行时产物（日志/锁/旧 venv 不属于分发内容）
rm -rf "$PLUGIN_DIR/logs" "$PLUGIN_DIR/.venv" "$PLUGIN_DIR/.widget.pid" 2>/dev/null || true
mkdir -p "$PLUGIN_DIR/logs"
echo "插件文件已就绪"

# ---------------- 4) 重写 config.json 为绝对路径 ----------------
say "4/6 重写 config.json 绝对路径"
"$PY" - "$TW_HOME" "$PLUGIN_DIR" <<'PY'
import json, os, sys
tw_home, plugin_dir = sys.argv[1], sys.argv[2]
cfg_path = os.path.join(plugin_dir, "config.json")
with open(cfg_path, encoding="utf-8") as f:
    cfg = json.load(f)

def w(p):  # Windows 友好：统一用正斜杠
    return p.replace("\\", "/")

cfg["electronExe"] = w(os.path.join(tw_home, "overlay", "node_modules", "electron", "dist", "electron.exe"))
cfg["electronApp"] = w(os.path.join(tw_home, "overlay"))
cfg["venvPythonw"] = w(os.path.join(tw_home, ".venv", "Scripts", "pythonw.exe"))
cfg["appEntry"]    = w(os.path.join(tw_home, "widget", "widget_app.py"))
cfg.pop("_comment", None)

with open(cfg_path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
    f.write("\n")
print("config.json ->")
print("  electronExe =", cfg["electronExe"])
print("  electronApp =", cfg["electronApp"])
PY

# ---------------- 5) 注册插件（installed_plugins.json） ----------------
say "5/6 注册插件"
"$PY" - "$PLUGIN_DIR" <<'PY'
import json, os, sys
plugin_dir = sys.argv[1].replace("\\", "/")
reg = os.path.join(os.path.expanduser("~"), ".workbuddy", "plugins", "installed_plugins.json")
entry = {
    "scope": "user",
    "installPath": plugin_dir,
    "version": "1.0.0",
    "installedAt": "2026-10-15T00:00:00.000Z",
    "lastUpdated": "2026-10-15T00:00:00.000Z",
}
try:
    with open(reg, encoding="utf-8") as f:
        data = json.load(f)
except Exception:
    data = {"version": 2, "plugins": {}}
plugins = data.setdefault("plugins", {})
key = "token-widget-plugin@local"
if key in plugins:
    print("已注册（保留原条目）:", key)
else:
    plugins[key] = [entry]
    with open(reg, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("已写入注册表:", key)
PY

# ---------------- 6) 自启 / 桌面快捷方式 ----------------
say "6/6 收尾"
if [ "$DO_AUTOSTART" = "1" ]; then
  STARTUP="$APPDATA/Microsoft/Windows/Start Menu/Programs/Startup"
  mkdir -p "$STARTUP" 2>/dev/null || true
  "$PY" - "$PLUGIN_DIR" "$STARTUP" <<'PY'
import os, sys
plugin_dir, startup = sys.argv[1], sys.argv[2]
pyw = os.path.join(os.path.expanduser("~"), ".workbuddy", "binaries", "python",
                   "versions", "3.13.12", "pythonw.exe")
wd = os.path.join(plugin_dir, "scripts", "watchdog.pyw")
if not os.path.exists(pyw):
    print("WARN: managed pythonw 不存在，跳过自启:", pyw); sys.exit(0)
vbs = (
    "' Token Widget watchdog (auto-start)\n"
    'Set W = CreateObject("WScript.Shell")\n'
    'W.Run """%s"" ""%s""", 0, False\n' % (pyw, wd)
)
out = os.path.join(startup, "token-widget-watchdog.vbs")
with open(out, "w", encoding="utf-8") as f:
    f.write(vbs)
print("开机自启已写入:", out)
PY
fi

if [ "$DO_DESKTOP" = "1" ]; then
  "$PY" "$PLUGIN_DIR/scripts/create_desktop_shortcut.py" || echo "WARN: 桌面快捷方式创建失败"
fi

cat <<EOF

✔ 安装完成
  应用目录 : $TW_HOME
  插件目录 : $PLUGIN_DIR
  启动日志 : $PLUGIN_DIR/logs/startup.log

下一步：
  1) 重启 WorkBuddy -> SessionStart hook 自动拉起浮窗（幂等）
  2) 想开机自启：bash install.sh --autostart
  3) 排查问题：cat "$PLUGIN_DIR/logs/startup.log"
EOF

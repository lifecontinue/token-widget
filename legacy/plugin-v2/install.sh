#!/usr/bin/env bash
# ============================================================
# Token Widget 插件 · 一键安装脚本（自包含分发用）
# ------------------------------------------------------------
# 作用：
#   1) 在插件内创建独立 .venv 并安装 pywebview（不依赖本机已有环境）
#   2) 按本机路径重写 scripts/start_widget.sh 与 config.json 的绝对路径
#
# 用法（Git Bash）：
#   bash install.sh
# ============================================================
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "插件根目录: $ROOT"

# 1) 选择 python（优先 managed，回退系统）
PY=""
for c in "$HOME/.workbuddy/binaries/python/versions/3.13.12/python.exe" \
         "$HOME/AppData/Local/Programs/Python/Python313/python.exe" \
         "python"; do
  if command -v "$c" >/dev/null 2>&1 || [ -x "$c" ]; then PY="$c"; break; fi
done
echo "使用 Python: $PY"

# 2) 建独立 venv + 装 pywebview
VENV="$ROOT/.venv"
if [ ! -f "$VENV/Scripts/pythonw.exe" ]; then
  echo "创建 venv ..."
  "$PY" -m venv "$VENV"
fi
echo "安装 pywebview ..."
"$VENV/Scripts/pip.exe" install --quiet --upgrade pip
"$VENV/Scripts/pip.exe" install --quiet pywebview
echo "pywebview 安装完成"

# 3) 重写绝对路径
PYW="$VENV/Scripts/pythonw.exe"
APP="$ROOT/widget/widget_app.py"
CONFIG="$ROOT/config.json"
LOGDIR="$ROOT/logs"

# config.json
cat > "$CONFIG" <<JSON
{
  "enabled": true,
  "version": "1.0.0",
  "widgetHome": "widget",
  "appEntry": "widget/widget_app.py",
  "venvPythonw": "$(echo "$PYW" | sed 's#\\#/#g')",
  "logFile": "logs/startup.log",
  "lockFile": "logs/.widget.pid"
}
JSON

# start_widget.sh 路径块
SH="$ROOT/scripts/start_widget.sh"
python3 - "$SH" "$PYW" "$APP" "$CONFIG" "$LOGDIR" <<'PY'
import sys, re
sh, pyw, app, cfg, logdir = sys.argv[1:6]
def w(p): return p.replace('\\','/')
src = open(sh, encoding='utf-8').read()
src = re.sub(r'PYW="[^"]*"', 'PYW="%s"' % w(pyw), src)
src = re.sub(r'APP="[^"]*"', 'APP="%s"' % w(app), src)
src = re.sub(r'CONFIG="[^"]*"', 'CONFIG="%s"' % w(cfg), src)
src = re.sub(r'LOGDIR="[^"]*"', 'LOGDIR="%s"' % w(logdir), src)
open(sh, 'w', encoding='utf-8').write(src)
print("start_widget.sh 路径已重写")
PY

echo ""
echo "✔ 安装完成。插件已自包含（含独立 venv）。"
echo "  可复制整个 $ROOT 目录到目标机器对应位置分发。"

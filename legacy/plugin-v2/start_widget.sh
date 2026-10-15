#!/usr/bin/env bash
# ============================================================
# Token Widget 插件 · 启动入口（联动触发）
# ------------------------------------------------------------
# 由 WorkBuddy 插件 hook（SessionStart / source=startup）触发，
# 在 WorkBuddy 打开时自动拉起桌面 token 浮窗。
#
# 特性：
#   - 幂等：已运行则跳过（锁文件 + PID 存活检测）
#   - 启用/禁用：读 config.json 的 enabled 字段
#   - 可读日志：所有动作写 logs/startup.log
#   - 明确错误：前置校验失败输出 FAIL + 原因
# ============================================================
set -u

# ---- 安装时生成的绝对路径（install.sh 会按本机重写这一块） ----
PYW="C:/Users/haida/WorkBuddy/2026-08-10-09-11-39/token-dashboard/.venv/Scripts/pythonw.exe"
APP="C:/Users/haida/.workbuddy/plugins/cache/local/token-widget-plugin/1.0.0/widget/widget_app.py"
CONFIG="C:/Users/haida/.workbuddy/plugins/cache/local/token-widget-plugin/1.0.0/config.json"
LOGDIR="C:/Users/haida/.workbuddy/plugins/cache/local/token-widget-plugin/1.0.0/logs"
# ------------------------------------------------------------

LOCK="$LOGDIR/.widget.pid"
LOG="$LOGDIR/startup.log"

mkdir -p "$LOGDIR" 2>/dev/null
ts(){ date '+%F %T'; }
log(){ echo "[$(ts)] $*" >> "$LOG"; }

log "SessionStart hook fired"

# 1) 启用/禁用检查
if grep -q '"enabled"[[:space:]]*:[[:space:]]*false' "$CONFIG" 2>/dev/null; then
  log "SKIP: disabled (config.json enabled=false)"
  exit 0
fi

# 2) 幂等检查：已有进程存活则跳过
if [ -f "$LOCK" ]; then
  _pid=$(cat "$LOCK" 2>/dev/null)
  if kill -0 "$_pid" 2>/dev/null; then
    log "SKIP: widget already running (pid $_pid)"
    exit 0
  fi
  rm -f "$LOCK"
fi

# 3) 前置校验（可读错误）
if [ ! -f "$PYW" ]; then log "FAIL: pythonw not found: $PYW"; exit 1; fi
if [ ! -f "$APP" ]; then log "FAIL: widget_app.py not found: $APP"; exit 1; fi

# 4) 后台启动并记录 PID
"$PYW" "$APP" &
echo $! > "$LOCK"
log "STARTED widget (pid $!)"
exit 0

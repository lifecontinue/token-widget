#!/usr/bin/env bash
# ============================================================
# Token Widget 插件 · 启动入口（SessionStart hook 调用）
# ------------------------------------------------------------
# v3 · 2026-10-15 重写
#
# 【v2 事故复盘】为什么重写
#   1) v2 把 pywebview 的 pythonw 路径硬编码在脚本里，且指向
#      WorkBuddy【会话工作区】内的 token-dashboard/.venv；
#      会话工作区被清理后 -> 每次启动都 FAIL，浮窗彻底消失。
#   2) v2 完全不读 config.json 的 engine / electronExe / electronApp。
#      config 早在 8/14 就切到 Electron 引擎，脚本却没同步，属于死代码。
#
# 【v3 规则】
#   - 引擎与路径一律以 config.json 为准，脚本内零硬编码路径
#   - 双引擎：electron（默认）/ pywebview（仅兼容旧安装）
#   - 相对路径基于 TOKEN_WIDGET_HOME（默认 ~/.workbuddy/token-widget）解析
#   - 幂等：锁文件 + PID 存活检测
#   - 失败必写可操作的 FAIL 原因到 logs/startup.log
#   - 配置读取用纯 bash 内置实现（不依赖 grep/sed/head/jq），
#     避免 hook 运行环境缺命令时静默取不到值
# ============================================================
set -u

# 纯 bash 解析自身路径（不依赖 dirname——hook 运行环境可能没有 coreutils）
_src="${BASH_SOURCE[0]}"
_dir="${_src%/*}"; [ "$_dir" = "$_src" ] && _dir="."
ROOT="$(cd "$_dir/.." 2>/dev/null && pwd)"; [ -n "$ROOT" ] || ROOT="$_dir/.."
CONFIG="${TOKEN_WIDGET_CONFIG:-$ROOT/config.json}"
LOGDIR="$ROOT/logs"

# hook 运行环境可能没有 mkdir，日志目录缺失时不阻塞启动（退化到插件根目录）
if [ ! -d "$LOGDIR" ]; then mkdir -p "$LOGDIR" 2>/dev/null || true; fi
LOG="$ROOT/startup.log";   [ -d "$LOGDIR" ] && LOG="$LOGDIR/startup.log"
LOCK="$ROOT/.widget.pid";  [ -d "$LOGDIR" ] && LOCK="$LOGDIR/.widget.pid"
ts(){ date '+%F %T' 2>/dev/null || printf '%s' '-'; }
log(){ echo "[$(ts)] $*" >> "$LOG" 2>/dev/null || true; }

log "SessionStart hook fired"

# ---------------- 配置读取（纯 bash 内置，无外部依赖） ----------------
# 约定：config.json 一行一个键（install.sh 以 indent=2 写出，满足）
cfg_get(){   # $1=key -> 打印字符串值；找不到打印空
  [ -f "$CONFIG" ] || return 0
  local key="$1" line val
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      *"\"$key\""*)
        val="${line#*:}"        # 去掉 key 与前缀
        val="${val#*\"}"        # 去掉到第一个引号
        val="${val%%\"*}"       # 去掉收尾引号及其后
        printf '%s' "$val"
        return 0
        ;;
    esac
  done < "$CONFIG"
  return 0
}

cfg_flag(){  # $1=key -> true / false（config 缺失时默认 true）
  [ -f "$CONFIG" ] || { echo "true"; return 0; }
  local key="$1" line
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      *"\"$key\""*)
        case "$line" in
          *true*) echo "true" ;;
          *)      echo "false" ;;
        esac
        return 0
        ;;
    esac
  done < "$CONFIG"
  echo "false"
}

# ---------------- 1) 启用 / 禁用 ----------------
if [ "$(cfg_flag enabled)" = "false" ]; then
  log "SKIP: disabled (config.json enabled=false)"
  exit 0
fi

# ---------------- 2) 幂等：已有进程存活则跳过 ----------------
if [ -f "$LOCK" ]; then
  _pid="$(cat "$LOCK" 2>/dev/null || true)"
  if [ -n "$_pid" ] && kill -0 "$_pid" 2>/dev/null; then
    log "SKIP: widget already running (pid $_pid)"
    exit 0
  fi
  rm -f "$LOCK" 2>/dev/null || true
fi

# ---------------- 3) 引擎与路径解析 ----------------
ENGINE="$(cfg_get engine)"; [ -z "$ENGINE" ] && ENGINE="electron"
TW_HOME="${TOKEN_WIDGET_HOME:-$HOME/.workbuddy/token-widget}"

resolve(){   # 相对路径 -> 基于 TW_HOME；绝对路径原样返回
  case "$1" in
    "")                          echo "" ;;
    /*|[A-Za-z]:/*|[A-Za-z]:\\*) echo "$1" ;;
    *)                           echo "$TW_HOME/$1" ;;
  esac
}

if [ "$ENGINE" = "electron" ]; then
  EXE="$(resolve "$(cfg_get electronExe)")"
  APPDIR="$(resolve "$(cfg_get electronApp)")"
  EXE_KEY="electronExe"; APP_KEY="electronApp"
else
  # 旧安装兼容：pywebview 方案（widget_app.py + venv）
  EXE="$(resolve "$(cfg_get venvPythonw)")"
  APPDIR="$(resolve "$(cfg_get appEntry)")"
  EXE_KEY="venvPythonw"; APP_KEY="appEntry"
fi

log "engine=$ENGINE exe='$EXE' app='$APPDIR' home='$TW_HOME'"

# ---------------- 4) 前置校验（可读错误） ----------------
if [ -z "$EXE" ] || [ ! -f "$EXE" ]; then
  log "FAIL: engine binary not found: '$EXE' (config.json: $EXE_KEY)"
  log "HINT: 运行 <repo>/workbuddy-plugin/scripts/install.sh 重新安装；"
  log "HINT: 不要把 token-widget 放进 WorkBuddy 会话工作区（会被清理）。"
  exit 1
fi
if [ -z "$APPDIR" ] || [ ! -e "$APPDIR" ]; then
  log "FAIL: app path not found: '$APPDIR' (config.json: $APP_KEY)"
  log "HINT: 应用应位于稳定目录（默认 $TW_HOME），会话工作区内的副本随时可能被清。"
  exit 1
fi

# ---------------- 5) 后台启动并记录 PID ----------------
if [ "$ENGINE" = "electron" ]; then
  ( cd "$APPDIR" 2>/dev/null || true; "$EXE" "$APPDIR" >/dev/null 2>&1 ) &
else
  "$EXE" "$APPDIR" >/dev/null 2>&1 &
fi
PID=$!
echo "$PID" > "$LOCK" 2>/dev/null || true
log "STARTED widget (pid $PID, engine=$ENGINE)"
exit 0

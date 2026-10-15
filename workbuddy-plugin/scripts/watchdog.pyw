# -*- coding: utf-8 -*-
"""
Token Widget 看门狗 v5（WorkBuddy 联动，不依赖插件加载器）
====================================================
监听 WorkBuddy.exe 进程：
  - WorkBuddy 起来 且 无浮窗进程 -> 拉起桌面 token 浮窗
  - WorkBuddy 退出 且 有浮窗进程 -> 关闭浮窗（随宿主同生共死）

v5 核心改进（修复 v4 的 tasklist 弹窗问题）：
  - 完全移除 tasklist.exe / PowerShell 子进程调用
  - 全部用纯 Win32 API（psapi.EnumProcesses + kernel32.OpenProcess + GetExitCodeProcess）
  - 不再 spawn 任何外部进程 -> 不再有 tasklist 残留窗口弹窗

防重复启动：
  1. 命名互斥体单例 —— 同一时刻只允许一个看门狗
  2. PID 文件追踪 —— widget 启动时写 .widget.pid，watchdog 用 OpenProcess 检查 PID 存活
  3. 启动冷却期 launchCooldownSec —— launch 后 N 秒内不做存活判断
  4. 启动失败重试上限 maxRetries
  5. 手动关闭不重拉 —— 浮窗稳定运行后消失视为手动操作

纯标准库（ctypes 互斥体 + Win32 API）。pythonw 运行，无控制台。
日志写 logs/watchdog.log。
"""
import os
import sys
import time
import json
import ctypes
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONFIG = os.path.join(ROOT, "config.json")
LOGDIR = os.path.join(ROOT, "logs")
LOG = os.path.join(LOGDIR, "watchdog.log")
STOPPED = os.path.join(LOGDIR, ".widget.stopped")
PIDFILE = os.path.join(LOGDIR, ".widget.pid")

MUTEX_NAME = "token-widget-watchdog-mutex-v1"

# ---------------- Win32 API 封装（纯标准库，不 spawn 子进程） ----------------
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
PROCESS_TERMINATE = 0x0001
STILL_ACTIVE = 259


def _enum_processes():
    """枚举所有进程 PID。"""
    PIDs = (wintypes.DWORD * 4096)()
    bytes_returned = wintypes.DWORD(0)
    if not psapi.EnumProcesses(ctypes.byref(PIDs), ctypes.sizeof(PIDs), ctypes.byref(bytes_returned)):
        return []
    count = bytes_returned.value // ctypes.sizeof(wintypes.DWORD)
    return [PIDs[i] for i in range(count) if PIDs[i]]


def _get_process_name(pid):
    """获取进程名（exe 文件名）。用 QueryFullProcessImageNameW（只需 PROCESS_QUERY_LIMITED_INFORMATION）。
    注意：不能用 GetModuleBaseNameW——它需要 PROCESS_QUERY_INFORMATION|PROCESS_VM_READ，
    在受限环境（沙箱/低权限）下会报 ERROR_ACCESS_DENIED。"""
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(512)
        size = wintypes.DWORD(512)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
    finally:
        k32.CloseHandle(h)
    return ""


def _pid_alive(pid):
    """检查 PID 是否存活（OpenProcess + GetExitCodeProcess，无 spawn）。"""
    if not pid:
        return False
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return False
    try:
        code = wintypes.DWORD(0)
        if k32.GetExitCodeProcess(h, ctypes.byref(code)):
            return code.value == STILL_ACTIVE
        return False
    finally:
        k32.CloseHandle(h)


def _kill_pid(pid):
    """终止进程。"""
    if not pid:
        return
    h = k32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if not h:
        return
    try:
        k32.TerminateProcess(h, 0)
    finally:
        k32.CloseHandle(h)


def workbuddy_running():
    """检查 WorkBuddy.exe 是否在运行。"""
    for pid in _enum_processes():
        if _get_process_name(pid).lower() == "workbuddy.exe":
            return True
    return False


# ---------------- 日志 ----------------
def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def acquire_mutex():
    """Windows 命名互斥体，确保单例。"""
    try:
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateMutexW(None, False, MUTEX_NAME)
        return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS
    except Exception:
        return True


def load_cfg():
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


def read_pidfile():
    """读取 .widget.pid 文件，返回记录的 PID。"""
    try:
        with open(PIDFILE, encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return 0


def write_pidfile(pid):
    """写入 .widget.pid 文件（widget 启动时调用）。"""
    try:
        os.makedirs(LOGDIR, exist_ok=True)
        with open(PIDFILE, "w", encoding="utf-8") as f:
            f.write(str(pid))
    except Exception:
        pass


def clear_pidfile():
    """删除 .widget.pid 文件。"""
    try:
        if os.path.exists(PIDFILE):
            os.remove(PIDFILE)
    except Exception:
        pass


def kill_widget_tree():
    """杀掉所有 widget 进程（electron 主进程 + 子进程 / pythonw）。"""
    killed = 0
    # 1) 杀 PID 文件记录的主进程
    pids = read_pidfile()
    if pids and _pid_alive(pids):
        _kill_pid(pids)
        killed += 1
    # 2) 兜底：杀掉所有 electron.exe 进程（widget 的 renderer/gpu/utility 子进程）
    #    注意：这会杀掉本机所有 Electron 应用（如 Cluely）。当前场景仅有本 widget
    #    是 Electron，可接受；若未来有多个 Electron 应用需改成精确匹配命令行。
    for pid in _enum_processes():
        if _get_process_name(pid).lower() == "electron.exe":
            _kill_pid(pid)
            killed += 1
    return killed


def main():
    cfg = load_cfg()
    if not cfg.get("enabled", True):
        log("watchdog: disabled (config.json enabled=false), exit")
        return

    engine = cfg.get("engine", "electron")
    if engine == "electron":
        exe = cfg.get("electronExe", "")
        app_dir = cfg.get("electronApp", "")
        proc_name = "electron.exe"
    else:
        exe = cfg.get("venvPythonw", "")
        app_dir = os.path.dirname(os.path.join(ROOT, cfg.get("appEntry", "widget/widget_app.py").replace("/", os.sep)))
        proc_name = "pythonw.exe"
    max_retries = int(cfg.get("maxRetries", 3))
    grace = int(cfg.get("startupGraceSec", 30))
    cooldown = int(cfg.get("launchCooldownSec", 15))

    if not os.path.exists(exe):
        log("watchdog: FAIL engine binary not found: %s" % exe)
        return
    if not os.path.exists(app_dir):
        log("watchdog: FAIL app dir not found: %s" % app_dir)
        return

    launch_pid = 0          # 本看门狗拉起的 widget launcher PID
    launch_ts = 0.0
    retry_count = 0
    started_ok = False
    failed_logged = False
    wb_was_up = False

    # 启动时检查 PID 文件（收养已存在的 widget）
    saved_pid = read_pidfile()
    if saved_pid and _pid_alive(saved_pid):
        # 检查是否是 widget 进程（electron.exe / pythonw.exe）
        if _get_process_name(saved_pid).lower() == proc_name:
            launch_pid = saved_pid
            log("watchdog: adopt existing widget pid=%d" % launch_pid)

    log("watchdog v5 started (engine=%s max_retries=%d grace=%ds cooldown=%ds)" % (engine, max_retries, grace, cooldown))
    while True:
        try:
            wb = workbuddy_running()

            # WorkBuddy 重新打开：重置会话状态
            if wb and not wb_was_up:
                if os.path.exists(STOPPED):
                    try:
                        os.remove(STOPPED)
                    except Exception:
                        pass
                retry_count = 0
                failed_logged = False
                started_ok = False
                # 不清 PID 文件——如果 widget 还在跑就保留
                log("watchdog: WorkBuddy reopened, state reset")

            now = time.time()

            # 启动冷却期：launch 后 N 秒内不做存活判断
            if launch_ts and (now - launch_ts) < cooldown:
                wb_was_up = wb
                time.sleep(3)
                continue

            # 判断浮窗是否存活：用 PID 文件 + OpenProcess 检查
            alive = False
            if launch_pid:
                alive = _pid_alive(launch_pid)
                if not alive:
                    # PID 死了，清空
                    launch_pid = 0
                    clear_pidfile()
            if not alive:
                # 尝试收养已存在的 widget（PID 文件或扫描）
                saved_pid = read_pidfile()
                if saved_pid and _pid_alive(saved_pid) and _get_process_name(saved_pid).lower() == proc_name:
                    launch_pid = saved_pid
                    alive = True
                    log("watchdog: adopt existing widget pid=%d" % launch_pid)

            if wb and not alive:
                if os.path.exists(STOPPED):
                    pass  # 已被手动关闭，本会话不再重拉
                elif started_ok:
                    # 曾稳定运行后消失 => 用户手动关闭
                    if not os.path.exists(STOPPED):
                        try:
                            open(STOPPED, "w", encoding="utf-8").write("1")
                        except Exception:
                            pass
                        log("watchdog: widget 已关闭（视为手动关闭），本会话不再自动重拉")
                    started_ok = False
                    launch_pid = 0
                    clear_pidfile()
                elif retry_count < max_retries:
                    # 启动 widget（Electron 或 pywebview）
                    import subprocess
                    p = subprocess.Popen([exe, app_dir], cwd=app_dir)
                    launch_pid = p.pid
                    launch_ts = now
                    write_pidfile(launch_pid)
                    retry_count += 1
                    log("watchdog: launch %d/%d pid=%d engine=%s" % (retry_count, max_retries, launch_pid, engine))
                else:
                    if not failed_logged:
                        log("watchdog: FAIL 连续启动失败 %d 次，停止重试（重启 WorkBuddy 恢复）" % max_retries)
                        failed_logged = True

            elif wb and alive:
                if not started_ok and launch_ts and (now - launch_ts) > grace:
                    started_ok = True
                    retry_count = 0
                    log("watchdog: widget 稳定运行")

            elif not wb and alive:
                # WorkBuddy 退出：关闭所有浮窗进程
                killed = kill_widget_tree()
                log("watchdog: WorkBuddy DOWN -> closed %d widget process(es)" % killed)
                launch_pid = 0
                launch_ts = 0.0
                retry_count = 0
                started_ok = False
                clear_pidfile()

            wb_was_up = wb
        except Exception as e:
            log("watchdog: error %r" % e)
        time.sleep(3)


if __name__ == "__main__":
    if not acquire_mutex():
        sys.exit(0)  # 已有看门狗在运行，直接退出
    try:
        main()
    except Exception as e:
        log("watchdog: fatal %r" % e)
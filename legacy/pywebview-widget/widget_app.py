# -*- coding: utf-8 -*-
"""
Token Widget · pywebview 宿主（单行 + popup 窗口方案）
==============================================
- 复用系统 WebView2，无需下载 Electron
- 主窗口永远保持单行胶囊，点击后打开独立 popup 详情窗口
- frameless + on_top + Win32 SetWindowRgn 裁剪为胶囊外形
- --wait：等待 WorkBuddy.exe 启动后再弹窗（用于开机自启 / 随软件启动）

用法：
  直接运行：        pythonw widget_app.py
  随 WorkBuddy 启动： pythonw widget_app.py --wait
"""
import os
import sys
import json
import time
import glob
import subprocess
import ctypes
from ctypes import wintypes

import webview

# pythonnet(clr) 已随 pywebview 加载；用于给 WinForms 宿主窗体设置透明键色，
# 修复 pywebview 透明模式下 Form 仍露出浅灰底色的问题（这是白/灰矩形的根因）。
try:
    import clr
    clr.AddReference('System.Drawing')
    from System.Drawing import Color as _WinColor
    _TRANSPARENT_KEY = _WinColor.FromArgb(255, 253, 2, 253)  # 极不常用的洋红，UI 不会命中
except Exception:
    _TRANSPARENT_KEY = None

# ---------------- 路径 ----------------
HERE = os.path.dirname(os.path.abspath(__file__))
WIDGET_HTML = os.path.join(HERE, "widget.html")
EXTRACT_PY = os.path.join(HERE, "extract.py")
PROJECTS_DIR = os.path.expanduser(os.path.join("~", ".workbuddy", "projects"))

# ---------------- 窗口尺寸（宽, 高） ----------------
SIZE_WIDGET = (300, 34)   # 单行胶囊，紧凑
SIZE_POPUP = (480, 520)   # 详情 popup


def widget_url(fragment=""):
    """生成带防缓存戳的本地 widget.html URL。"""
    base = "file:///" + WIDGET_HTML.replace("\\", "/") + "?_=" + str(int(time.time()))
    return base + ("#" + fragment if fragment else "")


class TokenApi:
    """暴露给前端（window.pywebview.api）的本地能力。"""

    def __init__(self):
        self.popup = None

    # 扫描 jsonl，按 messageId 去重，累计 input/output/total + 按模型拆分
    def read_tokens(self):
        files = []
        for root, _dirs, names in os.walk(PROJECTS_DIR):
            for nm in names:
                if nm.endswith(".jsonl"):
                    files.append(os.path.join(root, nm))

        seen = set()
        total_in = total_out = total = requests = 0
        bm = {}
        sessions = {}
        for fp in files:
            try:
                with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        if "rawUsage" not in line:
                            continue
                        try:
                            o = json.loads(line)
                        except Exception:
                            continue
                        pd = o.get("providerData") or {}
                        ru = pd.get("rawUsage") or {}
                        if not ru:
                            continue
                        if not o.get("timestamp"):
                            continue
                        mid = pd.get("messageId")
                        if mid:
                            if mid in seen:
                                continue
                            seen.add(mid)
                        inp = int(ru.get("prompt_tokens") or 0)
                        out = int(ru.get("completion_tokens") or 0)
                        tot = int(ru.get("total_tokens") or (inp + out))
                        total_in += inp
                        total_out += out
                        total += tot
                        requests += 1
                        model = pd.get("requestModelName") or pd.get("model") or "unknown"
                        m = bm.setdefault(model, {"model": model, "in": 0, "out": 0, "tot": 0, "cache": 0, "n": 0})
                        m["in"] += inp
                        m["out"] += out
                        m["tot"] += tot
                        m["n"] += 1
                        c = 0
                        if ru.get("prompt_cache_hit_tokens"):
                            c = int(ru["prompt_cache_hit_tokens"])
                        elif ru.get("prompt_tokens_details", {}).get("cached_tokens"):
                            c = int(ru["prompt_tokens_details"]["cached_tokens"])
                        m["cache"] += c

                        # 按对话(session)聚合：当前轮次 = 时间戳最新的 session
                        sid = o.get("sessionId") or "unknown"
                        s = sessions.setdefault(sid, {"sid": sid, "in": 0, "out": 0, "tot": 0, "n": 0, "last": 0})
                        s["in"] += inp
                        s["out"] += out
                        s["tot"] += tot
                        s["n"] += 1
                        ts = int(o.get("timestamp") or 0)
                        if ts > s["last"]:
                            s["last"] = ts
            except Exception:
                pass

        by_model = sorted(bm.values(), key=lambda x: x["tot"], reverse=True)

        # 当前轮次对话 = 最近有活动的 session
        current_session = None
        if sessions:
            cur_sid = max(sessions.values(), key=lambda x: x["last"])["sid"]
            current_session = sessions[cur_sid]

        return {
            "input": total_in,
            "output": total_out,
            "total": total,
            "requests": requests,
            "byModel": by_model,
            "currentSession": current_session,
            "scannedAt": int(time.time() * 1000),
        }

    def open_popup(self):
        """点击主窗口后打开详情 popup（只存在一个）。"""
        try:
            if self.popup is not None:
                try:
                    self.popup.show()
                    self.popup.restore()
                except Exception:
                    pass
                return True

            sw, sh = screen_size()
            pw, ph = SIZE_POPUP
            x = max(0, (sw - pw) // 2)
            y = max(0, (sh - ph) // 2)

            self.popup = webview.create_window(
                "Token 详情",
                url=widget_url("popup"),
                js_api=self,
                width=pw,
                height=ph,
                x=x,
                y=y,
                frameless=True,
                on_top=True,
                text_select=False,
                background_color="#080b16",
            )
            return True
        except Exception as e:
            _debug_log(f"open_popup error: {e}")
            return False

    def close_popup(self):
        try:
            if self.popup:
                self.popup.destroy()
                self.popup = None
        except Exception:
            self.popup = None
        return True

    def refresh(self):
        try:
            subprocess.run(
                [sys.executable, EXTRACT_PY], cwd=HERE,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
            )
            return True
        except Exception:
            return False

    def open_file(self, path):
        try:
            os.startfile(path)
        except Exception:
            pass
        return True

    def close(self):
        try:
            webview.windows[0].destroy()
        except Exception:
            pass
        return True


def is_workbuddy_running():
    try:
        ps = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Process -Name WorkBuddy -ErrorAction SilentlyContinue | Select-Object -First 1"],
            capture_output=True, text=True, timeout=10,
        )
        return bool(ps.stdout.strip())
    except Exception:
        return False


def screen_size():
    u = ctypes.windll.user32
    return u.GetSystemMetrics(0), u.GetSystemMetrics(1)


def center(w, h):
    sw, sh = screen_size()
    return max(0, (sw - w) // 2), max(0, (sh - h) // 2)


def _debug_log(msg):
    try:
        with open(os.path.join(HERE, "widget_debug.log"), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


def set_window_region(hwnd, w, h, radius):
    """用 Win32 SetWindowRgn 把窗口裁剪为圆角外形（点击穿透 + 干净边缘）。"""
    try:
        rgn = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, radius, radius)
        res = ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)
        _debug_log(f"SetWindowRgn hwnd={hwnd} size={w}x{h} radius={radius} res={res}")
    except Exception as e:
        _debug_log(f"set_window_region error: {e}")


def apply_overlay_style(win, w, h, radius):
    """
    用 Win32 SetWindowRgn 把窗口裁剪成胶囊/圆角外形（点击穿透 + 干净边缘）。
    采用不透明深色窗口方案（transparent=False），规避 WebView2 透明窗口在
    Windows 上的白底/闪烁问题。SetWindowRgn 是 Win32 API、线程安全，可安全地
    在 shown 回调（子线程）里调用；用 FindWindowW 按标题取 hwnd，避开 WinForms
    线程亲和性（之前用 form.BackColor/TransparencyKey 跨线程赋值会抛异常）。
    """
    try:
        hwnd = ctypes.windll.user32.FindWindowW(None, "Token Widget")
        if hwnd:
            set_window_region(hwnd, w, h, radius)
        else:
            _debug_log("apply_overlay_style: hwnd not found")
    except Exception as e:
        _debug_log(f"apply_overlay_style error: {e}")


def main():
    if "--wait" in sys.argv:
        while not is_workbuddy_running():
            time.sleep(3)

    api = TokenApi()
    w, h = SIZE_WIDGET
    x, y = center(w, h)

    window = webview.create_window(
        "Token Widget",
        url=widget_url(),
        js_api=api,
        width=w,
        height=h,
        min_size=(w, h),           # 覆盖默认 min_size=(200,100)，否则窗口被强制最小 100 高
        x=x,
        y=y,
        frameless=True,
        transparent=False,         # 不透明深色：彻底规避 transparent/layered 渲染闪烁
        easy_drag=False,
        on_top=True,
        text_select=False,
        background_color="#080b16",
    )

    def setup_gui():
        """
        不透明深色胶囊方案（最终稳定版）：
        彻底放弃透明（transparent=False），只用 SetWindowRgn 裁成胶囊外形。
        - 窗口是深色矩形，SetWindowRgn 裁掉圆角外 → 圆角外不渲染（非透明，DWM 裁剪）
        - 无 layered、无 colorkey、无 transparent → 无 WebView2 闪烁
        SetWindowRgn 是 Win32 API 线程安全，在新线程调用安全。
        """
        try:
            hwnd = 0
            for _ in range(120):  # 最多等 60s
                hwnd = ctypes.windll.user32.FindWindowW(None, "Token Widget")
                if hwnd:
                    break
                time.sleep(0.5)
            if not hwnd:
                _debug_log("setup_gui: hwnd not found after 60s")
                return
            set_window_region(hwnd, w, h, h)
            ctypes.windll.user32.RedrawWindow(hwnd, None, None, 0x0085)
            _debug_log("setup_gui ok hwnd=%d region applied" % hwnd)
        except Exception as e:
            _debug_log("setup_gui error: %r" % e)

    webview.start(setup_gui, gui="edgechromium", debug=False)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        import ctypes
        tb = traceback.format_exc()
        log = os.path.join(HERE, "widget_error.log")
        try:
            with open(log, "w", encoding="utf-8") as fh:
                fh.write(tb)
        except Exception:
            pass
        try:
            ctypes.windll.user32.MessageBoxW(0, tb[:3000], "Token Widget 启动失败", 0x10)
        except Exception:
            pass

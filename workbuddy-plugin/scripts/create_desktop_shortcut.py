# -*- coding: utf-8 -*-
"""创建 Token Widget 桌面快捷方式（Electron 版）：.vbs 启动器 + 尝试 .lnk。

路径从插件目录的 config.json 读取（engine=electron 时用 electronExe/electronApp），
不再硬编码——硬编码会话工作区路径是 2026-10 浮窗丢失的直接原因。
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
CONFIG = os.environ.get("TOKEN_WIDGET_CONFIG", os.path.join(PLUGIN_ROOT, "config.json"))


def load_cfg():
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


def get_desktop():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
        val, _ = winreg.QueryValueEx(k, "Desktop")
        winreg.CloseKey(k)
        if val:
            val = os.path.expandvars(val)
            if os.path.isdir(val):
                return val
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Desktop")


def main():
    cfg = load_cfg()
    exe = cfg.get("electronExe", "")
    app_dir = cfg.get("electronApp", "")
    if not exe or not os.path.isfile(exe):
        print("FAIL: electronExe 不存在：%s（先跑 install.sh）" % exe)
        return 1
    if not app_dir or not os.path.isdir(app_dir):
        print("FAIL: electronApp 目录不存在：%s（先跑 install.sh）" % app_dir)
        return 1

    desktop = get_desktop()
    print("desktop =", desktop)

    # ---- 1) .vbs 启动器（双击即启动 Electron，无黑窗）----
    vbs_path = os.path.join(desktop, "Token Widget.vbs")
    vbs = (
        'Set W = CreateObject("WScript.Shell")\n'
        'W.CurrentDirectory = "%s"\n'
        'W.Run """%s"" ""%s""", 0, False\n' % (app_dir, exe, app_dir)
    )
    with open(vbs_path, "w", encoding="utf-8") as f:
        f.write(vbs)
    print("vbs created:", vbs_path)

    # ---- 2) 尝试创建 .lnk（标准快捷方式，失败不影响 vbs）----
    lnk_path = os.path.join(desktop, "Token Widget.lnk")
    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        "$lnk = $ws.CreateShortcut('%s'); "
        "$lnk.TargetPath = '%s'; "
        "$lnk.Arguments = '\"%s\"'; "
        "$lnk.WorkingDirectory = '%s'; "
        "$lnk.Description = 'Token 消耗浮窗 (Electron)'; "
        "$lnk.Save()" % (lnk_path, exe, app_dir, app_dir)
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True, timeout=25)
        if os.path.exists(lnk_path):
            print("lnk created:", lnk_path)
        else:
            print("lnk NOT created (fallback to vbs)")
    except Exception as e:
        print("lnk creation error:", e)

    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())

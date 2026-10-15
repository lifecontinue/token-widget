# -*- coding: utf-8 -*-
"""创建 Token Widget 桌面快捷方式（Electron 版）：.vbs 启动器 + 尝试 .lnk。"""
import os
import subprocess

ELECTRON_EXE = r"C:\Users\haida\WorkBuddy\2026-08-10-09-11-39\token-dashboard\overlay\node_modules\electron\dist\electron.exe"
OVERLAY_DIR = r"C:\Users\haida\WorkBuddy\2026-08-10-09-11-39\token-dashboard\overlay"


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
    desktop = get_desktop()
    print("desktop =", desktop)

    # ---- 1) .vbs 启动器（双击即启动 Electron，无黑窗）----
    vbs_path = os.path.join(desktop, "Token Widget.vbs")
    vbs = (
        'Set W = CreateObject("WScript.Shell")\n'
        'W.CurrentDirectory = "%s"\n'
        f'W.Run """{ELECTRON_EXE}"" ""{OVERLAY_DIR}""", 0, False\n' % OVERLAY_DIR.replace("\\", "\\\\")
    )
    with open(vbs_path, "w", encoding="utf-8") as f:
        f.write(vbs)
    print("vbs created:", vbs_path)

    # ---- 2) 尝试创建 .lnk（标准快捷方式，失败不影响 vbs）----
    lnk_path = os.path.join(desktop, "Token Widget.lnk")
    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$lnk = $ws.CreateShortcut('{lnk_path}'); "
        f"$lnk.TargetPath = '{ELECTRON_EXE}'; "
        f"$lnk.Arguments = '\"{OVERLAY_DIR}\"'; "
        f"$lnk.WorkingDirectory = '{OVERLAY_DIR}'; "
        "$lnk.Description = 'Token 消耗浮窗 (Electron)'; "
        "$lnk.Save()"
    )
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=25)
        if os.path.exists(lnk_path):
            print("lnk created:", lnk_path)
        else:
            print("lnk NOT created (fallback to vbs):", r.stderr.strip()[:200])
    except Exception as e:
        print("lnk creation error:", e)

    print("DONE")


if __name__ == "__main__":
    main()

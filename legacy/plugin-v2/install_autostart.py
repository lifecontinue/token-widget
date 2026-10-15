# -*- coding: utf-8 -*-
"""
注册看门狗到 Windows「启动」文件夹，实现开机自启 + WorkBuddy 联动。
运行一次即可（用任意 Python 执行）：
    python install_autostart.py
"""
import os
import sys
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_VBS = os.path.join(HERE, "run_watchdog.vbs")

# Windows 启动文件夹（shell:startup）
STARTUP = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "Microsoft", "Windows", "Start Menu", "Programs", "Startup",
)
DST_VBS = os.path.join(STARTUP, "token-widget-watchdog.vbs")


def main():
    if not os.path.exists(SRC_VBS):
        print("FAIL: run_watchdog.vbs not found:", SRC_VBS)
        sys.exit(1)
    os.makedirs(STARTUP, exist_ok=True)
    shutil.copy2(SRC_VBS, DST_VBS)
    print("OK  watchdog 已注册到启动文件夹:", DST_VBS)
    print("    以后每次登录，看门狗自动运行，WorkBuddy 打开即拉起 token 浮窗。")


if __name__ == "__main__":
    main()

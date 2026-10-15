' Token Widget 看门狗启动器（无控制台，放 Windows 启动文件夹实现开机自启）
' 本文件由 workbuddy-plugin/scripts/install.sh --autostart 生成，请勿手改后提交。
Set W = CreateObject("WScript.Shell")
W.Run """__PYTHONW__"" ""__WATCHDOG__""", 0, False

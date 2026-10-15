' Token Widget 看门狗启动器（无控制台，放 Windows 启动文件夹实现开机自启）
Set W = CreateObject("WScript.Shell")
W.Run """C:\Users\haida\.workbuddy\binaries\python\versions\3.13.12\pythonw.exe"" ""C:\Users\haida\.workbuddy\plugins\cache\local\token-widget-plugin\1.0.0\scripts\watchdog.pyw""", 0, False

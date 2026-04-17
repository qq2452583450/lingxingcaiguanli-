@echo off
cd /d %~dp0
set "QT_QPA_PLATFORM_PLUGIN_PATH=C:\Users\蒋博丞\AppData\Local\Programs\Python\Python312\Lib\site-packages\PyQt5\Qt5\plugins\platforms"
"C:\Users\蒋博丞\AppData\Local\Programs\Python\Python312\python.exe" main.py
pause

@echo off
chcp 65001 >nul
title 零星材管理系统 Web版

echo ================================================
echo     零星材管理系统 Web版 - 启动脚本
echo ================================================
echo.

:: 检查 Python 是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8 或更高版本
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 设置环境变量
set SECRET_KEY=lingxingcai-secret-key-2026
set FLASK_DEBUG=False

echo [1/3] 检查依赖包...
python -m pip show flask >nul 2>&1
if errorlevel 1 (
    echo        正在安装 Flask 和相关依赖...
    python -m pip install flask flask-cors
)

:: 检查数据库
if not exist "%~dp0零星材管理系统.db" (
    echo [2/3] 首次运行，正在初始化数据库...
    python app.py --init-db
    echo.
)

echo [2/3] 启动 Flask 服务...
echo.

:: 启动 Flask 应用
start "零星材管理系统" cmd /c "title 零星材管理系统 - 服务窗口 && python app.py && pause"

:: 等待服务启动
timeout /t 3 /nobreak >nul

:: 检查服务是否成功启动
curl -s http://localhost:5000 >nul 2>&1
if errorlevel 1 (
    echo [警告] 服务可能未成功启动，请检查上面的日志
    echo.
)

echo [3/3] 正在打开浏览器...
start http://localhost:5000

echo.
echo ================================================
echo.
echo   ✓ 服务已启动！
echo.
echo   访问地址: http://localhost:5000
echo.
echo   注意：保持此窗口打开，关闭后服务将停止
echo.
echo ================================================
echo.

:: 打开监控窗口
pause

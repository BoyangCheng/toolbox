@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ==================================================
echo  我觉得系统应该是这样的 !
echo ==================================================

:: 检查 Python 是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    echo 下载地址: https://www.python.org/downloads/
    echo 安装时记得勾选 "Add Python to PATH"
    pause
    exit /b 1
)

:: 创建虚拟环境（如果不存在）
if not exist ".venv" (
    echo =^> 创建虚拟环境 .venv ...
    python -m venv .venv
)

:: 激活虚拟环境
call .venv\Scripts\activate.bat

:: 安装依赖
echo =^> 安装依赖 ...
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt

:: 启动服务
echo =^> 启动服务 ...
python app.py

pause

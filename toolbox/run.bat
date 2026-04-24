@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] 未检测到 Python，请先安装 Python 3.10+ 并勾选 "Add to PATH"
  echo 下载: https://www.python.org/downloads/windows/
  pause
  exit /b 1
)

if not exist ".venv" (
  echo [1/2] 创建虚拟环境...
  python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] 虚拟环境创建失败
    pause
    exit /b 1
  )
  echo [2/2] 安装依赖...
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\pip install -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] 依赖安装失败（检查网络）
    pause
    exit /b 1
  )
)

set SERVER_MODE=prod
.venv\Scripts\python app.py
pause

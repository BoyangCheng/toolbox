@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] 未检测到 Python，请先安装 Python 3.10+
  pause
  exit /b 1
)

if exist ".venv" (
  echo 检测到已有 .venv，将重装依赖...
) else (
  python -m venv .venv
)

.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt

echo.
echo ========== 安装完成 ==========
echo 双击 run.bat 启动服务
pause

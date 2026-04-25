# PowerShell 启动脚本
# 如提示"无法加载此脚本"，请先以管理员身份运行：
#   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 强制控制台与 PowerShell 输出使用 UTF-8（中文 Windows 默认 GBK 会乱码）
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    [Console]::InputEncoding  = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
    chcp 65001 > $null
} catch {}

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " 我觉得系统应该是这样的 !" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# 检查 Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[错误] 未找到 Python，请先安装 Python 3.8+" -ForegroundColor Red
    Write-Host "下载地址: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "安装时记得勾选 'Add Python to PATH'" -ForegroundColor Yellow
    Read-Host "按回车退出"
    exit 1
}

# 创建虚拟环境
if (-not (Test-Path ".venv")) {
    Write-Host "==> 创建虚拟环境 .venv ..."
    python -m venv .venv
}

# 激活虚拟环境
& ".venv\Scripts\Activate.ps1"

# 安装依赖
Write-Host "==> 安装依赖 ..."
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt

# 启动
Write-Host "==> 启动服务 ..."
python app.py

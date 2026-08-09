@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 Python。请先安装 Python 3.10 或更高版本，并勾选 Add Python to PATH。
  pause
  exit /b 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
  echo [错误] Python 版本过低。请安装 Python 3.10 或更高版本。
  pause
  exit /b 1
)

python scripts\launch_console.py
if errorlevel 1 pause

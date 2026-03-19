@echo off
setlocal enabledelayedexpansion

:: Set UTF-8 code page for Python output
chcp 65001 >nul 2>&1

title WenSi Agent

echo.
echo ================================================================
echo   WenSi Agent v1.0 - Novel Writing System
echo   Multi-Agent Architecture
echo ================================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.9+
    goto :end
)

:: Change to script directory
cd /d "%~dp0"
echo [INFO] Working directory: %CD%

:: Check .env file
if not exist ".env" (
    echo [INFO] Creating default config...
    if exist ".env.example" (
        copy .env.example .env >nul 2>&1
    ) else (
        echo OPENAI_API_KEY=> .env
        echo OPENAI_API_BASE=https://api.openai.com/v1>> .env
        echo OPENAI_MODEL=gpt-4>> .env
        echo HOST=0.0.0.0>> .env
        echo PORT=5656>> .env
    )
)

:: Check port
echo [1/3] Checking port 5656...
set PORT_IN_USE=0
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":5656 " ^| findstr "LISTENING"') do (
    set PORT_IN_USE=1
)
if !PORT_IN_USE! equ 1 (
    echo [WARN] Port 5656 is in use. Will let run.py auto-select an available port.
)

:: Check dependencies
echo [2/3] Checking dependencies...
pip show fastapi >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies
        goto :end
    )
)

:: Start server
echo [3/3] Starting server...
echo.
echo ================================================================
echo   URL: http://localhost:5656
echo   Press Ctrl+C to stop
echo ================================================================
echo.

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

python run.py
set EXITCODE=!errorlevel!

if !EXITCODE! neq 0 (
    echo.
    echo [ERROR] Python exited with code: !EXITCODE!
)

:end
echo.
echo Press any key to exit...
pause >nul
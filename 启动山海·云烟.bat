@echo off
setlocal enabledelayedexpansion

:: Set UTF-8 code page for Python output
chcp 65001 >nul 2>&1

title 山海·云烟

echo.
echo ================================================================
echo   山海·云烟 v1.0 - Novel Writing System
echo   Multi-Agent Architecture
echo ================================================================
echo.

:: Change to script directory
cd /d "%~dp0"
echo [INFO] Working directory: %CD%

:: Select interpreter
set "PYTHON_CMD=python"
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_CMD=%CD%\.venv\Scripts\python.exe"
    echo [INFO] Using project virtual environment: !PYTHON_CMD!
) else (
    echo [INFO] Project virtual environment not found. Using system Python from PATH.
)

:: Check Python
"%PYTHON_CMD%" --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found or interpreter is invalid: %PYTHON_CMD%
    goto :end
)

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
"%PYTHON_CMD%" -c "import fastapi, uvicorn, dotenv" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Required packages missing for this interpreter. Installing dependencies...
    "%PYTHON_CMD%" -m pip install -r requirements.txt
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

"%PYTHON_CMD%" run.py
set EXITCODE=!errorlevel!

if !EXITCODE! neq 0 (
    echo.
    echo [ERROR] Python exited with code: !EXITCODE!
)

:end
echo.
echo Press any key to exit...
pause >nul

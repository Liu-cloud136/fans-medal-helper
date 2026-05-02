@echo off
title B站粉丝牌助手 - Web Service

echo ========================================
echo     B站 Fans Medal Helper
echo          One-Click Start
echo ========================================
echo.

set PROJECT_DIR=%~dp0
set VENV_DIR=%PROJECT_DIR%venv
set PYTHON_CMD=python

echo [Step 1/5] Checking Python environment...
%PYTHON_CMD% --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+ and add to PATH.
    pause
    exit /b 1
)
echo [OK] Python found
%PYTHON_CMD% --version
echo.

echo [Step 2/5] Checking virtual environment...
if exist "%VENV_DIR%" (
    echo [OK] Virtual environment exists
) else (
    echo [INFO] Creating virtual environment...
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
)
echo.

echo [Step 3/5] Activating virtual environment...
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"

if not exist "%VENV_PYTHON%" (
    echo [ERROR] Virtual environment Python not found
    pause
    exit /b 1
)
echo [OK] Virtual environment activated
echo.

echo [Step 4/5] Installing/updating dependencies...
"%VENV_PIP%" install --upgrade pip -q
"%VENV_PIP%" install -r "%PROJECT_DIR%requirements.txt" -q
if errorlevel 1 (
    echo [WARNING] Some dependencies may have failed to install. Please check network connection.
)
echo [OK] Dependencies check completed
echo.

echo [Step 5/5] Starting Web Service...
echo.
echo ========================================
echo       Service Information
echo ========================================
echo Local URL:  http://localhost:8000
echo API Docs:   http://localhost:8000/docs
echo Project:    %PROJECT_DIR%
echo ========================================
echo.
echo Press Ctrl+C to stop the service
echo.

if not exist "%PROJECT_DIR%users.yaml" (
    echo [INFO] users.yaml config file not found
    echo [INFO] Please copy users.example.yaml to users.yaml and configure
    echo.
)

cd /d "%PROJECT_DIR%"
"%VENV_PYTHON%" "%PROJECT_DIR%web_server.py"

if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start service
    pause
)

@echo off
chcp 65001 >nul
title B站粉丝牌助手 - Web服务

echo ========================================
echo     B站粉丝牌助手 - 一键启动脚本
echo ========================================
echo.

set PROJECT_DIR=%~dp0
set VENV_DIR=%PROJECT_DIR%venv
set PYTHON_CMD=python
set PIP_CMD=pip

echo [1/5] 检查Python环境...
%PYTHON_CMD% --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请确保Python 3.10+ 已安装并添加到PATH
    pause
    exit /b 1
)
echo [OK] Python已找到
%PYTHON_CMD% --version
echo.

echo [2/5] 检查虚拟环境...
if exist "%VENV_DIR%" (
    echo [OK] 虚拟环境已存在
) else (
    echo [信息] 正在创建虚拟环境...
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败
        pause
        exit /b 1
    )
    echo [OK] 虚拟环境创建成功
)
echo.

echo [3/5] 激活虚拟环境...
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
set "VENV_UVICORN=%VENV_DIR%\Scripts\uvicorn.exe"

if not exist "%VENV_PYTHON%" (
    echo [错误] 虚拟环境Python不存在
    pause
    exit /b 1
)
echo [OK] 虚拟环境已激活
echo.

echo [4/5] 安装/更新依赖包...
"%VENV_PIP%" install --upgrade pip -q
"%VENV_PIP%" install -r "%PROJECT_DIR%requirements.txt" -q
if errorlevel 1 (
    echo [警告] 部分依赖安装可能失败，请检查网络连接
)
echo [OK] 依赖包检查完成
echo.

echo [5/5] 准备启动Web服务...
echo.
echo ========================================
echo       服务启动信息
echo ========================================
echo 本地访问地址: http://localhost:8000
echo API文档地址:  http://localhost:8000/docs
echo 项目目录:     %PROJECT_DIR%
echo ========================================
echo.
echo 按 Ctrl+C 停止服务
echo.

if not exist "%PROJECT_DIR%users.yaml" (
    echo [提示] 未找到users.yaml配置文件
    echo [提示] 请复制users.example.yaml为users.yaml并配置
    echo.
)

cd /d "%PROJECT_DIR%"
"%VENV_PYTHON%" "%PROJECT_DIR%web_server.py"

if errorlevel 1 (
    echo.
    echo [错误] 服务启动失败
    pause
)

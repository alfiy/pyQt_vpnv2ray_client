@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ==========================================
REM ov2n - VPN Client Launcher
REM 管理员权限由快捷方式的"以管理员身份运行"保证
REM ==========================================

REM 检测管理员权限
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  [ov2n] 需要管理员权限。
    echo.
    echo  请右键点击此文件或桌面快捷方式，
    echo  选择「以管理员身份运行」后重试。
    echo.
    pause
    exit /b 1
)

cd /d "%~dp0"

REM 查找 Python
set PYTHON=
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    python --version >nul 2>&1
    if !ERRORLEVEL! EQU 0 ( set PYTHON=python & goto :python_ok )
)
where python3 >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    python3 --version >nul 2>&1
    if !ERRORLEVEL! EQU 0 ( set PYTHON=python3 & goto :python_ok )
)

echo [ERROR] Python not found.
echo Please install Python 3.8+ from https://www.python.org/
pause
exit /b 1

:python_ok
set PYTHONPATH=%~dp0;%PYTHONPATH%
!PYTHON! "%~dp0main.py" %*

if !ERRORLEVEL! NEQ 0 (
    echo.
    echo 程序退出，错误码: !ERRORLEVEL!
    pause
)
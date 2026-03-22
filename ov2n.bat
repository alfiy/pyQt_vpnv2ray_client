@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title ov2n VPN Client
set PYTHON=
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 ( python --version >nul 2>&1 & if 0 EQU 0 set PYTHON=python )
if not defined PYTHON where python3 >nul 2>&1
if not defined PYTHON if %ERRORLEVEL% EQU 0 ( python3 --version >nul 2>&1 & if 0 EQU 0 set PYTHON=python3 )
if not defined PYTHON ( echo [ERROR] Python not found. & pause & exit /b 1 )
cd /d "%~dp0"
set PYTHONPATH=%~dp0;%PYTHONPATH%
"%PYTHON%" "%~dp0main.py" %*

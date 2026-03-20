@echo off
chcp 65001 >nul 2>&1
setlocal
REM ==========================================
REM ov2n - OpenVPN Windows Service Registration
REM Requires Administrator privileges
REM Note: No "pause" - this script is called by Python subprocess,
REM       pause would block the process indefinitely.
REM ==========================================
set SCRIPT_DIR=%~dp0
for %%i in ("%SCRIPT_DIR%\..\.." ) do set APP_ROOT=%%~fi

REM Configure paths - try win64 first
set NSSM_PATH=
if exist "%APP_ROOT%\resources\nssm\win64\nssm.exe" (
    set "NSSM_PATH=%APP_ROOT%\resources\nssm\win64\nssm.exe"
) else if exist "%APP_ROOT%\resources\nssm\nssm.exe" (
    set "NSSM_PATH=%APP_ROOT%\resources\nssm\nssm.exe"
)

set OPENVPN_EXE=%APP_ROOT%\resources\openvpn\bin\openvpn.exe
set SERVICE_NAME=OV2NService

REM Check NSSM
if not defined NSSM_PATH (
    echo [ERROR] NSSM not found in resources\nssm\
    exit /b 1
)

REM Check OpenVPN
if not exist "%OPENVPN_EXE%" (
    echo [ERROR] OpenVPN not found: %OPENVPN_EXE%
    exit /b 1
)

REM Check config file argument
if "%~1"=="" (
    echo [ERROR] Usage: register-openvpn-service.bat ^<config_file^>
    exit /b 1
)

set CONFIG_FILE=%~1
if not exist "%CONFIG_FILE%" (
    echo [ERROR] Config file not found: %CONFIG_FILE%
    exit /b 1
)

REM Remove old service if exists
echo Removing old service (if exists)...
"%NSSM_PATH%" remove %SERVICE_NAME% confirm >nul 2>&1

REM Register service
echo Registering OpenVPN service...
"%NSSM_PATH%" install %SERVICE_NAME% "%OPENVPN_EXE%" --config "%CONFIG_FILE%" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to register service
    exit /b 1
)

REM Set to manual start (not auto-start on boot)
"%NSSM_PATH%" set %SERVICE_NAME% Start SERVICE_DEMAND_START >nul 2>&1

REM Configure logging
set LOG_FILE=%APP_ROOT%\logs\openvpn-service.log
"%NSSM_PATH%" set %SERVICE_NAME% AppStdout "%LOG_FILE%" >nul 2>&1
"%NSSM_PATH%" set %SERVICE_NAME% AppStderr "%LOG_FILE%" >nul 2>&1
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateFiles 1 >nul 2>&1
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateBytes 1048576 >nul 2>&1

echo Service %SERVICE_NAME% registered successfully.
exit /b 0
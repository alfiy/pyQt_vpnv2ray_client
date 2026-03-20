@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ==========================================
REM ov2n - Windows Uninstall Script
REM Removes service, shortcuts, cleans up
REM Requires Administrator privileges
REM ==========================================

net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Please run this script as Administrator.
    pause
    exit /b 1
)

set SCRIPT_DIR=%~dp0
for %%i in ("%SCRIPT_DIR%\..\..") do set APP_ROOT=%%~fi

REM Try win64 first, then fallback
set NSSM_PATH=
if exist "%APP_ROOT%\resources\nssm\win64\nssm.exe" (
    set "NSSM_PATH=%APP_ROOT%\resources\nssm\win64\nssm.exe"
) else if exist "%APP_ROOT%\resources\nssm\nssm.exe" (
    set "NSSM_PATH=%APP_ROOT%\resources\nssm\nssm.exe"
)

echo ==========================================
echo   ov2n - Uninstaller (Windows)
echo ==========================================
echo.

REM Step 1: Stop processes
echo [1/5] Stopping running processes...
taskkill /F /IM xray.exe >nul 2>&1
echo   Xray stopped.

REM Kill any running Python main.py (ov2n GUI)
for /f "tokens=2" %%p in ('wmic process where "commandline like '%%main.py%%' and name='python.exe'" get processid 2^>nul ^| findstr /r "[0-9]"') do (
    taskkill /F /PID %%p >nul 2>&1
)
echo   ov2n GUI stopped.
echo.

REM Step 2: Stop and remove OV2NService
echo [2/5] Removing OV2NService...
net stop OV2NService >nul 2>&1
if defined NSSM_PATH (
    "!NSSM_PATH!" remove OV2NService confirm >nul 2>&1
) else (
    sc delete OV2NService >nul 2>&1
)
echo   Service removed.
echo.

REM Step 3: Remove Start Menu and Desktop shortcuts
echo [3/5] Removing shortcuts...
set "STARTMENU=%ProgramData%\Microsoft\Windows\Start Menu\Programs"
set "SHORTCUT_PATH=%STARTMENU%\ov2n VPN Client.lnk"
set "DESKTOP_SHORTCUT=%USERPROFILE%\Desktop\ov2n VPN Client.lnk"

if exist "!SHORTCUT_PATH!" (
    del "!SHORTCUT_PATH!" >nul 2>&1
    echo   Start Menu shortcut removed.
) else (
    echo   Start Menu shortcut not found (already removed).
)

if exist "!DESKTOP_SHORTCUT!" (
    del "!DESKTOP_SHORTCUT!" >nul 2>&1
    echo   Desktop shortcut removed.
) else (
    echo   Desktop shortcut not found (already removed).
)
echo.

REM Step 4: Clean up routes and DNS
echo [4/5] Cleaning up network settings...
route delete 0.0.0.0 mask 0.0.0.0 10.0.0.0 >nul 2>&1
route delete 0.0.0.0 mask 0.0.0.0 10.0.0.1 >nul 2>&1
echo   Routes cleaned.
ipconfig /flushdns >nul 2>&1
echo   DNS cache flushed.
echo.

REM Step 5: Clean up generated files
echo [5/5] Cleaning up generated files...
if exist "%APP_ROOT%\resources\images\ov2n.ico" (
    del "%APP_ROOT%\resources\images\ov2n.ico" >nul 2>&1
    echo   Generated .ico file removed.
)
if exist "%APP_ROOT%\logs" (
    echo   Log files kept in: %APP_ROOT%\logs
)
echo.

echo ==========================================
echo   Uninstall Summary
echo ==========================================
echo.
echo   [OK] Processes stopped
echo   [OK] OV2NService removed
echo   [OK] Start Menu shortcut removed
echo   [OK] Desktop shortcut removed
echo   [OK] Network settings cleaned
echo.
echo   Note: The following were NOT removed:
echo   - TAP-Windows driver (use "Add or Remove Programs")
echo   - Application files in: %APP_ROOT%
echo   - Python and PyQt5 packages
echo.
echo   To completely remove, delete the folder:
echo     %APP_ROOT%
echo.
pause
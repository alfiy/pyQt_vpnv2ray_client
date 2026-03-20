@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ==========================================
REM ov2n - Windows Installation Script
REM Installs TAP driver, Python deps, creates
REM Start Menu shortcut, registers service
REM Requires Administrator privileges
REM ==========================================

REM --- Check admin privileges ---
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 goto :need_admin

set SCRIPT_DIR=%~dp0
for %%i in ("%SCRIPT_DIR%\..\..") do set APP_ROOT=%%~fi

echo ==========================================
echo   ov2n - VPN Client Installer (Windows)
echo ==========================================
echo.
echo Application root: %APP_ROOT%
echo.

REM ---- Step 1: Create directories ----
echo [1/8] Creating directories...
if not exist "%APP_ROOT%\logs" mkdir "%APP_ROOT%\logs"
if not exist "%APP_ROOT%\resources\xray" mkdir "%APP_ROOT%\resources\xray"
if not exist "%APP_ROOT%\resources\openvpn" mkdir "%APP_ROOT%\resources\openvpn"
echo   OK
echo.

REM ---- Step 2: Check Python ----
echo [2/8] Checking Python...
set PYTHON=

REM Check "python" — but verify it's a real executable, not a Windows Store stub
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    python --version >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        set PYTHON=python
        goto :python_found
    )
)

REM Check "python3"
where python3 >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    python3 --version >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        set PYTHON=python3
        goto :python_found
    )
)

echo   [ERROR] Python not found!
echo   Please install Python 3.8+ from https://www.python.org/
echo   IMPORTANT: Check "Add Python to PATH" during installation.
echo.
echo   After installing Python, run this installer again.
echo.
pause
exit /b 1

:python_found
echo   Python found: !PYTHON!
for /f "tokens=*" %%v in ('!PYTHON! --version 2^>^&1') do echo   Version: %%v
echo.

REM ---- Step 3: Install Python dependencies ----
echo [3/8] Installing Python dependencies...
!PYTHON! -m pip install --upgrade pip >nul 2>&1
if exist "%APP_ROOT%\requirements.txt" (
    echo   Installing from requirements.txt...
    !PYTHON! -m pip install -r "%APP_ROOT%\requirements.txt"
    if !ERRORLEVEL! NEQ 0 (
        echo   [WARN] pip install from requirements.txt failed.
        echo   Trying PyQt5 directly...
        !PYTHON! -m pip install PyQt5
    )
) else (
    echo   requirements.txt not found, installing PyQt5 directly...
    !PYTHON! -m pip install PyQt5
)

REM Verify PyQt5 — explicitly import submodule PyQt5.QtCore to avoid
REM "module 'PyQt5' has no attribute 'QtCore'" AttributeError
!PYTHON! -c "from PyQt5.QtCore import PYQT_VERSION_STR; print('  PyQt5 version:', PYQT_VERSION_STR)"
set PYQT5_OK=%ERRORLEVEL%
if %PYQT5_OK% NEQ 0 (
    echo   [ERROR] PyQt5 installation failed.
    echo   Please install manually: pip install PyQt5
    pause
    exit /b 1
)
echo   OK
echo.

REM ---- Step 4: TAP-Windows driver ----
echo [4/8] Checking TAP-Windows driver...
set TAP_INSTALLED=0

REM Check if TAP driver is already installed
netsh interface show interface 2>nul | findstr /i "TAP" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set TAP_INSTALLED=1
    echo   TAP-Windows driver already installed.
    goto :step5
)

REM Search for TAP installer exe
set TAP_INSTALLER=
for %%f in ("%APP_ROOT%\resources\tap-windows\*.exe") do set TAP_INSTALLER=%%f

if not defined TAP_INSTALLER (
    echo   [WARN] No TAP-Windows installer found in:
    echo     %APP_ROOT%\resources\tap-windows\
    echo   Download from: https://openvpn.net/community-downloads/
    goto :tap_recheck
)

echo   Found TAP installer: !TAP_INSTALLER!
echo   Installing TAP-Windows driver (silent)...
"!TAP_INSTALLER!" /S
if !ERRORLEVEL! EQU 0 (
    echo   TAP-Windows driver installed successfully.
    set TAP_INSTALLED=1
    goto :tap_recheck
)

echo   [WARN] Silent install returned error !ERRORLEVEL!
echo   Trying interactive installation...
"!TAP_INSTALLER!"
if !ERRORLEVEL! EQU 0 (
    echo   TAP-Windows driver installed (interactive).
    set TAP_INSTALLED=1
) else (
    echo   [WARN] TAP installation may have failed.
    echo   You can install manually from resources\tap-windows\
)

:tap_recheck
if "%TAP_INSTALLED%"=="0" (
    netsh interface show interface 2>nul | findstr /i "TAP" >nul 2>&1
    if !ERRORLEVEL! EQU 0 set TAP_INSTALLED=1
)
echo.

REM ---- Step 5: Check NSSM ----
:step5
echo [5/8] Checking NSSM...
set NSSM_PATH=
if exist "%APP_ROOT%\resources\nssm\win64\nssm.exe" (
    set "NSSM_PATH=%APP_ROOT%\resources\nssm\win64\nssm.exe"
    goto :nssm_found
)
if exist "%APP_ROOT%\resources\nssm\nssm.exe" (
    set "NSSM_PATH=%APP_ROOT%\resources\nssm\nssm.exe"
    goto :nssm_found
)
echo   [WARN] NSSM not found.
echo   Download from: https://nssm.cc/download
echo   Place nssm.exe in resources\nssm\ or resources\nssm\win64\
goto :step6

:nssm_found
echo   NSSM found: !NSSM_PATH!
echo.

REM ---- Step 6: Check Xray and OpenVPN ----
:step6
echo [6/8] Checking Xray and OpenVPN...
set XRAY_PATH=%APP_ROOT%\resources\xray\xray.exe
if not exist "%XRAY_PATH%" (
    echo   [WARN] Xray not found at: %XRAY_PATH%
    echo   Download from: https://github.com/XTLS/Xray-core/releases
    echo   Place xray.exe + wintun.dll in resources\xray\
) else (
    echo   Xray found: %XRAY_PATH%
)
if exist "%APP_ROOT%\resources\xray\wintun.dll" (
    echo   wintun.dll found.
) else (
    echo   [WARN] wintun.dll not found. TUN mode requires wintun.dll.
)

set OPENVPN_PATH=%APP_ROOT%\resources\openvpn\bin\openvpn.exe
if exist "%OPENVPN_PATH%" (
    echo   OpenVPN found: %OPENVPN_PATH%
) else (
    echo   [WARN] OpenVPN not found at: %OPENVPN_PATH%
    echo   Install OpenVPN GUI and copy files to resources\openvpn\
)
echo.

REM ---- Step 7: Create Start Menu shortcut ----
echo [7/8] Creating Start Menu shortcut...

set "STARTMENU=%ProgramData%\Microsoft\Windows\Start Menu\Programs"
set "SHORTCUT_PATH=%STARTMENU%\ov2n VPN Client.lnk"
set "OV2N_BAT=%APP_ROOT%\ov2n.bat"
set "ICON_PATH=%APP_ROOT%\resources\images\ov2n256.png"
set "ICO_PATH=%APP_ROOT%\resources\images\ov2n.ico"

REM Convert PNG to ICO if .ico does not exist yet
if not exist "!ICO_PATH!" (
    echo   Converting icon to .ico format...
    powershell -ExecutionPolicy Bypass -Command ^
        "try { Add-Type -AssemblyName System.Drawing; $img = [System.Drawing.Image]::FromFile('%APP_ROOT%\resources\images\ov2n256.png'); $icon = [System.Drawing.Icon]::FromHandle(([System.Drawing.Bitmap]$img).GetHicon()); $fs = [System.IO.File]::Create('%ICO_PATH%'); $icon.Save($fs); $fs.Close(); Write-Host '  Icon converted successfully.' } catch { Write-Host '  [WARN] Icon conversion failed, shortcut will use default icon.' }" 2>nul
)

REM Create the Start Menu shortcut via PowerShell
powershell -ExecutionPolicy Bypass -Command ^
    "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT_PATH%'); $sc.TargetPath = '%OV2N_BAT%'; $sc.WorkingDirectory = '%APP_ROOT%'; $sc.Description = 'ov2n VPN Client - OpenVPN + Xray'; if (Test-Path '%ICO_PATH%') { $sc.IconLocation = '%ICO_PATH%' }; $sc.Save(); Write-Host '  Start Menu shortcut created.'" 2>nul

if exist "!SHORTCUT_PATH!" (
    echo   OK - Shortcut: !SHORTCUT_PATH!
) else (
    echo   [WARN] Failed to create Start Menu shortcut.
    echo   You can manually create a shortcut to: %OV2N_BAT%
)

REM Also create a Desktop shortcut
set "DESKTOP_SHORTCUT=%USERPROFILE%\Desktop\ov2n VPN Client.lnk"
powershell -ExecutionPolicy Bypass -Command ^
    "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%DESKTOP_SHORTCUT%'); $sc.TargetPath = '%OV2N_BAT%'; $sc.WorkingDirectory = '%APP_ROOT%'; $sc.Description = 'ov2n VPN Client - OpenVPN + Xray'; if (Test-Path '%ICO_PATH%') { $sc.IconLocation = '%ICO_PATH%' }; $sc.Save(); Write-Host '  Desktop shortcut created.'" 2>nul

if exist "!DESKTOP_SHORTCUT!" (
    echo   OK - Desktop: !DESKTOP_SHORTCUT!
) else (
    echo   [WARN] Failed to create Desktop shortcut.
)
echo.

REM ---- Step 8: Register OV2NService (optional, if NSSM available) ----
echo [8/8] Registering OV2NService...
if not defined NSSM_PATH (
    echo   [SKIP] NSSM not available, skipping service registration.
    echo   You can register the service later after installing NSSM.
    goto :summary
)

if not exist "%OPENVPN_PATH%" (
    echo   [SKIP] OpenVPN not found, skipping service registration.
    echo   Install OpenVPN first, then run register-openvpn-service.bat
    goto :summary
)

REM Remove stale service first so install never fails with "already exists"
sc query OV2NService >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo   Removing existing OV2NService...
    "!NSSM_PATH!" remove OV2NService confirm >nul 2>&1
)

REM Register service - no --config at this stage, set by GUI on first connect
REM or via register-openvpn-service.bat
echo   Registering OV2NService with NSSM (manual start)...
"!NSSM_PATH!" install OV2NService "!OPENVPN_PATH!" >nul 2>&1
set SVC_INSTALL=%ERRORLEVEL%

REM Configure service settings as standalone commands (NOT inside an if-block).
REM Avoids "." in APP_ROOT path (e.g. ov2n_1.4.2_windows) triggering
REM ". was unexpected at this time" when batch parser pre-scans the if-block.
if %SVC_INSTALL% NEQ 0 goto :svc_failed
"!NSSM_PATH!" set OV2NService Start SERVICE_DEMAND_START >nul 2>&1
"!NSSM_PATH!" set OV2NService AppStdout "!APP_ROOT!\logs\openvpn-service.log" >nul 2>&1
"!NSSM_PATH!" set OV2NService AppStderr "!APP_ROOT!\logs\openvpn-service.log" >nul 2>&1
"!NSSM_PATH!" set OV2NService AppRotateFiles 1 >nul 2>&1
"!NSSM_PATH!" set OV2NService AppRotateBytes 1048576 >nul 2>&1
echo   OV2NService registered successfully (manual start mode).
echo   Config will be set when you connect via the GUI, or run:
echo     scripts\windows\register-openvpn-service.bat ^<your.ovpn^>
goto :svc_done
:svc_failed
echo   [WARN] Service registration failed.
echo   You can register manually later by running:
echo     scripts\windows\register-openvpn-service.bat ^<your.ovpn^>
:svc_done
echo.

REM ---- Summary ----
:summary
echo ==========================================
echo   Installation Summary
echo ==========================================
echo.

if defined PYTHON (echo   [OK] Python: !PYTHON!) else (echo   [!!] Python - NOT FOUND)

!PYTHON! -c "from PyQt5.QtCore import PYQT_VERSION_STR" >nul 2>&1
set PYQT5_CHECK=%ERRORLEVEL%
if %PYQT5_CHECK% EQU 0 (echo   [OK] PyQt5) else (echo   [!!] PyQt5 - NOT INSTALLED)

if exist "%APP_ROOT%\resources\xray\xray.exe" (echo   [OK] Xray) else (echo   [!!] Xray - MISSING)
if exist "%APP_ROOT%\resources\xray\wintun.dll" (echo   [OK] wintun.dll) else (echo   [!!] wintun.dll - MISSING)
if "%TAP_INSTALLED%"=="1" (echo   [OK] TAP-Windows driver) else (echo   [!!] TAP-Windows driver - NOT DETECTED)
if defined NSSM_PATH (echo   [OK] NSSM) else (echo   [!!] NSSM - MISSING)
if exist "%OPENVPN_PATH%" (echo   [OK] OpenVPN) else (echo   [!!] OpenVPN - MISSING)

sc query OV2NService >nul 2>&1
set SVC_CHECK=%ERRORLEVEL%
if %SVC_CHECK% EQU 0 (echo   [OK] OV2NService registered) else (echo   [--] OV2NService not registered)

if exist "%SHORTCUT_PATH%" (echo   [OK] Start Menu shortcut) else (echo   [!!] Start Menu shortcut - MISSING)
if exist "%DESKTOP_SHORTCUT%" (echo   [OK] Desktop shortcut) else (echo   [--] Desktop shortcut - not created)

echo.
echo ==========================================
echo   How to Use
echo ==========================================
echo.
echo   1. Open "ov2n VPN Client" from Start Menu or Desktop
echo   2. In the GUI, import your OpenVPN config (.ovpn) file
echo   3. Import your Xray/V2Ray config (.json) file
echo   4. Click "Connect" to start the VPN connection
echo.
echo   For Xray TUN transparent proxy (admin PowerShell):
echo     powershell -ExecutionPolicy Bypass -File scripts\windows\start-xray.ps1
echo.
echo NOTE: First-time users should import config files through the GUI.
echo.
pause
goto :eof

:need_admin
echo [ERROR] Please run this script as Administrator.
echo Right-click install-ov2n.bat and select "Run as administrator"
pause
exit /b 1

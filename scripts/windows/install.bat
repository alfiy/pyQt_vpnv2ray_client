@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ==========================================
REM ov2n - Windows Installation Script v2
REM
REM 变更说明（对比 v1）：
REM   - 移除 NSSM 服务注册（Step 5/8 原 NSSM 检查 + Step 8 原服务注册）
REM   - OpenVPN 和 Xray 改由 vpn_process.py 直接管理进程，无需系统服务
REM   - 安装 psutil（vpn_process.py 依赖）
REM   - 保留所有其他步骤不变
REM
REM Requires: Administrator privileges
REM ==========================================

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
echo [1/7] Creating directories...
if not exist "%APP_ROOT%\logs"              mkdir "%APP_ROOT%\logs"
if not exist "%APP_ROOT%\resources\xray"   mkdir "%APP_ROOT%\resources\xray"
if not exist "%APP_ROOT%\resources\openvpn" mkdir "%APP_ROOT%\resources\openvpn"
echo   OK
echo.

REM ---- Step 2: Check Python ----
echo [2/7] Checking Python...
set PYTHON=
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    python --version >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        set PYTHON=python
        goto :python_found
    )
)
where python3 >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    python3 --version >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        set PYTHON=python3
        goto :python_found
    )
)
echo   [ERROR] Python not found. Please install Python 3.8+ from https://www.python.org/
pause
exit /b 1

:python_found
echo   Python: !PYTHON!
for /f "tokens=*" %%v in ('!PYTHON! --version 2^>^&1') do echo   Version: %%v
echo.

REM ---- Step 3: Install Python dependencies ----
echo [3/7] Installing Python dependencies...
!PYTHON! -m pip install --upgrade pip >nul 2>&1

REM 安装 requirements.txt（含 psutil，vpn_process.py 必需）
if exist "%APP_ROOT%\requirements.txt" (
    echo   Installing from requirements.txt...
    !PYTHON! -m pip install -r "%APP_ROOT%\requirements.txt"
) else (
    echo   requirements.txt not found, installing core packages...
    !PYTHON! -m pip install PyQt5 psutil
)

REM 确保 psutil 存在（vpn_process.py 依赖）
!PYTHON! -c "import psutil" >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo   Installing psutil...
    !PYTHON! -m pip install psutil
)

REM 验证 PyQt5
!PYTHON! -c "from PyQt5.QtCore import PYQT_VERSION_STR; print('  PyQt5 version:', PYQT_VERSION_STR)"
if !ERRORLEVEL! NEQ 0 (
    echo   [ERROR] PyQt5 installation failed.
    pause
    exit /b 1
)

REM 验证 psutil
!PYTHON! -c "import psutil; print('  psutil version:', psutil.__version__)"
if !ERRORLEVEL! NEQ 0 (
    echo   [ERROR] psutil installation failed.
    pause
    exit /b 1
)
echo   OK
echo.

REM ---- Step 4: TAP-Windows driver ----
echo [4/7] Checking TAP-Windows driver...
set TAP_INSTALLED=0
netsh interface show interface 2>nul | findstr /i "TAP" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set TAP_INSTALLED=1
    echo   TAP-Windows driver already installed.
    goto :step5
)

set TAP_INSTALLER=
for %%f in ("%APP_ROOT%\resources\tap-windows\*.exe") do set TAP_INSTALLER=%%f
if not defined TAP_INSTALLER (
    echo   [WARN] No TAP-Windows installer found in resources\tap-windows\
    echo   Download from: https://openvpn.net/community-downloads/
    goto :step5
)

echo   Found: !TAP_INSTALLER!
echo   Installing (silent)...
"!TAP_INSTALLER!" /S
if !ERRORLEVEL! EQU 0 (
    set TAP_INSTALLED=1
    echo   TAP-Windows installed.
) else (
    echo   [WARN] Silent install failed, trying interactive...
    "!TAP_INSTALLER!"
    if !ERRORLEVEL! EQU 0 set TAP_INSTALLED=1
)

:step5
echo.

REM ---- Step 5: Check Xray and OpenVPN ----
echo [5/7] Checking Xray and OpenVPN...
set XRAY_PATH=%APP_ROOT%\resources\xray\xray.exe
if exist "%XRAY_PATH%" (
    echo   Xray found: %XRAY_PATH%
) else (
    echo   [WARN] xray.exe not found. Download from: https://github.com/XTLS/Xray-core/releases
    echo         Place xray.exe + wintun.dll in resources\xray\
)

if exist "%APP_ROOT%\resources\xray\wintun.dll" (
    echo   wintun.dll found.
) else (
    echo   [WARN] wintun.dll not found. TUN mode requires wintun.dll alongside xray.exe.
)

set OPENVPN_PATH=%APP_ROOT%\resources\openvpn\bin\openvpn.exe
if exist "%OPENVPN_PATH%" (
    echo   OpenVPN found: %OPENVPN_PATH%
) else (
    echo   [WARN] openvpn.exe not found at: %OPENVPN_PATH%
)
echo.

REM ---- Step 6: Create shortcuts ----
echo [6/7] Creating shortcuts...
set "STARTMENU=%ProgramData%\Microsoft\Windows\Start Menu\Programs"
set "SHORTCUT_PATH=%STARTMENU%\ov2n VPN Client.lnk"
set "OV2N_BAT=%APP_ROOT%\ov2n.bat"
set "ICO_PATH=%APP_ROOT%\resources\images\ov2n.ico"

if not exist "!ICO_PATH!" (
    echo   Converting icon...
    powershell -ExecutionPolicy Bypass -Command "$img=[System.Drawing.Image]::FromFile('%APP_ROOT%\resources\images\ov2n256.png');$icon=[System.Drawing.Icon]::FromHandle(([System.Drawing.Bitmap]$img).GetHicon());$fs=[System.IO.File]::Create('%ICO_PATH%');$icon.Save($fs);$fs.Close()" 2>nul
)

powershell -ExecutionPolicy Bypass -Command "$ws=New-Object -ComObject WScript.Shell;$sc=$ws.CreateShortcut('%SHORTCUT_PATH%');$sc.TargetPath='%OV2N_BAT%';$sc.WorkingDirectory='%APP_ROOT%';if(Test-Path '%ICO_PATH%'){$sc.IconLocation='%ICO_PATH%'};$sc.Save()" 2>nul
if exist "!SHORTCUT_PATH!" (echo   Start Menu: OK) else (echo   [WARN] Start Menu shortcut failed)

set "DESKTOP=%USERPROFILE%\Desktop\ov2n VPN Client.lnk"
powershell -ExecutionPolicy Bypass -Command "$ws=New-Object -ComObject WScript.Shell;$sc=$ws.CreateShortcut('%DESKTOP%');$sc.TargetPath='%OV2N_BAT%';$sc.WorkingDirectory='%APP_ROOT%';if(Test-Path '%ICO_PATH%'){$sc.IconLocation='%ICO_PATH%'};$sc.Save()" 2>nul
if exist "!DESKTOP!" (echo   Desktop: OK) else (echo   [WARN] Desktop shortcut failed)
echo.

REM ---- Step 7: Verify vpn_process.py ----
echo [7/7] Verifying vpn_process.py...
if exist "%APP_ROOT%\vpn_process.py" (
    echo   vpn_process.py found.
) else (
    echo   [WARN] vpn_process.py not found in %APP_ROOT%
    echo          Please ensure vpn_process.py is deployed to the app root.
)
echo.

REM ---- Summary ----
echo ==========================================
echo   Installation Summary
echo ==========================================
echo.

if defined PYTHON (echo   [OK] Python: !PYTHON!) else (echo   [!!] Python - NOT FOUND)

!PYTHON! -c "from PyQt5.QtCore import PYQT_VERSION_STR" >nul 2>&1
if !ERRORLEVEL! EQU 0 (echo   [OK] PyQt5) else (echo   [!!] PyQt5 - NOT INSTALLED)

!PYTHON! -c "import psutil" >nul 2>&1
if !ERRORLEVEL! EQU 0 (echo   [OK] psutil) else (echo   [!!] psutil - NOT INSTALLED)

if exist "%APP_ROOT%\resources\xray\xray.exe"     (echo   [OK] Xray) else (echo   [!!] Xray - MISSING)
if exist "%APP_ROOT%\resources\xray\wintun.dll"   (echo   [OK] wintun.dll) else (echo   [!!] wintun.dll - MISSING)
if "%TAP_INSTALLED%"=="1" (echo   [OK] TAP-Windows) else (echo   [!!] TAP-Windows - NOT DETECTED)
if exist "%OPENVPN_PATH%"                         (echo   [OK] OpenVPN) else (echo   [!!] OpenVPN - MISSING)
if exist "%APP_ROOT%\vpn_process.py"              (echo   [OK] vpn_process.py) else (echo   [!!] vpn_process.py - MISSING)
if exist "!SHORTCUT_PATH!"                        (echo   [OK] Start Menu shortcut) else (echo   [--] Start Menu shortcut)

echo.
echo ==========================================
echo   How to Use
echo ==========================================
echo.
echo   1. Open "ov2n VPN Client" from Start Menu or Desktop
echo   2. In the GUI, import your OpenVPN config (.ovpn) file
echo   3. Import your Xray/V2Ray config (.json) file
echo   4. Click "Connect" — OpenVPN and Xray are managed directly
echo      by vpn_process.py without any system service or scripts
echo.
echo   NOTE: No NSSM service is installed. Processes are managed
echo         directly by the GUI application (vpn_process.py).
echo.
pause
goto :eof

:need_admin
echo [ERROR] Please run as Administrator.
pause
exit /b 1
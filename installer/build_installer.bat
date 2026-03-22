@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ============================================================
REM ov2n - Windows Installer Builder
REM Usage: run installer\build_installer.bat from project root
REM Output: dist\ov2n_x.x.x_setup.exe
REM ============================================================

echo ==========================================
echo   ov2n - Installer Builder
echo ==========================================
echo.

REM Switch to project root (script lives in installer\ subdirectory)
cd /d "%~dp0.."
set "PROJECT_ROOT=%CD%"
echo Project root: %PROJECT_ROOT%
echo.

REM Read version
set VERSION=1.4.3
if exist "version.txt" (
    set /p VERSION=<version.txt
    set VERSION=!VERSION: =!
)
echo Version: !VERSION!
echo.

REM ── Locate Inno Setup compiler ─────────────────────────────
set ISCC=
if exist "D:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC=D:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    goto :iscc_found
)
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    goto :iscc_found
)
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
    goto :iscc_found
)
if exist "D:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC=D:\Program Files\Inno Setup 6\ISCC.exe"
    goto :iscc_found
)
if exist "E:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC=E:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    goto :iscc_found
)
if exist "E:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC=E:\Program Files\Inno Setup 6\ISCC.exe"
    goto :iscc_found
)
if exist "D:\Program Files (x86)\Inno Setup 5\ISCC.exe" (
    set "ISCC=D:\Program Files (x86)\Inno Setup 5\ISCC.exe"
    goto :iscc_found
)
if exist "C:\Program Files (x86)\Inno Setup 5\ISCC.exe" (
    set "ISCC=C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
    goto :iscc_found
)
where ISCC.exe >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    set ISCC=ISCC.exe
    goto :iscc_found
)
echo [ERROR] ISCC.exe not found.
echo Please verify Inno Setup 6 is installed at:
echo   D:\Program Files (x86)\Inno Setup 6\
echo Download: https://jrsoftware.org/isdl.php
echo.
pause
exit /b 1

:iscc_found
echo Inno Setup: !ISCC!
echo.

REM ── Check required files ───────────────────────────────────
echo [1/5] Checking required files...
if not exist "main.py" (
    echo [ERROR] main.py not found. Run from the project root directory.
    pause
    exit /b 1
)
echo   OK main.py
if not exist "installer\ov2n_setup.iss" (
    echo [ERROR] installer\ov2n_setup.iss not found.
    pause
    exit /b 1
)
echo   OK installer\ov2n_setup.iss
if exist "resources\python\python-3.12.10-amd64.exe" (
    echo   OK resources\python\python-3.12.10-amd64.exe
) else (
    echo   [WARN] Python installer not found - target must have Python pre-installed
)
if exist "resources\tap-windows\tap-windows-installer.exe" (
    echo   OK resources\tap-windows\tap-windows-installer.exe
) else (
    echo   [WARN] TAP-Windows installer not found - TAP step will be skipped
)
if not exist "resources\images\ov2n.ico" (
    echo [ERROR] resources\images\ov2n.ico not found.
    echo Run: python -c "from PIL import Image; img=Image.open('resources/images/ov2n256.png'); img.save('resources/images/ov2n.ico',format='ICO',sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
    pause
    exit /b 1
)
echo   OK resources\images\ov2n.ico
echo.

REM ── Write version.txt ──────────────────────────────────────
echo [2/5] Writing version.txt...
echo !VERSION!> version.txt
echo   OK version = !VERSION!
echo.

REM ── Prepare output directory ───────────────────────────────
echo [3/5] Preparing output directory...
if not exist "dist" mkdir "dist"
echo   OK dist
echo.

REM ── Generate launcher files ────────────────────────────────
echo Generating launcher files...

REM Generate ov2n.bat (used internally and as fallback)
(
    echo @echo off
    echo chcp 65001 ^>nul 2^>^&1
    echo setlocal enabledelayedexpansion
    echo title ov2n VPN Client
    echo set PYTHON=
    echo where python ^>nul 2^>^&1
    echo if %%ERRORLEVEL%% EQU 0 ^( python --version ^>nul 2^>^&1 ^& if !ERRORLEVEL! EQU 0 set PYTHON=python ^)
    echo if not defined PYTHON where python3 ^>nul 2^>^&1
    echo if not defined PYTHON if %%ERRORLEVEL%% EQU 0 ^( python3 --version ^>nul 2^>^&1 ^& if !ERRORLEVEL! EQU 0 set PYTHON=python3 ^)
    echo if not defined PYTHON ^( echo [ERROR] Python not found. ^& pause ^& exit /b 1 ^)
    echo cd /d "%%~dp0"
    echo set PYTHONPATH=%%~dp0;%%PYTHONPATH%%
    echo "%%PYTHON%%" "%%~dp0main.py" %%*
) > "ov2n.bat"
echo   OK ov2n.bat

REM Generate ov2n_launcher.vbs via PowerShell base64 decode
REM (avoids cmd echo parenthesis parsing issues with VBScript content)
set "B64_VBS=JyBvdjJuIFZQTiBDbGllbnQgTGF1bmNoZXIKT3B0aW9uIEV4cGxpY2l0CgpEaW0gb1NoZWxsLCBvRlNPLCBzQXBwRGlyLCBzTWFpbgpTZXQgb1NoZWxsID0gQ3JlYXRlT2JqZWN0KCJXU2NyaXB0LlNoZWxsIikKU2V0IG9GU08gICA9IENyZWF0ZU9iamVjdCgiU2NyaXB0aW5nLkZpbGVTeXN0ZW1PYmplY3QiKQoKc0FwcERpciA9IG9GU08uR2V0UGFyZW50Rm9sZGVyTmFtZShXU2NyaXB0LlNjcmlwdEZ1bGxOYW1lKQpzTWFpbiAgID0gc0FwcERpciAmICJcbWFpbi5weSIKCklmIE5vdCBvRlNPLkZpbGVFeGlzdHMoc01haW4pIFRoZW4KICAgIE1zZ0JveCAibWFpbi5weSBub3QgZm91bmQgaW46ICIgJiBzQXBwRGlyLCB2YkNyaXRpY2FsLCAib3YybiIKICAgIFdTY3JpcHQuUXVpdCAxCkVuZCBJZgoKb1NoZWxsLkN1cnJlbnREaXJlY3RvcnkgPSBzQXBwRGlyCgpEaW0gc0NtZApzQ21kID0gImNtZCAvYyBzdGFydCAvYiAiIiIiIHB5dGhvbncgIiIiICYgc01haW4gJiAiIiIiCm9TaGVsbC5SdW4gc0NtZCwgMCwgRmFsc2UK"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$b=[System.Convert]::FromBase64String($env:B64_VBS); $s=[System.Text.Encoding]::UTF8.GetString($b); $enc=New-Object System.Text.UTF8Encoding($false); [System.IO.File]::WriteAllText((Join-Path (Get-Location) 'ov2n_launcher.vbs'),$s,$enc)"
if !ERRORLEVEL! EQU 0 (
    echo   OK ov2n_launcher.vbs
) else (
    echo   [WARN] ov2n_launcher.vbs generation failed
)
echo.

REM ── Convert scripts to CRLF via a helper ps1 ───────────────
REM Write a temporary PowerShell script to do the conversion.
REM This avoids escaping hell inside cmd for /r + PowerShell -Command.
echo [4/5] Converting scripts to CRLF line endings...
set "PS_HELPER=%TEMP%\ov2n_crlf_helper.ps1"
(
    echo $count = 0
    echo Get-ChildItem -Path 'scripts\windows' -Recurse -Include *.bat,*.ps1,*.cmd ^| ForEach-Object {
    echo     $text = [System.IO.File]::ReadAllText($_.FullName^)
    echo     $text = $text -replace "`r`n", "`n"
    echo     $text = $text -replace "`n", "`r`n"
    echo     [System.IO.File]::WriteAllText($_.FullName, $text, [System.Text.Encoding]::UTF8^)
    echo     $count++
    echo }
    echo Write-Host "  OK $count script files converted"
) > "!PS_HELPER!"
powershell -ExecutionPolicy Bypass -NoProfile -File "!PS_HELPER!"
del "!PS_HELPER!" >nul 2>&1
echo.

REM ── Build with Inno Setup ──────────────────────────────────
echo [5/5] Building installer...
echo.
"!ISCC!" /DMyAppVersion="!VERSION!" "installer\ov2n_setup.iss"
set BUILD_RESULT=!ERRORLEVEL!

echo.
if %BUILD_RESULT% EQU 0 (
    echo ==========================================
    echo   Build successful!
    echo ==========================================
    echo.
    set "OUTPUT_FILE=dist\ov2n_!VERSION!_setup.exe"
    if exist "!OUTPUT_FILE!" (
        for %%f in ("!OUTPUT_FILE!") do (
            echo   Output : %%~ff
            echo   Size   : %%~zf bytes
        )
    )
) else (
    echo ==========================================
    echo   [ERROR] Build failed. Code: %BUILD_RESULT%
    echo ==========================================
    echo.
    echo Common causes:
    echo   1. Syntax error in ov2n_setup.iss - check output above
    echo   2. Source file path mismatch in [Files] section
    echo   3. resources\images\ov2n.ico missing or invalid
)

echo.
pause
exit /b %BUILD_RESULT%
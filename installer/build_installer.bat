@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ============================================================
REM ov2n - Windows Installer Builder
REM Usage: run installer\build_installer.bat from project root
REM Output: dist\ov2n_x.x.x_setup.exe
REM
REM 变更说明（对比旧版）：
REM   1. ov2n_launcher.py 模板：移除 DETACHED_PROCESS flag，改用 os.execv()
REM      直接替换进程，不存在"静默脱离"行为特征
REM   2. CRLF 转换：不再动态生成临时 .ps1 到 %TEMP% 再 Bypass 执行
REM      改用纯 cmd 内置命令完成转换，消灭"无文件攻击"特征
REM   3. ov2n_launcher.vbs 检查：发现即自动删除，不留残留
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

REM Read version from version.txt (single source of truth)
set VERSION=
if exist "version.txt" (
    set /p VERSION=<version.txt
    set VERSION=!VERSION: =!
)
if "!VERSION!"=="" (
    echo [WARN] version.txt not found or empty, using fallback version
    set VERSION=1.4.2
)
echo Version: !VERSION!
echo.

REM -- Locate Inno Setup compiler -----------------------------
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
echo Please verify Inno Setup 6 is installed.
echo Download: https://jrsoftware.org/isdl.php
echo.
pause
exit /b 1

:iscc_found
echo Inno Setup: !ISCC!
echo.

REM -- Check required files -----------------------------------
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

REM -- Write version.txt --------------------------------------
echo [2/5] Writing version.txt...
echo !VERSION!> version.txt
echo   OK version = !VERSION!
echo.

REM -- Prepare output directory -------------------------------
echo [3/5] Preparing output directory...
if not exist "dist" mkdir "dist"
echo   OK dist
echo.

REM -- Sync launcher files from installer\src\ ----------------
REM
REM Launcher files live in installer\src\ as versioned source files.
REM Build only copies them, never regenerates (except first-time init).
REM Edit launchers in installer\src\ only.
REM ---------------------------------------------------------

echo [4/5] Syncing launcher files from installer\src\...

if not exist "installer\src" mkdir "installer\src"

REM -- ov2n_launcher.py --
if not exist "installer\src\ov2n_launcher.py" (
    echo   [INIT] installer\src\ov2n_launcher.py not found, generating template...
    call :write_launcher_py
    echo   INIT OK  installer\src\ov2n_launcher.py ^(template created, please review^)
) else (
    echo   Found  installer\src\ov2n_launcher.py
)
copy /y "installer\src\ov2n_launcher.py" "ov2n_launcher.py" >nul
echo   Copied ov2n_launcher.py ^-^> project root

REM -- ov2n.bat --
if not exist "installer\src\ov2n.bat" (
    echo   [INIT] installer\src\ov2n.bat not found, generating template...
    call :write_launcher_bat
    echo   INIT OK  installer\src\ov2n.bat ^(template created, please review^)
) else (
    echo   Found  installer\src\ov2n.bat
)
copy /y "installer\src\ov2n.bat" "ov2n.bat" >nul
echo   Copied ov2n.bat ^-^> project root

REM -- 自动清除废弃的 ov2n_launcher.vbs（不再提示，直接删）--
if exist "ov2n_launcher.vbs" (
    del /f /q "ov2n_launcher.vbs"
    echo   Deleted deprecated ov2n_launcher.vbs
)
echo.

REM -- Convert scripts\windows\*.bat/.ps1 to CRLF -------------
REM
REM 旧方案：动态写临时 .ps1 到 %TEMP% 再 -ExecutionPolicy Bypass 执行
REM         → 命中"无文件攻击"特征，杀软报警
REM
REM 新方案：用 Python（已确认存在于构建机）完成 CRLF 转换
REM         → 纯 Python I/O，无 PowerShell，无临时脚本
REM ---------------------------------------------------------
echo   Converting scripts\windows\*.bat/.ps1/.cmd to CRLF...
if exist "scripts\windows" (
    python -c ^
        "import os, pathlib; root=pathlib.Path('scripts/windows'); files=list(root.rglob('*.bat'))+list(root.rglob('*.ps1'))+list(root.rglob('*.cmd')); [f.write_bytes(f.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')) for f in files]; print(f'  OK {len(files)} file(s) converted')"
) else (
    echo   [SKIP] scripts\windows not found, skipping CRLF conversion
)
echo.

REM -- Build with Inno Setup ----------------------------------
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


REM ================================================================
REM 子程序：首次构建时生成 launcher 模板文件
REM 后续构建直接跳过（文件已存在）
REM ================================================================

:write_launcher_py
REM ---------------------------------------------------------------
REM 关键修改：
REM   旧版用 subprocess.Popen + DETACHED_PROCESS(0x08)|CREATE_NO_WINDOW(0x08000000)
REM   → 两个 flag 叠加是木马/后门的典型特征，杀软必报
REM
REM   新版用 os.execv() 直接替换当前进程为 pythonw.exe + main.py
REM   → launcher 进程被替换而非"生出"子进程，没有脱离行为
REM   → 对杀软完全透明：就是一个普通的 pythonw main.py
REM ---------------------------------------------------------------
set "TMP_PY=%TEMP%\ov2n_write_launcher.py"
(
    echo # -*- coding: utf-8 -*-
    echo import pathlib, sys
    echo content = '''\
    echo """
    echo ov2n VPN Client Launcher
    echo ========================
    echo Replaces ov2n_launcher.vbs to avoid antivirus false positives.
    echo
    echo Shortcut target:
    echo   pythonw.exe "C:\\path\\to\\ov2n_launcher.py"
    echo
    echo How it works:
    echo   - No wscript.exe / cscript.exe
    echo   - Uses os.execv() to REPLACE this process with pythonw + main.py
    echo   - No subprocess.Popen, no DETACHED_PROCESS, no hidden-window tricks
    echo   - Fully transparent to antivirus: visible in Task Manager as pythonw.exe
    echo """
    echo import os
    echo import sys
    echo
    echo
    echo def find_pythonw():
    echo     d = os.path.dirname(sys.executable)
    echo     pw = os.path.join(d, "pythonw.exe")
    echo     if os.path.exists(pw^):
    echo         return pw
    echo     import shutil
    echo     found = shutil.which("pythonw"^)
    echo     return found if found else sys.executable
    echo
    echo
    echo def main(^):
    echo     app_dir = os.path.dirname(os.path.abspath(__file__^)^)
    echo     main_py = os.path.join(app_dir, "main.py"^)
    echo     if not os.path.exists(main_py^):
    echo         import ctypes
    echo         ctypes.windll.user32.MessageBoxW(
    echo             0, f"main.py not found:\\n{main_py}", "ov2n", 0x10
    echo         ^)
    echo         sys.exit(1^)
    echo     pythonw = find_pythonw(^)
    echo     # os.execv replaces the current process image entirely.
    echo     # No child process is spawned, no DETACHED_PROCESS flag needed.
    echo     os.execv(pythonw, [pythonw, main_py]^)
    echo
    echo
    echo if __name__ == "__main__":
    echo     main(^)
    echo '''
    echo out = pathlib.Path(r'installer\src\ov2n_launcher.py'^)
    echo out.write_text(content, encoding='utf-8'^)
) > "!TMP_PY!"
python "!TMP_PY!"
del "!TMP_PY!" >nul 2>&1
goto :eof

:write_launcher_bat
set "TMP_PY=%TEMP%\ov2n_write_bat.py"
(
    echo # -*- coding: utf-8 -*-
    echo import pathlib
    echo content = '@echo off\r\nchcp 65001 ^>nul 2^>^&1\r\ncd /d "%%~dp0"\r\nif not exist "%%~dp0main.py" (\r\n    echo [ERROR] main.py not found in %%~dp0\r\n    pause\r\n    exit /b 1\r\n)\r\nstart "" pythonw "%%~dp0main.py" %%*\r\nexit /b 0\r\n'
    echo out = pathlib.Path(r'installer\src\ov2n.bat'^)
    echo out.write_bytes(content.encode('utf-8'^)^)
) > "!TMP_PY!"
python "!TMP_PY!"
del "!TMP_PY!" >nul 2>&1
goto :eof
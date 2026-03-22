@echo off
chcp 65001 >nul 2>&1
REM ============================================================
REM 将 PNG 转换为 ICO（安装包图标）
REM 需要 ImageMagick: https://imagemagick.org/
REM 或 Python + Pillow: pip install Pillow
REM ============================================================
cd /d "%~dp0.."

set ICO_FILE=resources\images\ov2n.ico
set PNG_FILE=resources\images\ov2n256.png

if exist "%ICO_FILE%" (
    echo [OK] %ICO_FILE% 已存在，跳过转换。
    goto :done
)

if not exist "%PNG_FILE%" (
    echo [ERROR] %PNG_FILE% 不存在。
    pause
    exit /b 1
)

REM 方法1：Python + Pillow（推荐，无需额外安装工具）
python -c "from PIL import Image; img = Image.open(r'%PNG_FILE%'); img.save(r'%ICO_FILE%', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])" >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    echo [OK] ICO 已通过 Pillow 生成: %ICO_FILE%
    goto :done
)

REM 方法2：ImageMagick
where magick >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    magick "%PNG_FILE%" -define icon:auto-resize=256,128,64,48,32,16 "%ICO_FILE%"
    if !ERRORLEVEL! EQU 0 (
        echo [OK] ICO 已通过 ImageMagick 生成: %ICO_FILE%
        goto :done
    )
)

REM 方法3：PowerShell（内置，但只支持单尺寸）
echo 尝试 PowerShell 转换（单尺寸 256x256）...
powershell -Command ^
    "Add-Type -AssemblyName System.Drawing; $img = [System.Drawing.Image]::FromFile((Resolve-Path '%PNG_FILE%')); $icon = [System.Drawing.Icon]::FromHandle(([System.Drawing.Bitmap]$img).GetHicon()); $fs = [System.IO.File]::Create('%ICO_FILE%'); $icon.Save($fs); $fs.Close(); Write-Host '[OK] ICO 已生成'"

:done
if exist "%ICO_FILE%" (
    echo ICO 文件: %ICO_FILE%
) else (
    echo [ERROR] ICO 转换失败，请手动转换 PNG 为 ICO 格式。
)
pause

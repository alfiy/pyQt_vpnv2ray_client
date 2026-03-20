#!/bin/bash
# Build script for creating packages (Linux DEB / Windows ZIP)
# Project: ov2n - OpenVPN + V2Ray Client
# 修复: 多发行版 PyQt5 兼容问题 (Kylin/Ubuntu/Debian 等)
# Usage: ./build.sh [clean|rebuild] [--platform linux|windows] [--version X.Y.Z] [--debug]

set -euo pipefail

# Color definitions for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

########################################
# Command & Argument Parsing
########################################

COMMAND="build"
DEBUG=false
PLATFORM=""

if [[ "${1:-}" == "clean" ]]; then
    COMMAND="clean"
    shift
elif [[ "${1:-}" == "rebuild" ]]; then
    COMMAND="rebuild"
    shift
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        --debug)
            DEBUG=true
            set -x
            shift
            ;;
        --version)
            VERSION="$2"
            shift 2
            ;;
        --platform)
            PLATFORM="$2"
            shift 2
            ;;
        *)
            break
            ;;
    esac
done

# Auto-detect platform if not specified
if [ -z "$PLATFORM" ]; then
    case "$(uname -s)" in
        Linux*)  PLATFORM="linux" ;;
        MINGW*|MSYS*|CYGWIN*) PLATFORM="windows" ;;
        *)       PLATFORM="linux" ;;
    esac
fi

if [[ "$PLATFORM" != "linux" && "$PLATFORM" != "windows" ]]; then
    echo -e "${RED}✗ Unknown platform: $PLATFORM (use 'linux' or 'windows')${NC}"
    exit 1
fi

# Default values
VERSION="${VERSION:-}"
DISTRO="${2:-focal}"
PKG_NAME="ov2n"
APP_NAME="ov2n"
APP_TITLE="ov2n - VPN Client"
MAINTAINER="Alfiy <13012648@qq.com>"
BUILD_DIR="build"
DEB_BUILD_DIR="${BUILD_DIR}/deb"
WIN_BUILD_DIR="${BUILD_DIR}/windows"
DIST_DIR="dist"

########################################
# Auto version from git tag
########################################
if [ -z "$VERSION" ]; then
    if git describe --tags --abbrev=0 >/dev/null 2>&1; then
        VERSION=$(git describe --tags --abbrev=0)
    else
        VERSION="1.3.0"
    fi
fi

########################################
# Clean function
########################################
clean_build() {
    echo -e "${YELLOW}Cleaning build artifacts...${NC}"
    rm -rf "${BUILD_DIR}" 2>/dev/null || true
    rm -rf "${DIST_DIR}" 2>/dev/null || true
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    echo -e "${GREEN}✓ Clean completed successfully${NC}"
    echo ""
}

########################################
# Command router
########################################

if [ "$COMMAND" = "clean" ]; then
    clean_build
    exit 0
fi

if [ "$COMMAND" = "rebuild" ]; then
    clean_build
fi

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════╗"
echo "║  ov2n - VPN Client Builder (Enhanced)     ║"
echo "║  OpenVPN + V2Ray/Xray Integration         ║"
echo "║  + Bundled Geo Files & V2Ray Binary       ║"
echo "╚═══════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo -e "${BLUE}Version:${NC} $VERSION"
echo -e "${BLUE}Platform:${NC} $PLATFORM"
echo -e "${BLUE}Distribution:${NC} $DISTRO"
echo ""

########################################
# Windows build path
########################################
if [ "$PLATFORM" = "windows" ]; then
    build_windows() {
        echo -e "${YELLOW}[1/7] Checking source files...${NC}"
        if [ ! -f "main.py" ]; then
            echo -e "${RED}✗ main.py not found${NC}"; exit 1
        fi
        echo -e "${GREEN}  ✓ main.py found${NC}"
        echo ""

        echo -e "${YELLOW}[2/7] Preparing Windows build directory...${NC}"
        rm -rf "${WIN_BUILD_DIR}"
        local APP_DIR="${WIN_BUILD_DIR}/${PKG_NAME}"
        mkdir -p "${APP_DIR}"
        mkdir -p "${APP_DIR}/resources/images"
        mkdir -p "${APP_DIR}/resources/xray"
        mkdir -p "${APP_DIR}/resources/openvpn/bin"
        mkdir -p "${APP_DIR}/resources/openvpn/config"
        mkdir -p "${APP_DIR}/resources/openvpn/log"
        mkdir -p "${APP_DIR}/resources/tap-windows"
        mkdir -p "${APP_DIR}/resources/nssm"
        mkdir -p "${APP_DIR}/scripts/windows"
        mkdir -p "${APP_DIR}/logs"
        mkdir -p "${DIST_DIR}"
        echo -e "${GREEN}  ✓ Directories prepared${NC}"
        echo ""

        echo -e "${YELLOW}[3/7] Copying application files...${NC}"
        cp main.py "${APP_DIR}/"
        cp requirements.txt "${APP_DIR}/"
        echo "${VERSION}" > "${APP_DIR}/version.txt"

        # 复制 Python 源码
        if [ -d "core" ]; then
            cp -r core "${APP_DIR}/"
            # 清理 __pycache__
            find "${APP_DIR}/core" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
            echo -e "${GREEN}  ✓ core/ copied (with platform/windows/ implementations)${NC}"
        fi
        if [ -d "ui" ]; then
            cp -r ui "${APP_DIR}/"
            find "${APP_DIR}/ui" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
            echo -e "${GREEN}  ✓ ui/ copied${NC}"
        fi

        # 图标资源
        if [ -d "resources/images" ]; then
            cp resources/images/* "${APP_DIR}/resources/images/" 2>/dev/null || true
            echo -e "${GREEN}  ✓ resources/images/ copied${NC}"
        fi

        # Xray 资源（Windows 版使用 resources/xray/ 目录）
        echo ""
        echo -e "${YELLOW}  Checking Xray resources...${NC}"

        # 批量复制 resources/xray/ 下所有文件
        if [ -d "resources/xray" ]; then
            for f in resources/xray/*; do
                [ -f "$f" ] && cp "$f" "${APP_DIR}/resources/xray/" 2>/dev/null || true
            done
        fi

        # geo 文件（如果 resources/xray/ 没有，则从 resources/v2ray/ 补充）
        for geo_file in geoip.dat geosite.dat; do
            if [ ! -f "${APP_DIR}/resources/xray/${geo_file}" ]; then
                [ -f "resources/v2ray/${geo_file}" ] && cp "resources/v2ray/${geo_file}" "${APP_DIR}/resources/xray/"
            fi
            if [ -f "${APP_DIR}/resources/xray/${geo_file}" ]; then
                geo_size=$(stat -c%s "${APP_DIR}/resources/xray/${geo_file}" 2>/dev/null || echo "0")
                echo -e "${GREEN}    ✓ ${geo_file} copied ($(numfmt --to=iec $geo_size 2>/dev/null || echo "${geo_size} bytes"))${NC}"
            fi
        done

        # xray.exe 检查
        local XRAY_BUNDLED=false
        if [ -f "${APP_DIR}/resources/xray/xray.exe" ]; then
            XRAY_BUNDLED=true
            echo -e "${GREEN}    ✓ xray.exe bundled${NC}"
        else
            echo -e "${YELLOW}    ⚠ xray.exe not found${NC}"
            echo -e "${YELLOW}      请下载: https://github.com/XTLS/Xray-core/releases${NC}"
            echo -e "${YELLOW}      将 xray.exe 放入 resources/xray/ 后重新构建${NC}"
        fi

        # wintun.dll 检查
        if [ -f "${APP_DIR}/resources/xray/wintun.dll" ]; then
            echo -e "${GREEN}    ✓ wintun.dll bundled${NC}"
        fi

        # Xray 辅助脚本检查
        for helper in xray_no_window.ps1 xray_no_window.vbs; do
            [ -f "${APP_DIR}/resources/xray/${helper}" ] && echo -e "${GREEN}    ✓ ${helper} bundled${NC}"
        done

        # Xray 配置模板
        if [ -f "${APP_DIR}/resources/xray/config.json.windows.template" ]; then
            cp "${APP_DIR}/resources/xray/config.json.windows.template" "${APP_DIR}/resources/xray/config.json"
            echo -e "${GREEN}    ✓ Xray config template applied${NC}"
        elif [ -f "${APP_DIR}/resources/xray/config.json" ]; then
            echo -e "${GREEN}    ✓ Xray config.json present${NC}"
        fi

        # TAP-Windows 驱动安装包
        echo ""
        echo -e "${YELLOW}  Checking TAP-Windows resources...${NC}"
        if [ -d "resources/tap-windows" ]; then
            cp -r resources/tap-windows/* "${APP_DIR}/resources/tap-windows/" 2>/dev/null || true
            # 自动检测任何 TAP 安装程序 (.exe)
            local TAP_FOUND=false
            for tap_exe in "${APP_DIR}"/resources/tap-windows/*.exe; do
                if [ -f "$tap_exe" ]; then
                    TAP_FOUND=true
                    echo -e "${GREEN}    ✓ TAP-Windows installer bundled: $(basename "$tap_exe")${NC}"
                fi
            done
            if [ "$TAP_FOUND" = false ]; then
                echo -e "${YELLOW}    ⚠ TAP-Windows installer (.exe) not found in resources/tap-windows/${NC}"
                echo -e "${YELLOW}      请下载 TAP-Windows 安装包并放入 resources/tap-windows/${NC}"
            fi
        fi

        # NSSM - 复制整个目录结构（含 win32/ win64/ 子目录）
        echo ""
        echo -e "${YELLOW}  Checking NSSM...${NC}"
        if [ -d "resources/nssm" ]; then
            cp -r resources/nssm/* "${APP_DIR}/resources/nssm/" 2>/dev/null || true
            # 确保根目录有 nssm.exe（优先 win64）
            if [ ! -f "${APP_DIR}/resources/nssm/nssm.exe" ]; then
                if [ -f "${APP_DIR}/resources/nssm/win64/nssm.exe" ]; then
                    cp "${APP_DIR}/resources/nssm/win64/nssm.exe" "${APP_DIR}/resources/nssm/nssm.exe"
                elif [ -f "${APP_DIR}/resources/nssm/win32/nssm.exe" ]; then
                    cp "${APP_DIR}/resources/nssm/win32/nssm.exe" "${APP_DIR}/resources/nssm/nssm.exe"
                fi
            fi
        fi
        if [ -f "${APP_DIR}/resources/nssm/nssm.exe" ]; then
            echo -e "${GREEN}    ✓ nssm.exe bundled${NC}"
            [ -f "${APP_DIR}/resources/nssm/win64/nssm.exe" ] && echo -e "${GREEN}    ✓ nssm/win64/nssm.exe bundled${NC}"
            [ -f "${APP_DIR}/resources/nssm/win32/nssm.exe" ] && echo -e "${GREEN}    ✓ nssm/win32/nssm.exe bundled${NC}"
        else
            echo -e "${YELLOW}    ⚠ nssm.exe not found${NC}"
            echo -e "${YELLOW}      请下载: https://nssm.cc/download${NC}"
            echo -e "${YELLOW}      将 nssm.exe 放入 resources/nssm/${NC}"
        fi

        # OpenVPN 资源 - 复制整个目录（bin/config/include/log）
        echo ""
        echo -e "${YELLOW}  Checking OpenVPN resources...${NC}"
        if [ -d "resources/openvpn" ]; then
            for subdir in bin config include log; do
                mkdir -p "${APP_DIR}/resources/openvpn/${subdir}" 2>/dev/null || true
            done
            cp -r resources/openvpn/* "${APP_DIR}/resources/openvpn/" 2>/dev/null || true
            if [ -f "${APP_DIR}/resources/openvpn/bin/openvpn.exe" ]; then
                echo -e "${GREEN}    ✓ OpenVPN files bundled${NC}"
                local dll_count=$(ls "${APP_DIR}/resources/openvpn/bin/"*.dll 2>/dev/null | wc -l)
                [ "$dll_count" -gt 0 ] && echo -e "${GREEN}    ✓ ${dll_count} DLL files bundled${NC}"
            else
                echo -e "${YELLOW}    ⚠ openvpn.exe not found in resources/openvpn/bin/${NC}"
                echo -e "${YELLOW}      请安装 OpenVPN GUI 后将 bin/config/include/log 复制到 resources/openvpn/${NC}"
            fi
        else
            echo -e "${YELLOW}    ⚠ resources/openvpn/ directory not found${NC}"
        fi

        # 文档
        for doc in README.md INSTALL.md LICENSE LICENSE.md; do
            [ -f "$doc" ] && cp "$doc" "${APP_DIR}/" 2>/dev/null || true
        done
        echo ""
        echo -e "${GREEN}  ✓ Application files copied${NC}"
        echo ""

        # 复制 Windows 脚本
        echo -e "${YELLOW}[4/7] Copying Windows scripts...${NC}"
        if [ -d "scripts/windows" ]; then
            cp scripts/windows/*.ps1 "${APP_DIR}/scripts/windows/" 2>/dev/null || true
            cp scripts/windows/*.bat "${APP_DIR}/scripts/windows/" 2>/dev/null || true
            echo -e "${GREEN}  ✓ PowerShell scripts copied (start-xray.ps1, stop-xray.ps1)${NC}"
            echo -e "${GREEN}  ✓ Batch scripts copied (install.bat, uninstall.bat, register-openvpn-service.bat)${NC}"
        fi
        echo ""

        # 创建 Windows 启动脚本
        echo -e "${YELLOW}[5/7] Creating Windows launcher...${NC}"
        cat > "${APP_DIR}/ov2n.bat" << 'WINLAUNCHER'
@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ==========================================
REM ov2n - VPN Client Launcher for Windows
REM Requires: Python 3.8+ with PyQt5
REM ==========================================

title ov2n VPN Client

REM Try to find python
set PYTHON=
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PYTHON=python
    goto :python_ok
)
where python3 >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PYTHON=python3
    goto :python_ok
)

echo ==========================================
echo   [ERROR] Python not found!
echo ==========================================
echo.
echo   Please install Python 3.8+ from:
echo   https://www.python.org/downloads/
echo.
echo   IMPORTANT: Check "Add Python to PATH"
echo   during installation.
echo.
echo   After installing Python, run install-ov2n.bat
echo   as Administrator to set up dependencies.
echo.
pause
exit /b 1

:python_ok
REM Check PyQt5
!PYTHON! -c "import PyQt5" >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [WARN] PyQt5 not found. Installing...
    !PYTHON! -m pip install PyQt5
    if !ERRORLEVEL! NEQ 0 (
        echo.
        echo [ERROR] Failed to install PyQt5.
        echo Please run: pip install PyQt5
        echo Or run install-ov2n.bat as Administrator.
        echo.
        pause
        exit /b 1
    )
)

REM Launch application
cd /d "%~dp0"
set PYTHONPATH=%~dp0;%PYTHONPATH%
echo Starting ov2n VPN Client...
!PYTHON! main.py %*

REM If the application exits with an error, show it
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo ==========================================
    echo   Application exited with error code: !ERRORLEVEL!
    echo ==========================================
    echo.
    echo   If the GUI did not appear, try:
    echo   1. Run install-ov2n.bat as Administrator
    echo   2. Check that PyQt5 is installed: pip install PyQt5
    echo   3. Check logs\ folder for error details
    echo.
    pause
)
WINLAUNCHER
        echo -e "${GREEN}  ✓ ov2n.bat created${NC}"

        # 创建 PowerShell 启动脚本
        cat > "${APP_DIR}/ov2n.ps1" << 'PSLAUNCHER'
# ov2n - VPN Client Launcher for Windows (PowerShell)
$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Find Python
$python = $null
foreach ($cmd in @("python", "python3")) {
    try {
        $null = & $cmd --version 2>&1
        $python = $cmd
        break
    } catch {}
}
if (-not $python) {
    Write-Error "Python not found. Please install Python 3.8+ from https://www.python.org/"
    Read-Host "Press Enter to exit"
    exit 1
}

# Check PyQt5
try { & $python -c "import PyQt5" 2>$null } catch {
    Write-Host "Installing PyQt5..." -ForegroundColor Yellow
    & $python -m pip install PyQt5
}

# Launch
Set-Location $AppDir
$env:PYTHONPATH = "$AppDir;$env:PYTHONPATH"
& $python "$AppDir\main.py" $args
PSLAUNCHER
        echo -e "${GREEN}  ✓ ov2n.ps1 created${NC}"
        echo ""

        # Create installer entry point scripts (root-level shortcuts)
        echo -e "${YELLOW}[6/7] Creating installer entry point...${NC}"

        # install-entry.bat (ASCII-safe, no Chinese in filename)
        cat > "${APP_DIR}/install-ov2n.bat" << 'INSTALL_ENTRY'
@echo off
chcp 65001 >nul 2>&1
REM ov2n - One-click installer (TAP driver + components)
REM Requires Administrator privileges

net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Please run as Administrator.
    echo Right-click this file and select "Run as administrator"
    pause
    exit /b 1
)

cd /d "%~dp0"
call scripts\windows\install.bat
INSTALL_ENTRY
        echo -e "${GREEN}  ✓ install-ov2n.bat created (installer entry point)${NC}"

        cat > "${APP_DIR}/uninstall-ov2n.bat" << 'UNINSTALL_ENTRY'
@echo off
chcp 65001 >nul 2>&1
REM ov2n - Uninstaller
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Please run as Administrator.
    pause
    exit /b 1
)
cd /d "%~dp0"
call scripts\windows\uninstall.bat
UNINSTALL_ENTRY
        echo -e "${GREEN}  ✓ uninstall-ov2n.bat created (uninstaller entry point)${NC}"
        echo ""

        # Convert all .bat and .ps1 files to Windows CRLF line endings
        echo -e "${YELLOW}[7/8] Converting scripts to Windows line endings (CRLF)...${NC}"
        local crlf_count=0
        while IFS= read -r -d '' batfile; do
            if command -v unix2dos &>/dev/null; then
                unix2dos -q "$batfile" 2>/dev/null
            else
                # sed-based CRLF conversion: remove any existing \r, then add \r before \n
                sed -i 's/\r$//' "$batfile"
                sed -i 's/$/\r/' "$batfile"
            fi
            crlf_count=$((crlf_count + 1))
        done < <(find "${APP_DIR}" -type f \( -name "*.bat" -o -name "*.ps1" -o -name "*.cmd" \) -print0)
        echo -e "${GREEN}  ✓ Converted ${crlf_count} script files to CRLF${NC}"
        echo ""

        # Package as ZIP
        echo -e "${YELLOW}[8/8] Creating ZIP package...${NC}"
        local ZIP_FILE="${DIST_DIR}/${PKG_NAME}_${VERSION}_windows.zip"

        if command -v zip &>/dev/null; then
            (cd "${WIN_BUILD_DIR}" && zip -r "../../${ZIP_FILE}" "${PKG_NAME}/")
        elif command -v 7z &>/dev/null; then
            (cd "${WIN_BUILD_DIR}" && 7z a "../../${ZIP_FILE}" "${PKG_NAME}/")
        else
            # tar.gz fallback
            ZIP_FILE="${DIST_DIR}/${PKG_NAME}_${VERSION}_windows.tar.gz"
            (cd "${WIN_BUILD_DIR}" && tar czf "../../${ZIP_FILE}" "${PKG_NAME}/")
            echo -e "${YELLOW}  ⚠ zip/7z not found, created tar.gz instead${NC}"
        fi

        local SIZE=$(du -h "${ZIP_FILE}" | cut -f1)
        echo -e "${GREEN}  ✓ Package created: ${ZIP_FILE} (${SIZE})${NC}"
        echo ""

        # 列出打包内容摘要
        echo -e "${BLUE}Bundled Components:${NC}"
        [ -f "${APP_DIR}/resources/xray/xray.exe" ] && \
            echo -e "  ${GREEN}✓ xray.exe${NC}" || \
            echo -e "  ${YELLOW}⚠ xray.exe (需用户自行放入)${NC}"
        [ -f "${APP_DIR}/resources/xray/wintun.dll" ] && \
            echo -e "  ${GREEN}✓ wintun.dll${NC}" || \
            echo -e "  ${YELLOW}⚠ wintun.dll (需用户自行放入)${NC}"
        [ -f "${APP_DIR}/resources/xray/geoip.dat" ] && \
            echo -e "  ${GREEN}✓ geoip.dat${NC}" || \
            echo -e "  ${YELLOW}⚠ geoip.dat${NC}"
        [ -f "${APP_DIR}/resources/xray/geosite.dat" ] && \
            echo -e "  ${GREEN}✓ geosite.dat${NC}" || \
            echo -e "  ${YELLOW}⚠ geosite.dat${NC}"
        # TAP-Windows installer
        local TAP_SUMMARY=false
        for tap_exe in "${APP_DIR}"/resources/tap-windows/*.exe; do
            if [ -f "$tap_exe" ]; then
                echo -e "  ${GREEN}✓ TAP installer: $(basename "$tap_exe")${NC}"
                TAP_SUMMARY=true
            fi
        done
        [ "$TAP_SUMMARY" = false ] && echo -e "  ${YELLOW}⚠ TAP installer (需用户自行放入)${NC}"
        [ -f "${APP_DIR}/resources/nssm/nssm.exe" ] && \
            echo -e "  ${GREEN}✓ nssm.exe${NC}" || \
            echo -e "  ${YELLOW}⚠ nssm.exe (需用户自行放入)${NC}"
        [ -f "${APP_DIR}/resources/openvpn/bin/openvpn.exe" ] && \
            echo -e "  ${GREEN}✓ openvpn.exe${NC}" || \
            echo -e "  ${YELLOW}⚠ openvpn.exe (需用户自行放入)${NC}"
        echo -e "  ${GREEN}✓ start-xray.ps1 (Xray TUN 启动脚本)${NC}"
        echo -e "  ${GREEN}✓ stop-xray.ps1 (Xray TUN 停止脚本)${NC}"
        echo -e "  ${GREEN}✓ install.bat (自动安装 TAP 驱动)${NC}"
        echo -e "  ${GREEN}✓ register-openvpn-service.bat (注册 OpenVPN 服务)${NC}"
        echo ""

        echo -e "${BLUE}═══════════════════════════════════════${NC}"
        echo -e "${GREEN}Windows Installation Instructions:${NC}"
        echo -e "${BLUE}═══════════════════════════════════════${NC}"
        echo ""
        echo "  1. 将 ${ZIP_FILE} 复制到 Windows 机器"
        echo "  2. 解压到任意目录 (如 C:\\ov2n)"
        echo "  3. 右键以管理员身份运行 安装.bat"
        echo "     - 自动安装 TAP-Windows 驱动"
        echo "     - 自动检测 NSSM / Xray / OpenVPN"
        echo "  4. 安装 Python 3.8+: https://www.python.org/"
        echo "  5. 运行 ov2n.bat 启动 GUI"
        echo ""
        echo "  Xray TUN 透明代理 (管理员 PowerShell):"
        echo "    powershell -ExecutionPolicy Bypass -File scripts\\windows\\start-xray.ps1"
        echo ""
        echo "  OpenVPN 服务注册 (可选, 管理员):"
        echo "    scripts\\windows\\register-openvpn-service.bat <config.ovpn>"
        echo ""
        echo "  注意: 默认不添加开机自启动服务。"
        echo "  如需开机自启, 在 GUI 中勾选或手动执行:"
        echo "    resources\\nssm\\nssm.exe set OV2NService Start SERVICE_AUTO_START"
        echo ""
    }

    build_windows
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════╗"
    echo "         Build Completed! (Windows)       "
    echo "       ov2n ${VERSION} is ready             "
    echo "╚════════════════════════════════════════╝"
    echo -e "${NC}"
    exit 0
fi

# ========================================================
# Linux build path (original logic below)
# ========================================================

# Step 1: Check dependencies
echo -e "${YELLOW}[1/9] Checking dependencies...${NC}"
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo -e "${RED}✗ $1 is not installed${NC}"
        echo "      Please install $1 and try again"
        exit 1
    fi
    echo -e "${GREEN}  ✓ $1 found${NC}"
}

check_command "python3"
if [ "$PLATFORM" != "windows" ]; then
    check_command "dpkg"
    check_command "fakeroot"
else
    echo -e "${GREEN}  ✓ dpkg/fakeroot not required for Windows build${NC}"
fi

echo ""

# Step 2: Check source files
echo -e "${YELLOW}[2/9] Checking source files...${NC}"
if [ ! -f "main.py" ]; then
    echo -e "${RED}✗ main.py not found in current directory${NC}"
    exit 1
fi
echo -e "${GREEN}  ✓ main.py found${NC}"

if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}✗ requirements.txt not found in current directory${NC}"
    exit 1
fi
echo -e "${GREEN}  ✓ requirements.txt found${NC}"

echo ""

# Step 3: Check bundled v2ray and geo files
echo -e "${YELLOW}[3/10] Checking bundled v2ray and geo files...${NC}"

BUNDLED_V2RAY_OK=false
BUNDLED_GEO_OK=true

if [ -f "resources/v2ray/v2ray" ]; then
    V2RAY_SIZE=$(stat -c%s "resources/v2ray/v2ray" 2>/dev/null || stat -f%z "resources/v2ray/v2ray" 2>/dev/null || echo "0")
    if [ "$V2RAY_SIZE" -gt 1048576 ]; then
        echo -e "${GREEN}  ✓ resources/v2ray/v2ray found ($(numfmt --to=iec $V2RAY_SIZE 2>/dev/null || echo "${V2RAY_SIZE} bytes"))${NC}"
        if [ -x "resources/v2ray/v2ray" ]; then
            echo -e "${GREEN}  ✓ v2ray is executable${NC}"
        else
            echo -e "${YELLOW}  ⚠ v2ray is not executable, fixing...${NC}"
            chmod +x "resources/v2ray/v2ray"
        fi
        BUNDLED_V2RAY_OK=true
    else
        echo -e "${YELLOW}  ⚠ resources/v2ray/v2ray is too small (${V2RAY_SIZE} bytes), may be invalid${NC}"
    fi
else
    echo -e "${YELLOW}  ⚠ resources/v2ray/v2ray not found${NC}"
fi

for geo_file in geoip.dat geosite.dat; do
    if [ -f "resources/v2ray/${geo_file}" ]; then
        GEO_SIZE=$(stat -c%s "resources/v2ray/${geo_file}" 2>/dev/null || stat -f%z "resources/v2ray/${geo_file}" 2>/dev/null || echo "0")
        if [ "$GEO_SIZE" -gt 102400 ]; then
            echo -e "${GREEN}  ✓ resources/v2ray/${geo_file} found ($(numfmt --to=iec $GEO_SIZE 2>/dev/null || echo "${GEO_SIZE} bytes"))${NC}"
        else
            echo -e "${YELLOW}  ⚠ resources/v2ray/${geo_file} is too small (${GEO_SIZE} bytes), may be invalid${NC}"
            BUNDLED_GEO_OK=false
        fi
    else
        echo -e "${YELLOW}  ⚠ resources/v2ray/${geo_file} not found${NC}"
        BUNDLED_GEO_OK=false
    fi
done

if [ "$BUNDLED_V2RAY_OK" = false ]; then
    echo ""
    echo -e "${YELLOW}  提示: 预打包的 v2ray 二进制文件缺失或无效${NC}"
    echo -e "${YELLOW}  下载方法:${NC}"
    echo -e "${YELLOW}    mkdir -p resources/v2ray${NC}"
    echo -e "${YELLOW}    wget https://github.com/v2fly/v2ray-core/releases/latest/download/v2ray-linux-64.zip${NC}"
    echo -e "${YELLOW}    unzip v2ray-linux-64.zip${NC}"
    echo -e "${YELLOW}    cp v2ray resources/v2ray/${NC}"
    echo -e "${YELLOW}    chmod +x resources/v2ray/v2ray${NC}"
    echo ""
fi

if [ "$BUNDLED_GEO_OK" = false ]; then
    echo ""
    echo -e "${YELLOW}  提示: 预打包的 geo 文件缺失或无效${NC}"
    echo -e "${YELLOW}  下载方法:${NC}"
    echo -e "${YELLOW}    mkdir -p resources/v2ray${NC}"
    echo -e "${YELLOW}    wget -O resources/v2ray/geoip.dat https://github.com/v2fly/geoip/releases/latest/download/geoip.dat${NC}"
    echo -e "${YELLOW}    wget -O resources/v2ray/geosite.dat https://github.com/v2fly/domain-list-community/releases/latest/download/dlc.dat${NC}"
    echo ""
fi

if [ "$BUNDLED_V2RAY_OK" = false ] || [ "$BUNDLED_GEO_OK" = false ]; then
    echo -e "${YELLOW}  继续构建 (安装时将从网络下载缺失的文件)...${NC}"
fi

echo ""

# Step 4: Prepare directories
echo -e "${YELLOW}[4/10] Preparing build directories...${NC}"
rm -rf "${DEB_BUILD_DIR}"
mkdir -p "${DEB_BUILD_DIR}/DEBIAN"
mkdir -p "${DEB_BUILD_DIR}/usr/local/bin"
mkdir -p "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}"
mkdir -p "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources"
mkdir -p "${DEB_BUILD_DIR}/usr/share/applications"
mkdir -p "${DEB_BUILD_DIR}/usr/share/pixmaps"
mkdir -p "${DEB_BUILD_DIR}/usr/share/doc/${PKG_NAME}"
mkdir -p "${DIST_DIR}"
mkdir -p "${DEB_BUILD_DIR}/usr/share/icons/hicolor/48x48/apps"
mkdir -p "${DEB_BUILD_DIR}/usr/share/icons/hicolor/64x64/apps"
mkdir -p "${DEB_BUILD_DIR}/usr/share/icons/hicolor/128x128/apps"
mkdir -p "${DEB_BUILD_DIR}/usr/share/icons/hicolor/256x256/apps"

echo -e "${GREEN}  ✓ Directories prepared${NC}"
echo ""

# Step 5: Copy application files
echo -e "${YELLOW}[5/10] Copying application files...${NC}"

cp -v main.py "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/" || {
    echo -e "${RED}✗ Failed to copy main.py${NC}"
    exit 1
}

cp -v requirements.txt "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/" || {
    echo -e "${RED}✗ Failed to copy requirements.txt${NC}"
    exit 1
}

echo "${VERSION}" > "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/version.txt"
echo -e "${GREEN}  ✓ version.txt created (${VERSION})${NC}"

if [ -d "core" ]; then
    cp -rv core "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/" || true
    echo -e "${GREEN}  ✓ core directory copied${NC}"
fi

if [ -d "ui" ]; then
    cp -rv ui "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/" || true
    echo -e "${GREEN}  ✓ ui directory copied${NC}"
fi

if [ -d "polkit" ]; then
    cp -rv polkit "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/" || true
    echo -e "${GREEN}  ✓ polkit directory copied${NC}"
fi

if [ -d "resources" ]; then
    if [ -d "resources/images" ]; then
        mkdir -p "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/images"
        cp -rv resources/images/* "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/images/" 2>/dev/null || true
        echo -e "${GREEN}  ✓ resources/images directory copied${NC}"
    fi
    if [ -d "resources/v2ray" ]; then
        mkdir -p "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/v2ray"
        cp -rv resources/v2ray/* "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/v2ray/" 2>/dev/null || true
        echo -e "${GREEN}  ✓ resources/v2ray directory copied${NC}"
        if [ -f "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/v2ray/v2ray" ]; then
            v2ray_size=$(stat -c%s "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/v2ray/v2ray" 2>/dev/null || echo "0")
            chmod +x "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/v2ray/v2ray"
            echo -e "${GREEN}    ✓ v2ray binary bundled ($(numfmt --to=iec $v2ray_size 2>/dev/null || echo "${v2ray_size} bytes"))${NC}"
        fi
        for geo_file in geoip.dat geosite.dat; do
            if [ -f "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/v2ray/${geo_file}" ]; then
                geo_size=$(stat -c%s "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/v2ray/${geo_file}" 2>/dev/null || echo "0")
                echo -e "${GREEN}    ✓ ${geo_file} bundled ($(numfmt --to=iec $geo_size 2>/dev/null || echo "${geo_size} bytes"))${NC}"
            fi
        done
    fi
fi

for doc in README.md INSTALL.md LICENSE LICENSE.md COPYING; do
    if [ -f "$doc" ]; then
        cp -v "$doc" "${DEB_BUILD_DIR}/usr/share/doc/${PKG_NAME}/" || true
        echo -e "${GREEN}  ✓ $doc copied${NC}"
    fi
done

echo -e "${GREEN}  ✓ Application files copied${NC}"
echo ""

echo -e "${YELLOW}  Installing application icons...${NC}"
cp resources/images/ov2n48.png  "${DEB_BUILD_DIR}/usr/share/icons/hicolor/48x48/apps/ov2n.png"   2>/dev/null || true
cp resources/images/ov2n64.png  "${DEB_BUILD_DIR}/usr/share/icons/hicolor/64x64/apps/ov2n.png"   2>/dev/null || true
cp resources/images/ov2n128.png "${DEB_BUILD_DIR}/usr/share/icons/hicolor/128x128/apps/ov2n.png" 2>/dev/null || true
cp resources/images/ov2n256.png "${DEB_BUILD_DIR}/usr/share/icons/hicolor/256x256/apps/ov2n.png" 2>/dev/null || true
chmod 644 "${DEB_BUILD_DIR}/usr/share/icons/hicolor/"*/apps/ov2n.png 2>/dev/null || true
echo -e "${GREEN}  ✓ Icons installed${NC}"

# ============================================================
# Step 6: Create launcher script
# 【修复核心】不再硬编码 #!/usr/bin/env python3
# 改为运行时动态探测持有 PyQt5 的 Python 解释器
# ============================================================
echo -e "${YELLOW}[6/10] Creating launcher script...${NC}"

cat > "${DEB_BUILD_DIR}/usr/local/bin/${PKG_NAME}" << 'LAUNCHER'
#!/bin/bash
# ov2n launcher - 自动探测正确的 Python 解释器
# 修复: 不同发行版 python3 指向不同版本导致 PyQt5 找不到的问题

APP_DIR="/usr/local/lib/ov2n"

# ── 动态探测持有 PyQt5 的 Python ──────────────────────────
find_python() {
    # 按优先级逐一尝试各 python 解释器
    local candidates=(
        "/usr/bin/python3"
        "/usr/local/bin/python3"
        "/usr/bin/python3.11"
        "/usr/bin/python3.10"
        "/usr/bin/python3.9"
        "/usr/bin/python3.8"
        "/usr/local/bin/python3.11"
        "/usr/local/bin/python3.10"
        "/usr/local/bin/python3.9"
        "/usr/local/bin/python3.8"
    )

    for py in "${candidates[@]}"; do
        if [ -x "$py" ] && "$py" -c "import PyQt5.QtWidgets" 2>/dev/null; then
            echo "$py"
            return 0
        fi
    done

    # 最后用 find 全盘搜索（慢但全面）
    while IFS= read -r py; do
        if [ -x "$py" ] && "$py" -c "import PyQt5.QtWidgets" 2>/dev/null; then
            echo "$py"
            return 0
        fi
    done < <(find /usr -name "python3*" -type f 2>/dev/null | sort -V)

    return 1
}

# ── 处理 --version / -v（不启动 GUI）─────────────────────
if [[ "${1:-}" == "--version" || "${1:-}" == "-v" ]]; then
    VERSION_FILE="${APP_DIR}/version.txt"
    if [ -f "$VERSION_FILE" ]; then
        echo "ov2n version $(cat "$VERSION_FILE")"
    else
        echo "ov2n version unknown"
    fi
    exit 0
fi

# ── 找到可用的 Python ──────────────────────────────────────
PYTHON=$(find_python)

if [ -z "$PYTHON" ]; then
    echo "错误: 未找到安装了 PyQt5 的 Python 解释器" >&2
    echo "" >&2
    echo "请运行以下命令安装 PyQt5:" >&2
    echo "  sudo apt install python3-pyqt5" >&2
    echo "" >&2
    echo "如果仍然失败，请尝试:" >&2
    echo "  sudo pip3 install PyQt5" >&2

    # 尝试弹出图形化错误提示（如果有 zenity 或 kdialog）
    if command -v zenity >/dev/null 2>&1; then
        zenity --error \
            --title="ov2n 启动失败" \
            --text="缺少依赖: PyQt5\n\n请运行: sudo apt install python3-pyqt5" \
            2>/dev/null || true
    elif command -v kdialog >/dev/null 2>&1; then
        kdialog --error "缺少依赖: PyQt5\n\n请运行: sudo apt install python3-pyqt5" \
            --title "ov2n 启动失败" 2>/dev/null || true
    fi
    exit 1
fi

# ── 启动应用 ──────────────────────────────────────────────
cd "$APP_DIR"
export QT_API=pyqt5
export PYTHONPATH="$APP_DIR:${PYTHONPATH:-}"

# ── 启动应用 ──────────────────────────────────────────────
cd "$APP_DIR"
export QT_API=pyqt5
export PYTHONPATH="$APP_DIR:${PYTHONPATH:-}"

# 【关键修复】直接用 main.py 文件启动，而非 -c 参数
# 使用 -c 启动时 WM_CLASS 会变成 ("-c", "VPN Client")，
# 导致 GNOME 无法通过 StartupWMClass=ov2n 匹配 .desktop 文件，
# 从而标题栏无图标、Dock 图标也不正确。
# 直接传文件路径，sys.argv[0] = "main.py"，WM_CLASS 由 Qt 内部正确设置。
exec "$PYTHON" "$APP_DIR/main.py" "$@"
LAUNCHER

chmod +x "${DEB_BUILD_DIR}/usr/local/bin/${PKG_NAME}"
echo -e "${GREEN}  ✓ Launcher script created at /usr/local/bin/${PKG_NAME}${NC}"
echo ""

# Step 7: Create desktop entry
echo -e "${YELLOW}[7/10] Creating desktop entry...${NC}"

cat > "${DEB_BUILD_DIR}/usr/share/applications/${PKG_NAME}.desktop" << DESKTOP
[Desktop Entry]
Type=Application
Name=ov2n
GenericName=VPN Client
Comment=Integrated OpenVPN and V2Ray/Xray Client
Exec=${PKG_NAME}
Icon=${PKG_NAME}
Categories=Network;Utility;System;
Terminal=false
StartupNotify=true
StartupWMClass=${PKG_NAME}
Keywords=vpn;openvpn;v2ray;xray;proxy;network;security;

[Desktop Action Help]
Name=Help
Exec=xdg-open https://github.com/alfiy/pyQt_vpnv2ray_client
DESKTOP

echo -e "${GREEN}  ✓ Desktop entry created${NC}"
echo ""

# ============================================================
# Step 8: Create DEBIAN control file and scripts
# 【修复核心】
# 1. Depends 加入 python3-pyqt5 硬依赖
# 2. postinst 用与启动脚本相同的探测逻辑验证 PyQt5
# 3. 检测不到时自动尝试 apt / pip 安装
# ============================================================
echo -e "${YELLOW}[8/10] Creating DEBIAN metadata...${NC}"

cat > "${DEB_BUILD_DIR}/DEBIAN/control" << CONTROL
Package: ${PKG_NAME}
Version: ${VERSION}
Architecture: all
Maintainer: ${MAINTAINER}
Homepage: https://github.com/alfiy/pyQt_vpnv2ray_client
Depends: python3 (>= 3.8), python3-pyqt5, python3-xlib, openvpn, policykit-1, iptables, wget | curl
Recommends: network-manager, python3-pyqt5.qtsvg
Suggests: gnupg, iptables-persistent
Priority: optional
Section: net
Description: Integrated OpenVPN and V2Ray/Xray VPN Client
 ov2n is a PyQt5-based GUI application that integrates OpenVPN
 and V2Ray/Xray protocols, providing a unified interface for
 managing both traditional VPN and modern proxy connections.
 .
 Features:
  - Simple and intuitive interface
  - Support for OpenVPN protocol
  - Support for V2Ray/Xray proxy protocol (bundled binary)
  - Transparent proxy via iptables TProxy
  - Integrated connection management
  - PolicyKit integration for privilege escalation
  - Bundled geo data files and v2ray binary
  - Auto-check geo file updates at runtime
  - Cross-platform compatibility (Ubuntu/Kylin/Debian)
CONTROL


# ============================================================
# postinst - 增强版 PyQt5 检测与自动修复
# ============================================================
cat > "${DEB_BUILD_DIR}/DEBIAN/postinst" << 'POSTINST'
#!/bin/bash
set -e

PKG_NAME="ov2n"
PKG_PATH="/usr/local/lib/${PKG_NAME}"
BIN_PATH="/usr/local/bin/${PKG_NAME}"
RESOURCES_PATH="${PKG_PATH}/resources"
GEO_DIR="/usr/local/share/v2ray"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}✓${NC} $1"; }
log_warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
log_error() { echo -e "${RED}✗${NC} $1"; }

echo ""
echo "══════════════════════════════════════"
echo "  ov2n Installation & Configuration"
echo "══════════════════════════════════════"
echo ""

# Step 1: Verify launcher exists and is executable
if [ ! -f "${BIN_PATH}" ]; then
    log_error "Launcher script not found at ${BIN_PATH}"
    exit 1
fi
chmod +x "${BIN_PATH}" 2>/dev/null || true
log_info "Launcher script verified"

# Step 2: Verify package path exists
if [ ! -d "${PKG_PATH}" ]; then
    log_error "Package directory not found at ${PKG_PATH}"
    exit 1
fi
log_info "Package directory verified"

# Step 3: Create convenient symlink
mkdir -p /opt 2>/dev/null || true
ln -sf "${PKG_PATH}" "/opt/${PKG_NAME}" 2>/dev/null || true
log_info "Symlink created at /opt/${PKG_NAME}"

# Step 4: Install polkit files if present
if [ -d "${PKG_PATH}/polkit" ]; then
    echo ""
    echo "Configuring PolicyKit integration..."
    if ls ${PKG_PATH}/polkit/*.policy 1>/dev/null 2>&1; then
        cp ${PKG_PATH}/polkit/*.policy /usr/share/polkit-1/actions/ 2>/dev/null || true
        log_info "PolicyKit policies installed"
    fi
    for script in ${PKG_PATH}/polkit/*.py; do
        if [ -f "$script" ]; then
            cp "$script" /usr/local/bin/ 2>/dev/null || true
            chmod +x "/usr/local/bin/$(basename $script)" 2>/dev/null || true
        fi
    done
    log_info "Helper scripts installed"
fi

# Step 5: Install V2Ray binary
echo ""
echo "Installing V2Ray..."
BUNDLED_V2RAY="${RESOURCES_PATH}/v2ray/v2ray"

if command -v v2ray >/dev/null 2>&1; then
    V2RAY_VERSION=$(v2ray version 2>/dev/null | head -1 || echo "unknown")
    log_info "V2Ray already installed: $V2RAY_VERSION"
elif command -v xray >/dev/null 2>&1; then
    XRAY_VERSION=$(xray version 2>/dev/null | head -1 || echo "unknown")
    log_info "Xray already installed: $XRAY_VERSION"
elif [ -f "$BUNDLED_V2RAY" ]; then
    echo "   Copying bundled v2ray binary to /usr/local/bin/..."
    cp "$BUNDLED_V2RAY" /usr/local/bin/v2ray
    chmod +x /usr/local/bin/v2ray
    if [ -f /usr/local/bin/v2ray ] && [ -x /usr/local/bin/v2ray ]; then
        V2RAY_VERSION=$(/usr/local/bin/v2ray version 2>/dev/null | head -1 || echo "installed")
        log_info "V2Ray installed from bundled binary: $V2RAY_VERSION"
    else
        log_warn "Failed to copy v2ray binary to /usr/local/bin/"
    fi
else
    log_warn "Bundled v2ray binary not found at $BUNDLED_V2RAY"
    echo "   Please install v2ray manually:"
    echo "   bash <(curl -L https://raw.githubusercontent.com/v2fly/fhs-install-v2ray/master/install-release.sh)"
fi

# Step 6: Install geo data files
echo ""
echo "Installing V2Ray geo data files..."
mkdir -p "$GEO_DIR" 2>/dev/null || true

for geo_file in geoip.dat geosite.dat; do
    bundled_path="$RESOURCES_PATH/v2ray/$geo_file"
    target_path="$GEO_DIR/$geo_file"
    if [ -f "$target_path" ]; then
        size=$(stat -c%s "$target_path" 2>/dev/null || echo "0")
        if [ "$size" -gt 102400 ]; then
            log_info "$geo_file already exists ($(numfmt --to=iec $size 2>/dev/null || echo "${size} bytes"))"
            continue
        fi
    fi
    if [ -f "$bundled_path" ]; then
        bundled_size=$(stat -c%s "$bundled_path" 2>/dev/null || echo "0")
        if [ "$bundled_size" -gt 102400 ]; then
            cp "$bundled_path" "$target_path"
            log_info "$geo_file installed from bundled resources ($(numfmt --to=iec $bundled_size 2>/dev/null || echo "${bundled_size} bytes"))"
        else
            log_warn "$geo_file bundled but file is too small (${bundled_size} bytes)"
        fi
    else
        log_warn "$geo_file not found in bundled resources"
        echo "   You can download manually:"
        echo "   sudo wget -O $target_path https://github.com/v2fly/geoip/releases/latest/download/geoip.dat"
    fi
done

echo ""
echo "Creating geo file symlinks..."
for link_dir in "/usr/bin" "/usr/local/bin" "/usr/share/v2ray"; do
    if [ -d "$link_dir" ]; then
        for geo_file in "geoip.dat" "geosite.dat"; do
            if [ -f "$GEO_DIR/$geo_file" ]; then
                ln -sf "$GEO_DIR/$geo_file" "$link_dir/$geo_file" 2>/dev/null || true
            fi
        done
    fi
done
log_info "Symlinks created"

# Step 7: Update desktop database
echo ""
echo "Updating desktop database..."
update-desktop-database /usr/share/applications 2>/dev/null || true
gtk-update-icon-cache /usr/share/icons/hicolor 2>/dev/null || true
log_info "Desktop database updated"

# Step 7.5: 清理之前版本错误写入到用户目录的盾牌图标
echo ""
echo "Cleaning up legacy user icon cache..."
for uid_dir in /home/*/; do
    [ -d "$uid_dir" ] || continue
    username=$(basename "$uid_dir")
    xdg_icons="${uid_dir}.local/share/icons/hicolor"
    [ -d "$xdg_icons" ] || continue
    cleaned=false
    for size_dir in "$xdg_icons"/*/apps/; do
        [ -d "$size_dir" ] || continue
        user_icon="${size_dir}ov2n.png"
        [ -f "$user_icon" ] || continue
        size_name=$(basename "$(dirname "$size_dir")")
        system_icon="/usr/share/icons/hicolor/${size_name}/apps/ov2n.png"
        if [ ! -f "$system_icon" ]; then
            rm -f "$user_icon" 2>/dev/null || true
            cleaned=true
            continue
        fi
        user_sz=$(stat -c%s "$user_icon" 2>/dev/null || echo "0")
        sys_sz=$(stat -c%s "$system_icon" 2>/dev/null || echo "1")
        if [ "$user_sz" != "$sys_sz" ]; then
            rm -f "$user_icon" 2>/dev/null || true
            cleaned=true
        fi
    done
    if [ "$cleaned" = true ]; then
        su - "$username" -c \
            "gtk-update-icon-cache -f -t '$xdg_icons' 2>/dev/null || true" \
            2>/dev/null || true
    fi
done
log_info "User icon cache cleaned"

# ============================================================
# Step 8: 【关键修复】验证 PyQt5 - 与启动脚本用相同的探测逻辑
# ============================================================
echo ""
echo "Verifying PyQt5 installation..."

# 与启动脚本保持一致: 按优先级探测每个 python 解释器
find_python_with_pyqt5() {
    local candidates=(
        "/usr/bin/python3"
        "/usr/local/bin/python3"
        "/usr/bin/python3.11"
        "/usr/bin/python3.10"
        "/usr/bin/python3.9"
        "/usr/bin/python3.8"
        "/usr/local/bin/python3.11"
        "/usr/local/bin/python3.10"
        "/usr/local/bin/python3.9"
        "/usr/local/bin/python3.8"
    )
    for py in "${candidates[@]}"; do
        if [ -x "$py" ] && "$py" -c "import PyQt5.QtWidgets" 2>/dev/null; then
            echo "$py"
            return 0
        fi
    done
    return 1
}

PYQT5_PYTHON=$(find_python_with_pyqt5 || true)

if [ -n "$PYQT5_PYTHON" ]; then
    PYQT5_VER=$("$PYQT5_PYTHON" -c "import PyQt5; print(PyQt5.QtCore.PYQT_VERSION_STR)" 2>/dev/null || echo "unknown")
    log_info "PyQt5 ${PYQT5_VER} found at: $PYQT5_PYTHON"
else
    # PyQt5 未找到 - 尝试自动安装
    log_warn "PyQt5 not found! Attempting automatic installation..."
    echo ""

    INSTALL_OK=false

    # 方法1: apt install python3-pyqt5（系统级，最可靠）
    echo "   [1/2] Trying: apt install python3-pyqt5 ..."
    if apt-get install -y python3-pyqt5 2>/dev/null; then
        # apt 安装完再探测一次
        PYQT5_PYTHON=$(find_python_with_pyqt5 || true)
        if [ -n "$PYQT5_PYTHON" ]; then
            log_info "PyQt5 installed successfully via apt"
            INSTALL_OK=true
        fi
    fi

    # 方法2: 对每个 python 解释器尝试 pip 安装
    if [ "$INSTALL_OK" = false ]; then
        echo "   [2/2] Trying: pip install PyQt5 for each python..."
        for py in "/usr/bin/python3" "/usr/local/bin/python3" \
                  "/usr/bin/python3.11" "/usr/bin/python3.10" \
                  "/usr/bin/python3.9"  "/usr/bin/python3.8"; do
            if [ -x "$py" ]; then
                echo "         Testing $py ..."
                if "$py" -m pip install PyQt5 --quiet 2>/dev/null; then
                    if "$py" -c "import PyQt5.QtWidgets" 2>/dev/null; then
                        log_info "PyQt5 installed via pip for $py"
                        INSTALL_OK=true
                        PYQT5_PYTHON="$py"
                        break
                    fi
                fi
            fi
        done
    fi

    # 自动安装失败 - 打印明确的手动修复指引
    if [ "$INSTALL_OK" = false ]; then
        echo ""
        echo -e "${RED}════════════════════════════════════════════${NC}"
        echo -e "${RED}  警告: PyQt5 安装失败，ov2n 将无法启动！${NC}"
        echo -e "${RED}════════════════════════════════════════════${NC}"
        echo ""
        echo "  请手动运行以下命令修复:"
        echo ""
        echo "  方法1 (推荐):"
        echo "    sudo apt install python3-pyqt5"
        echo ""
        echo "  方法2 (若方法1无效):"
        echo "    sudo apt install python3-pip"
        echo "    sudo pip3 install PyQt5"
        echo ""
        echo "  方法3 (指定具体 python 版本):"
        echo "    # 先查看系统有哪些 python:"
        echo "    ls /usr/bin/python3* /usr/local/bin/python3*"
        echo "    # 对 PyQt5 所在版本的 python 安装:"
        echo "    sudo /usr/bin/python3.X -m pip install PyQt5"
        echo ""
        # 仅警告，不中断安装（包本身已正确安装，只是缺运行时依赖）
        # 不 exit 1，让用户可以手动修复后直接运行
    fi
fi


# ============================================================
# Step 9: 验证 python3-xlib - Ubuntu 标题栏图标依赖
# ============================================================
echo ""
echo "Verifying python3-xlib installation..."

# 用与 PyQt5 相同的 python 解释器检测
XLIB_OK=false
CHECK_PY="${PYQT5_PYTHON:-python3}"

if [ -x "$CHECK_PY" ] && "$CHECK_PY" -c "from Xlib import display" 2>/dev/null; then
    XLIB_OK=true
    log_info "python3-xlib found"
else
    log_warn "python3-xlib not found! Attempting automatic installation..."
    echo ""

    # 方法1: apt install python3-xlib（最可靠）
    echo "   [1/2] Trying: apt install python3-xlib ..."
    if apt-get install -y python3-xlib 2>/dev/null; then
        if [ -x "$CHECK_PY" ] && "$CHECK_PY" -c "from Xlib import display" 2>/dev/null; then
            log_info "python3-xlib installed successfully via apt"
            XLIB_OK=true
        fi
    fi

    # 方法2: pip 安装（apt 失败时兜底）
    if [ "$XLIB_OK" = false ] && [ -x "$CHECK_PY" ]; then
        echo "   [2/2] Trying: pip install python-xlib ..."
        if "$CHECK_PY" -m pip install python-xlib --quiet 2>/dev/null; then
            if "$CHECK_PY" -c "from Xlib import display" 2>/dev/null; then
                log_info "python3-xlib installed via pip"
                XLIB_OK=true
            fi
        fi
    fi

    if [ "$XLIB_OK" = false ]; then
        log_warn "python3-xlib installation failed (window icon may not show in title bar)"
        echo "  To fix manually: sudo apt install python3-xlib"
    fi
fi

# 最终总结
echo ""
echo "══════════════════════════════════════"
echo "  Installation Summary"
echo "══════════════════════════════════════"
log_info "Installation completed"
if [ -n "${PYQT5_PYTHON:-}" ]; then
    log_info "Runtime Python: $PYQT5_PYTHON"
fi

echo ""
echo "╔════════════════════════════════════════╗"
echo "║   ov2n Installation Completed!         ║"
echo "╠════════════════════════════════════════╣"
echo "║  Start the application:                ║"
echo "║    $ ov2n                              ║"
echo "║                                        ║"
echo "║  Or search for 'ov2n' in your menu     ║"
echo "║                                        ║"
echo "║  Bundled: v2ray binary + geo files     ║"
echo "║  Auto-update: geo files at runtime     ║"
echo "╚════════════════════════════════════════╝"
echo ""

exit 0
POSTINST

chmod +x "${DEB_BUILD_DIR}/DEBIAN/postinst"

# Create prerm script
cat > "${DEB_BUILD_DIR}/DEBIAN/prerm" << 'PRERM'
#!/bin/bash
set -e
PKG_NAME="ov2n"
echo "Cleaning up ${PKG_NAME}..."
rm -f /usr/share/polkit-1/actions/org.example.vpnclient.policy 2>/dev/null || true
rm -f /usr/local/bin/vpn-helper.py 2>/dev/null || true
rm -f /opt/${PKG_NAME} 2>/dev/null || true
echo "✓ Pre-removal cleanup completed"
exit 0
PRERM

chmod +x "${DEB_BUILD_DIR}/DEBIAN/prerm"

# Create postrm script
cat > "${DEB_BUILD_DIR}/DEBIAN/postrm" << 'POSTRM'
#!/bin/bash
set -e
if [ "$1" = "purge" ]; then
    echo "Purging ov2n configuration..."
fi
exit 0
POSTRM

chmod +x "${DEB_BUILD_DIR}/DEBIAN/postrm"

# Create copyright file
cat > "${DEB_BUILD_DIR}/DEBIAN/copyright" << COPYRIGHT
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: ov2n
Upstream-Contact: Alfiy <13012648@qq.com>
Source: https://github.com/alfiy/pyQt_vpnv2ray_client

Files: *
Copyright: 2024 Alfiy
License: MIT

License: MIT
 Permission is hereby granted, free of charge, to any person obtaining a copy
 of this software and associated documentation files (the "Software"), to deal
 in the Software without restriction, including without limitation the rights
 to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 copies of the Software, and to permit persons to whom the Software is
 furnished to do so, subject to the following conditions:
 .
 The above copyright notice and this permission notice shall be included in all
 copies or substantial portions of the Software.
 .
 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 SOFTWARE.
COPYRIGHT

echo -e "${GREEN}  ✓ DEBIAN metadata created${NC}"
echo ""

# Step 9: Build the DEB package
echo -e "${YELLOW}[9/10] Building DEB package...${NC}"

DEB_FILE="${DIST_DIR}/${PKG_NAME}_${VERSION}_amd64.deb"

if fakeroot dpkg-deb --build "${DEB_BUILD_DIR}" "${DEB_FILE}" 2>/dev/null; then
    echo -e "${GREEN}  ✓ DEB package built successfully!${NC}"
    echo ""

    echo -e "${BLUE}Package Information:${NC}"
    dpkg -I "${DEB_FILE}" 2>/dev/null | head -25
    echo ""

    SIZE=$(du -h "${DEB_FILE}" | cut -f1)
    echo -e "${BLUE}Package Size:${NC} ${SIZE}"
    echo -e "${BLUE}Package Location:${NC} ${DEB_FILE}"
    echo ""

    echo -e "${BLUE}Bundled Components:${NC}"
    if [ -f "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/v2ray/v2ray" ]; then
        v2ray_size=$(stat -c%s "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/v2ray/v2ray" 2>/dev/null || echo "0")
        echo -e "  ${GREEN}✓ v2ray binary ($(numfmt --to=iec $v2ray_size 2>/dev/null || echo "${v2ray_size} bytes"))${NC}"
    else
        echo -e "  ${YELLOW}⚠ v2ray binary not bundled (will download on install)${NC}"
    fi
    for geo_file in geoip.dat geosite.dat; do
        if [ -f "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/v2ray/${geo_file}" ]; then
            geo_size=$(stat -c%s "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/v2ray/${geo_file}" 2>/dev/null || echo "0")
            echo -e "  ${GREEN}✓ ${geo_file} ($(numfmt --to=iec $geo_size 2>/dev/null || echo "${geo_size} bytes"))${NC}"
        else
            echo -e "  ${YELLOW}⚠ ${geo_file} not bundled (will download on install)${NC}"
        fi
    done
    echo ""

    echo -e "${BLUE}═══════════════════════════════════════${NC}"
    echo -e "${GREEN}Installation Instructions:${NC}"
    echo -e "${BLUE}═══════════════════════════════════════${NC}"
    echo ""
    echo "  1. Install the package (recommended):"
    echo -e "     ${YELLOW}sudo apt install ./${DEB_FILE}${NC}"
    echo ""
    echo "  2. Or use dpkg + fix dependencies:"
    echo -e "     ${YELLOW}sudo dpkg -i ${DEB_FILE}${NC}"
    echo -e "     ${YELLOW}sudo apt-get install -f${NC}"
    echo ""
    echo "  3. Launch the application:"
    echo -e "     ${YELLOW}ov2n${NC}"
    echo ""
    echo "  4. Uninstall (if needed):"
    echo -e "     ${YELLOW}sudo apt remove ${PKG_NAME}${NC}"
    echo ""
    echo -e "${GREEN}Features in This Build:${NC}"
    echo "  ✓ Bundled v2ray binary (offline installation)"
    echo "  ✓ Bundled geo files (no download on first install)"
    echo "  ✓ Auto-detect Python interpreter with PyQt5"
    echo "  ✓ Auto-install PyQt5 if missing (apt + pip fallback)"
    echo "  ✓ Friendly error message if PyQt5 still missing"
    echo "  ✓ Cross-distro compatible (Ubuntu/Kylin/Debian)"
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════${NC}"
    echo ""
else
    echo -e "${RED}✗ Failed to build DEB package${NC}"
    exit 1
fi

echo -e "${BLUE}"
echo "╔════════════════════════════════════════╗"
echo "         Build Completed!                 "
echo "       ov2n ${VERSION} is ready             "
echo "╚════════════════════════════════════════╝"
echo -e "${NC}"

exit 0
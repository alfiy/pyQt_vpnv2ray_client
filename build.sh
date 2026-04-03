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
# Auto version: version.txt > git tag > fallback
########################################
if [ -z "$VERSION" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [ -f "${SCRIPT_DIR}/version.txt" ]; then
        VERSION="$(tr -d '[:space:]' < "${SCRIPT_DIR}/version.txt")"
    fi
    if [ -z "$VERSION" ]; then
        if git describe --tags --abbrev=0 >/dev/null 2>&1; then
            VERSION=$(git describe --tags --abbrev=0)
        fi
    fi
    if [ -z "$VERSION" ]; then
        VERSION="1.4.2"
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

        # vpn_process.py 是 v2 架构的核心，必须存在
        if [ ! -f "vpn_process.py" ]; then
            echo -e "${RED}✗ vpn_process.py not found${NC}"
            echo -e "${RED}  vpn_process.py 是必需文件，请先从项目仓库获取${NC}"
            exit 1
        fi
        echo -e "${GREEN}  ✓ vpn_process.py found${NC}"
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
        # resources/nssm 不再打包（v2 不需要 NSSM）
        mkdir -p "${APP_DIR}/logs"
        mkdir -p "${DIST_DIR}"
        echo -e "${GREEN}  ✓ Directories prepared${NC}"
        echo -e "${YELLOW}    NOTE: resources/nssm 目录不再打包（v2 不使用 NSSM 服务）${NC}"
        echo ""

        echo -e "${YELLOW}[3/7] Copying application files...${NC}"
        cp main.py "${APP_DIR}/"
        cp requirements.txt "${APP_DIR}/"

        # ── 核心变更：打包 vpn_process.py，不再打包 .ps1 脚本 ──
        cp vpn_process.py "${APP_DIR}/"
        echo -e "${GREEN}  ✓ vpn_process.py copied (替代所有 .ps1 / .bat 脚本)${NC}"

        echo "${VERSION}" > "${APP_DIR}/version.txt"

        if [ -d "core" ]; then
            cp -r core "${APP_DIR}/"
            find "${APP_DIR}/core" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
            echo -e "${GREEN}  ✓ core/ copied${NC}"
        fi
        if [ -d "ui" ]; then
            cp -r ui "${APP_DIR}/"
            find "${APP_DIR}/ui" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
            echo -e "${GREEN}  ✓ ui/ copied${NC}"
        fi

        if [ -d "resources/images" ]; then
            cp resources/images/* "${APP_DIR}/resources/images/" 2>/dev/null || true
            echo -e "${GREEN}  ✓ resources/images/ copied${NC}"
        fi

        # Xray 资源
        echo ""
        echo -e "${YELLOW}  Checking Xray resources...${NC}"
        if [ -d "resources/xray" ]; then
            for f in resources/xray/*; do
                # ── 关键：跳过 .ps1 文件，不打包进安装包 ──
                case "$f" in
                    *.ps1|*.vbs)
                        echo -e "${YELLOW}    SKIP ${f} (脚本文件不打包，由 vpn_process.py 替代)${NC}"
                        continue
                        ;;
                esac
                [ -f "$f" ] && cp "$f" "${APP_DIR}/resources/xray/" 2>/dev/null || true
            done
        fi

        for geo_file in geoip.dat geosite.dat; do
            if [ ! -f "${APP_DIR}/resources/xray/${geo_file}" ]; then
                [ -f "resources/v2ray/${geo_file}" ] && cp "resources/v2ray/${geo_file}" "${APP_DIR}/resources/xray/"
            fi
            if [ -f "${APP_DIR}/resources/xray/${geo_file}" ]; then
                geo_size=$(stat -c%s "${APP_DIR}/resources/xray/${geo_file}" 2>/dev/null || echo "0")
                echo -e "${GREEN}    ✓ ${geo_file} copied ($(numfmt --to=iec $geo_size 2>/dev/null || echo "${geo_size} bytes"))${NC}"
            fi
        done

        if [ -f "${APP_DIR}/resources/xray/xray.exe" ]; then
            echo -e "${GREEN}    ✓ xray.exe bundled${NC}"
        else
            echo -e "${YELLOW}    ⚠ xray.exe not found${NC}"
        fi
        if [ -f "${APP_DIR}/resources/xray/wintun.dll" ]; then
            echo -e "${GREEN}    ✓ wintun.dll bundled${NC}"
        fi
        if [ -f "${APP_DIR}/resources/xray/config.json.windows.template" ]; then
            cp "${APP_DIR}/resources/xray/config.json.windows.template" "${APP_DIR}/resources/xray/config.json"
            echo -e "${GREEN}    ✓ Xray config template applied${NC}"
        fi

        # TAP-Windows
        echo ""
        echo -e "${YELLOW}  Checking TAP-Windows resources...${NC}"
        if [ -d "resources/tap-windows" ]; then
            cp -r resources/tap-windows/* "${APP_DIR}/resources/tap-windows/" 2>/dev/null || true
            local TAP_FOUND=false
            for tap_exe in "${APP_DIR}"/resources/tap-windows/*.exe; do
                if [ -f "$tap_exe" ]; then
                    TAP_FOUND=true
                    echo -e "${GREEN}    ✓ TAP-Windows installer: $(basename "$tap_exe")${NC}"
                fi
            done
            if [ "$TAP_FOUND" = false ]; then
                echo -e "${YELLOW}    ⚠ TAP-Windows installer not found in resources/tap-windows/${NC}"
            fi
        fi

        # OpenVPN（只复制 bin/config/log，不需要 NSSM）
        echo ""
        echo -e "${YELLOW}  Checking OpenVPN resources...${NC}"
        if [ -d "resources/openvpn" ]; then
            for subdir in bin config log; do
                mkdir -p "${APP_DIR}/resources/openvpn/${subdir}" 2>/dev/null || true
            done
            cp -r resources/openvpn/* "${APP_DIR}/resources/openvpn/" 2>/dev/null || true
            if [ -f "${APP_DIR}/resources/openvpn/bin/openvpn.exe" ]; then
                echo -e "${GREEN}    ✓ OpenVPN files bundled${NC}"
                local dll_count=$(ls "${APP_DIR}/resources/openvpn/bin/"*.dll 2>/dev/null | wc -l)
                [ "$dll_count" -gt 0 ] && echo -e "${GREEN}    ✓ ${dll_count} DLL files bundled${NC}"
            else
                echo -e "${YELLOW}    ⚠ openvpn.exe not found${NC}"
            fi
        fi

        for doc in README.md INSTALL.md LICENSE LICENSE.md; do
            [ -f "$doc" ] && cp "$doc" "${APP_DIR}/" 2>/dev/null || true
        done
        echo ""
        echo -e "${GREEN}  ✓ Application files copied${NC}"
        echo ""

        # ══════════════════════════════════════════════════════════
        # [4/7] 变更说明：
        #   旧版：cp scripts/windows/*.ps1 → 打包 start-xray.ps1 / stop-xray.ps1
        #         这些脚本会触发杀软（-ExecutionPolicy Bypass 特征）
        #
        #   新版：只复制 install.bat（仅安装用，安装后不会被调用）
        #         start-xray.ps1 / stop-xray.ps1 / register-openvpn-service.bat
        #         完全由 vpn_process.py 替代，不再打包
        # ══════════════════════════════════════════════════════════
        echo -e "${YELLOW}[4/7] Copying Windows scripts (install-only)...${NC}"

        # 只保留 scripts/windows/ 目录用于安装时使用的 install.bat
        # 运行时脚本（.ps1）全部由 vpn_process.py 替代，不打包
        if [ -d "scripts/windows" ]; then
            mkdir -p "${APP_DIR}/scripts/windows"
            # 只复制 install.bat 和 uninstall.bat，跳过所有 .ps1
            for bat_file in scripts/windows/install.bat scripts/windows/uninstall.bat; do
                if [ -f "$bat_file" ]; then
                    cp "$bat_file" "${APP_DIR}/scripts/windows/"
                    echo -e "${GREEN}  ✓ Copied: $(basename "$bat_file")${NC}"
                fi
            done
            echo -e "${YELLOW}  NOTE: start-xray.ps1 / stop-xray.ps1 / register-openvpn-service.bat${NC}"
            echo -e "${YELLOW}        不再打包 — 功能已由 vpn_process.py 完全替代${NC}"
        fi
        echo ""

        # 创建主启动脚本 ov2n.bat
        echo -e "${YELLOW}[5/7] Creating Windows launcher...${NC}"
        cat > "${APP_DIR}/ov2n.bat" << 'WINLAUNCHER'
@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ==========================================
REM ov2n - VPN Client Launcher for Windows
REM Requires: Python 3.8+ with PyQt5, psutil
REM ==========================================

title ov2n VPN Client

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
echo   IMPORTANT: Check "Add Python to PATH"
echo.
pause
exit /b 1

:python_ok
!PYTHON! -c "import PyQt5" >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [WARN] PyQt5 not found. Installing...
    !PYTHON! -m pip install PyQt5
)

!PYTHON! -c "import psutil" >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [WARN] psutil not found. Installing...
    !PYTHON! -m pip install psutil
)

cd /d "%~dp0"
set PYTHONPATH=%~dp0;%PYTHONPATH%
!PYTHON! main.py %*

if !ERRORLEVEL! NEQ 0 (
    echo.
    echo Application exited with error code: !ERRORLEVEL!
    pause
)
WINLAUNCHER
        echo -e "${GREEN}  ✓ ov2n.bat created${NC}"

        # 创建安装入口
        cat > "${APP_DIR}/install-ov2n.bat" << 'INSTALL_ENTRY'
@echo off
chcp 65001 >nul 2>&1
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Please run as Administrator.
    pause
    exit /b 1
)
cd /d "%~dp0"
call scripts\windows\install.bat
INSTALL_ENTRY
        echo -e "${GREEN}  ✓ install-ov2n.bat created${NC}"

        cat > "${APP_DIR}/uninstall-ov2n.bat" << 'UNINSTALL_ENTRY'
@echo off
chcp 65001 >nul 2>&1
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Please run as Administrator.
    pause
    exit /b 1
)
cd /d "%~dp0"
call scripts\windows\uninstall.bat
UNINSTALL_ENTRY
        echo -e "${GREEN}  ✓ uninstall-ov2n.bat created${NC}"
        echo ""

        # CRLF 转换（只处理 .bat，不再有 .ps1 需要转换）
        echo -e "${YELLOW}[6/10] Converting .bat scripts to CRLF...${NC}"
        local crlf_count=0
        while IFS= read -r -d '' batfile; do
            if command -v unix2dos &>/dev/null; then
                unix2dos -q "$batfile" 2>/dev/null
            else
                sed -i 's/\r$//' "$batfile"
                sed -i 's/$/\r/' "$batfile"
            fi
            crlf_count=$((crlf_count + 1))
        done < <(find "${APP_DIR}" -type f \( -name "*.bat" -o -name "*.cmd" \) -print0)
        echo -e "${GREEN}  ✓ Converted ${crlf_count} .bat file(s) to CRLF${NC}"
        echo ""

        # Package as ZIP
        echo -e "${YELLOW}[7/10] Creating ZIP package...${NC}"
        local ZIP_FILE="${DIST_DIR}/${PKG_NAME}_${VERSION}_windows.zip"
        if command -v zip &>/dev/null; then
            (cd "${WIN_BUILD_DIR}" && zip -r "../../${ZIP_FILE}" "${PKG_NAME}/")
        elif command -v 7z &>/dev/null; then
            (cd "${WIN_BUILD_DIR}" && 7z a "../../${ZIP_FILE}" "${PKG_NAME}/")
        else
            ZIP_FILE="${DIST_DIR}/${PKG_NAME}_${VERSION}_windows.tar.gz"
            (cd "${WIN_BUILD_DIR}" && tar czf "../../${ZIP_FILE}" "${PKG_NAME}/")
            echo -e "${YELLOW}  ⚠ zip/7z not found, created tar.gz instead${NC}"
        fi
        local SIZE=$(du -h "${ZIP_FILE}" | cut -f1)
        echo -e "${GREEN}  ✓ Package: ${ZIP_FILE} (${SIZE})${NC}"
        echo ""

        # ══════════════════════════════════════════════════════════
        # [8/10] 生成 Inno Setup 启动器文件（项目根目录）
        #
        # 旧版：生成 ov2n_launcher.vbs（base64 解码）
        #       VBScript + wscript.exe + Run sCmd, 0, False → 杀软必报
        #
        # 新版：生成 ov2n_launcher.py（os.execv 直接替换进程）
        #       对杀软完全透明，Task Manager 只见 pythonw.exe main.py
        # ══════════════════════════════════════════════════════════
        echo -e "${YELLOW}[8/10] Generating ov2n_launcher.py for Inno Setup...${NC}"

        # 优先使用 installer/src/ov2n_launcher.py（由 build_installer.bat 维护）
        if [ -f "installer/src/ov2n_launcher.py" ]; then
            cp "installer/src/ov2n_launcher.py" "ov2n_launcher.py"
            echo -e "${GREEN}  ✓ ov2n_launcher.py copied from installer/src/${NC}"
        else
            # 首次构建：用 Python 直接写入，不借助 PowerShell
            python3 - << 'PYEOF'
import pathlib
content = '''\
"""
ov2n VPN Client Launcher
========================
Shortcut target:
  pythonw.exe "C:\\path\\to\\ov2n_launcher.py"

How it works:
  - No wscript.exe / cscript.exe
  - Uses os.execv() to REPLACE this process with pythonw + main.py
  - No subprocess.Popen, no DETACHED_PROCESS, no hidden-window tricks
  - Fully transparent to antivirus: visible in Task Manager as pythonw.exe
"""
import os
import sys


def find_pythonw():
    d = os.path.dirname(sys.executable)
    pw = os.path.join(d, "pythonw.exe")
    if os.path.exists(pw):
        return pw
    import shutil
    found = shutil.which("pythonw")
    return found if found else sys.executable


def main():
    app_dir = os.path.dirname(os.path.abspath(__file__))
    main_py = os.path.join(app_dir, "main.py")
    if not os.path.exists(main_py):
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0, f"main.py not found:\\n{main_py}", "ov2n", 0x10
        )
        sys.exit(1)
    pythonw = find_pythonw()
    # os.execv replaces the current process image entirely.
    # No child process is spawned, no DETACHED_PROCESS flag needed.
    os.execv(pythonw, [pythonw, main_py])


if __name__ == "__main__":
    main()
'''
pathlib.Path("ov2n_launcher.py").write_text(content, encoding="utf-8")
print("  ✓ ov2n_launcher.py generated")
PYEOF
        fi

        # 确保不存在废弃的 ov2n_launcher.vbs
        if [ -f "ov2n_launcher.vbs" ]; then
            rm -f "ov2n_launcher.vbs"
            echo -e "${YELLOW}  Deleted deprecated ov2n_launcher.vbs${NC}"
        fi

        # 确保项目根有 ov2n.bat
        if [ ! -f "ov2n.bat" ]; then
            cp "${APP_DIR}/ov2n.bat" "ov2n.bat" 2>/dev/null || true
            [ -f "ov2n.bat" ] && echo -e "${GREEN}  ✓ ov2n.bat copied to project root${NC}"
        else
            echo -e "${GREEN}  ✓ ov2n.bat already in project root${NC}"
        fi
        echo ""

        # 尝试 Inno Setup 构建 setup.exe
        echo -e "${YELLOW}[9/10] Building Windows installer (setup.exe)...${NC}"
        local SETUP_BUILT=false

        if [ -f "installer/build_installer.bat" ]; then
            echo "${VERSION}" > "version.txt"
            mkdir -p "${DIST_DIR}"

            local WIN_PROJECT_ROOT
            WIN_PROJECT_ROOT=$(cygpath -w "$(pwd)" 2>/dev/null) || true
            if [ -z "$WIN_PROJECT_ROOT" ]; then
                local UNIX_PWD; UNIX_PWD="$(pwd)"
                if [[ "$UNIX_PWD" =~ ^/([a-zA-Z])/ ]]; then
                    local DRIVE="${BASH_REMATCH[1]}"
                    local REST="${UNIX_PWD:2}"
                    WIN_PROJECT_ROOT="${DRIVE^^}:${REST//\//\\}"
                else
                    WIN_PROJECT_ROOT="$UNIX_PWD"
                fi
            fi

            echo -e "${YELLOW}  Project root (Windows): ${WIN_PROJECT_ROOT}${NC}"
            local CMD_OUTPUT=""
            CMD_OUTPUT=$(cmd.exe /c "cd /d \"${WIN_PROJECT_ROOT}\" && installer\\build_installer.bat --nopause" 2>&1) || true
            local CMD_EXIT=$?
            [ -n "$CMD_OUTPUT" ] && echo "$CMD_OUTPUT" | tr -d '\r'

            local SETUP_FILE="${DIST_DIR}/${PKG_NAME}_${VERSION}_setup.exe"
            if [ -f "$SETUP_FILE" ]; then
                local SETUP_SIZE=$(du -h "${SETUP_FILE}" | cut -f1)
                echo -e "${GREEN}  ✓ Installer: ${SETUP_FILE} (${SETUP_SIZE})${NC}"
                SETUP_BUILT=true
            else
                local FOUND_SETUP=""
                FOUND_SETUP=$(find "${DIST_DIR}" -maxdepth 1 -name "*setup*.exe" -print -quit 2>/dev/null) || true
                if [ -n "$FOUND_SETUP" ]; then
                    echo -e "${GREEN}    Found: ${FOUND_SETUP}${NC}"
                    SETUP_BUILT=true
                fi
            fi
        fi

        if [ "$SETUP_BUILT" = false ]; then
            echo ""
            echo -e "${RED}╔══════════════════════════════════════════════════════════╗${NC}"
            echo -e "${RED}║  ⚠ 无法自动生成 setup.exe                              ║${NC}"
            echo -e "${RED}╚══════════════════════════════════════════════════════════╝${NC}"
            echo ""
            echo -e "${YELLOW}  请在 CMD 中手动运行：installer\\build_installer.bat${NC}"
            echo -e "${YELLOW}  当前已生成便携版: ${GREEN}${ZIP_FILE}${NC}"
        fi
        echo ""

        # 打包内容摘要
        echo -e "${BLUE}Bundled Components:${NC}"
        [ -f "${APP_DIR}/vpn_process.py" ]                         && echo -e "  ${GREEN}✓ vpn_process.py (OpenVPN + Xray 进程管理)${NC}"
        [ -f "${APP_DIR}/resources/xray/xray.exe" ]                && echo -e "  ${GREEN}✓ xray.exe${NC}"             || echo -e "  ${YELLOW}⚠ xray.exe (需自行放入)${NC}"
        [ -f "${APP_DIR}/resources/xray/wintun.dll" ]              && echo -e "  ${GREEN}✓ wintun.dll${NC}"           || echo -e "  ${YELLOW}⚠ wintun.dll (需自行放入)${NC}"
        [ -f "${APP_DIR}/resources/xray/geoip.dat" ]               && echo -e "  ${GREEN}✓ geoip.dat${NC}"            || echo -e "  ${YELLOW}⚠ geoip.dat${NC}"
        [ -f "${APP_DIR}/resources/xray/geosite.dat" ]             && echo -e "  ${GREEN}✓ geosite.dat${NC}"          || echo -e "  ${YELLOW}⚠ geosite.dat${NC}"
        [ -f "${APP_DIR}/resources/openvpn/bin/openvpn.exe" ]      && echo -e "  ${GREEN}✓ openvpn.exe${NC}"          || echo -e "  ${YELLOW}⚠ openvpn.exe (需自行放入)${NC}"
        echo -e "  ${GREEN}✓ install.bat (TAP 驱动安装)${NC}"
        echo -e "  ${YELLOW}✗ start-xray.ps1 / stop-xray.ps1 / register-openvpn-service.bat${NC}"
        echo -e "  ${YELLOW}    → 已由 vpn_process.py 完全替代，不再打包${NC}"
        echo ""

        echo -e "${BLUE}═══════════════════════════════════════${NC}"
        echo -e "${GREEN}Windows Build Output:${NC}"
        echo -e "${BLUE}═══════════════════════════════════════${NC}"
        echo ""
        if [ "$SETUP_BUILT" = true ]; then
            echo -e "  ${GREEN}✓ 安装包: dist/${PKG_NAME}_${VERSION}_setup.exe${NC} (推荐)"
            echo -e "  ${GREEN}✓ 便携版: ${ZIP_FILE}${NC}"
        else
            echo -e "  ${GREEN}✓ 便携版: ${ZIP_FILE}${NC}"
            echo -e "  ${YELLOW}⚠ 安装包: 未生成 (需要 Inno Setup)${NC}"
        fi
        echo ""
        echo "  使用方法:"
        echo "  1. 解压到任意目录 (如 C:\\ov2n)"
        echo "  2. 右键以管理员身份运行 install-ov2n.bat"
        echo "     - 自动安装 TAP-Windows 驱动"
        echo "     - 自动安装 Python 依赖（PyQt5、psutil）"
        echo "  3. 运行 ov2n.bat 启动 GUI"
        echo "  4. 在 GUI 中导入 .ovpn 和 config.json，点击连接"
        echo "     OpenVPN 和 Xray 由 vpn_process.py 直接管理，无需系统服务"
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
# Linux build path（保持原有逻辑不变）
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
    echo -e "${YELLOW}    mkdir -p resources/v2ray${NC}"
    echo -e "${YELLOW}    wget https://github.com/v2fly/v2ray-core/releases/latest/download/v2ray-linux-64.zip${NC}"
    echo ""
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

cp -v main.py "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/" || { echo -e "${RED}✗ Failed to copy main.py${NC}"; exit 1; }
cp -v requirements.txt "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/" || { echo -e "${RED}✗ Failed to copy requirements.txt${NC}"; exit 1; }

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

# Step 6: Create launcher script
echo -e "${YELLOW}[6/10] Creating launcher script...${NC}"

cat > "${DEB_BUILD_DIR}/usr/local/bin/${PKG_NAME}" << 'LAUNCHER'
#!/bin/bash
# ov2n launcher - 自动探测正确的 Python 解释器
APP_DIR="/usr/local/lib/ov2n"

find_python() {
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
    while IFS= read -r py; do
        if [ -x "$py" ] && "$py" -c "import PyQt5.QtWidgets" 2>/dev/null; then
            echo "$py"
            return 0
        fi
    done < <(find /usr -name "python3*" -type f 2>/dev/null | sort -V)
    return 1
}

if [[ "${1:-}" == "--version" || "${1:-}" == "-v" ]]; then
    VERSION_FILE="${APP_DIR}/version.txt"
    if [ -f "$VERSION_FILE" ]; then
        echo "ov2n version $(cat "$VERSION_FILE")"
    else
        echo "ov2n version unknown"
    fi
    exit 0
fi

PYTHON=$(find_python)

if [ -z "$PYTHON" ]; then
    echo "错误: 未找到安装了 PyQt5 的 Python 解释器" >&2
    echo "请运行: sudo apt install python3-pyqt5" >&2
    if command -v zenity >/dev/null 2>&1; then
        zenity --error --title="ov2n 启动失败" \
            --text="缺少依赖: PyQt5\n\n请运行: sudo apt install python3-pyqt5" 2>/dev/null || true
    fi
    exit 1
fi

cd "$APP_DIR"
export QT_API=pyqt5
export PYTHONPATH="$APP_DIR:${PYTHONPATH:-}"
exec "$PYTHON" "$APP_DIR/main.py" "$@"
LAUNCHER

chmod +x "${DEB_BUILD_DIR}/usr/local/bin/${PKG_NAME}"
echo -e "${GREEN}  ✓ Launcher script created${NC}"
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

# Step 8: Create DEBIAN metadata（与原版完全一致，略）
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

# postinst / prerm / postrm 与原版完全一致，此处省略以保持文件简洁
# 请将原 build.sh 中的 DEBIAN/postinst、prerm、postrm 内容原样保留

echo -e "${GREEN}  ✓ DEBIAN metadata created${NC}"
echo ""

# Step 9: Build the DEB package
echo -e "${YELLOW}[9/10] Building DEB package...${NC}"

DEB_FILE="${DIST_DIR}/${PKG_NAME}_${VERSION}_amd64.deb"

if fakeroot dpkg-deb --build "${DEB_BUILD_DIR}" "${DEB_FILE}" 2>/dev/null; then
    echo -e "${GREEN}  ✓ DEB package built successfully!${NC}"
    SIZE=$(du -h "${DEB_FILE}" | cut -f1)
    echo -e "${BLUE}Package Size:${NC} ${SIZE}"
    echo -e "${BLUE}Package Location:${NC} ${DEB_FILE}"
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
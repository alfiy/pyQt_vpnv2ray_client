#!/bin/bash
# Build script for creating DEB packages on Linux (增强版)
# Project: ov2n - OpenVPN + V2Ray Client
# 增强功能: 自动安装 V2Ray 和 geo 数据文件 (优先使用预打包文件)
# Usage: ./build.sh [version] [distro]

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
        *)
            break
            ;;
    esac
done

# Default values
VERSION="${VERSION:-}"
DISTRO="${2:-focal}"
PKG_NAME="ov2n"
APP_NAME="ov2n"
APP_TITLE="ov2n - VPN Client"
MAINTAINER="Alfiy <13012648@qq.com>"
BUILD_DIR="build"
DEB_BUILD_DIR="${BUILD_DIR}/deb"
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
echo "╔════════════════════════════════════════╗"
echo "║  ov2n - VPN Client Builder (Enhanced)  ║"
echo "║  OpenVPN + V2Ray/Xray Integration      ║"
echo "║  + Bundled Geo Files Support           ║"
echo "╚════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo -e "${BLUE}Version:${NC} $VERSION"
echo -e "${BLUE}Distribution:${NC} $DISTRO"
echo ""

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
check_command "dpkg"
check_command "fakeroot"

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

# Step 3: Check bundled geo files
echo -e "${YELLOW}[3/9] Checking bundled geo files...${NC}"

BUNDLED_GEO_OK=true

if [ -f "resources/geoip.dat" ]; then
    GEOIP_SIZE=$(stat -c%s "resources/geoip.dat" 2>/dev/null || stat -f%z "resources/geoip.dat" 2>/dev/null || echo "0")
    if [ "$GEOIP_SIZE" -gt 102400 ]; then
        echo -e "${GREEN}  ✓ resources/geoip.dat found ($(numfmt --to=iec $GEOIP_SIZE 2>/dev/null || echo "${GEOIP_SIZE} bytes"))${NC}"
    else
        echo -e "${YELLOW}  ⚠ resources/geoip.dat is too small (${GEOIP_SIZE} bytes), may be invalid${NC}"
        BUNDLED_GEO_OK=false
    fi
else
    echo -e "${YELLOW}  ⚠ resources/geoip.dat not found${NC}"
    BUNDLED_GEO_OK=false
fi

if [ -f "resources/geosite.dat" ]; then
    GEOSITE_SIZE=$(stat -c%s "resources/geosite.dat" 2>/dev/null || stat -f%z "resources/geosite.dat" 2>/dev/null || echo "0")
    if [ "$GEOSITE_SIZE" -gt 102400 ]; then
        echo -e "${GREEN}  ✓ resources/geosite.dat found ($(numfmt --to=iec $GEOSITE_SIZE 2>/dev/null || echo "${GEOSITE_SIZE} bytes"))${NC}"
    else
        echo -e "${YELLOW}  ⚠ resources/geosite.dat is too small (${GEOSITE_SIZE} bytes), may be invalid${NC}"
        BUNDLED_GEO_OK=false
    fi
else
    echo -e "${YELLOW}  ⚠ resources/geosite.dat not found${NC}"
    BUNDLED_GEO_OK=false
fi

if [ "$BUNDLED_GEO_OK" = false ]; then
    echo ""
    echo -e "${YELLOW}  提示: 预打包的 geo 文件缺失或无效${NC}"
    echo -e "${YELLOW}  运行以下命令下载:${NC}"
    echo -e "${YELLOW}    ./resources/download_geo.sh${NC}"
    echo ""
    echo -e "${YELLOW}  继续构建 (安装时将从网络下载 geo 文件)...${NC}"
fi

echo ""

# Step 4: Prepare directories
echo -e "${YELLOW}[4/9] Preparing build directories...${NC}"
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
echo -e "${YELLOW}[5/9] Copying application files...${NC}"

cp -v main.py "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/" || {
    echo -e "${RED}✗ Failed to copy main.py${NC}"
    exit 1
}

cp -v requirements.txt "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/" || {
    echo -e "${RED}✗ Failed to copy requirements.txt${NC}"
    exit 1
}

# 复制可选的目录
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

# 【新增】复制预打包的 geo 文件到 resources 目录
if [ -d "resources" ]; then
    # 复制所有 resources 内容 (包括 geo 文件、校验和、README 等)
    cp -rv resources/* "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/" 2>/dev/null || true
    echo -e "${GREEN}  ✓ resources directory copied${NC}"

    # 统计复制的 geo 文件
    for geo_file in geoip.dat geosite.dat; do
        if [ -f "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/${geo_file}" ]; then
            geo_size=$(stat -c%s "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/${geo_file}" 2>/dev/null || echo "0")
            echo -e "${GREEN}    ✓ ${geo_file} bundled ($(numfmt --to=iec $geo_size 2>/dev/null || echo "${geo_size} bytes"))${NC}"
        fi
    done
fi

# Copy documentation
for doc in README.md INSTALL.md LICENSE LICENSE.md COPYING; do
    if [ -f "$doc" ]; then
        cp -v "$doc" "${DEB_BUILD_DIR}/usr/share/doc/${PKG_NAME}/" || true
        echo -e "${GREEN}  ✓ $doc copied${NC}"
    fi
done

echo -e "${GREEN}  ✓ Application files copied${NC}"
echo ""

# Copy application icons
echo -e "${YELLOW}  Installing application icons...${NC}"

cp resources/images/ov2n48.png  \
   "${DEB_BUILD_DIR}/usr/share/icons/hicolor/48x48/apps/ov2n.png" 2>/dev/null || true

cp resources/images/ov2n64.png  \
   "${DEB_BUILD_DIR}/usr/share/icons/hicolor/64x64/apps/ov2n.png" 2>/dev/null || true

cp resources/images/ov2n128.png \
   "${DEB_BUILD_DIR}/usr/share/icons/hicolor/128x128/apps/ov2n.png" 2>/dev/null || true

cp resources/images/ov2n256.png \
   "${DEB_BUILD_DIR}/usr/share/icons/hicolor/256x256/apps/ov2n.png" 2>/dev/null || true

chmod 644 "${DEB_BUILD_DIR}/usr/share/icons/hicolor/"*/apps/ov2n.png 2>/dev/null || true

echo -e "${GREEN}  ✓ Icons installed${NC}"

# Step 6: Create launcher script
echo -e "${YELLOW}[6/9] Creating launcher script...${NC}"

cat > "${DEB_BUILD_DIR}/usr/local/bin/${PKG_NAME}" << 'LAUNCHER'
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ov2n - OpenVPN + V2Ray/Xray Integrated Client
A PyQt5-based GUI application for managing VPN connections
"""

import sys
import os

# Set application directory
APP_DIR = "/usr/local/lib/ov2n"
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

# Set environment variables
os.environ['QT_API'] = 'pyqt5'

try:
    from main import main
    if __name__ == "__main__":
        main()
except ImportError as e:
    print(f"Error: Failed to import main module: {e}", file=sys.stderr)
    print("Please ensure ov2n is properly installed.", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
LAUNCHER

chmod +x "${DEB_BUILD_DIR}/usr/local/bin/${PKG_NAME}"
echo -e "${GREEN}  ✓ Launcher script created at /usr/local/bin/${PKG_NAME}${NC}"
echo ""

# Step 7: Create desktop entry
echo -e "${YELLOW}[7/9] Creating desktop entry...${NC}"

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
Keywords=vpn;openvpn;v2ray;xray;proxy;network;security;

[Desktop Action Help]
Name=Help
Exec=xdg-open https://github.com/alfiy/pyQt_vpnv2ray_client
DESKTOP

echo -e "${GREEN}  ✓ Desktop entry created${NC}"
echo ""

# Step 8: Create DEBIAN control file and scripts
echo -e "${YELLOW}[8/9] Creating DEBIAN metadata...${NC}"

cat > "${DEB_BUILD_DIR}/DEBIAN/control" << CONTROL
Package: ${PKG_NAME}
Version: ${VERSION}
Architecture: all
Maintainer: ${MAINTAINER}
Homepage: https://github.com/alfiy/pyQt_vpnv2ray_client
Depends: python3 (>= 3.8), python3-pyqt5, openvpn, policykit-1, iptables, wget | curl
Recommends: xray | v2ray, network-manager
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
  - Support for V2Ray/Xray proxy protocol
  - Transparent proxy via iptables TProxy
  - Integrated connection management
  - PolicyKit integration for privilege escalation
  - Bundled geo data files (no download needed on first install)
  - Auto-check geo file updates at runtime
  - Cross-platform compatibility
CONTROL

# Create postinst script - 增强版 (优先使用预打包 geo 文件)
cat > "${DEB_BUILD_DIR}/DEBIAN/postinst" << 'POSTINST'
#!/bin/bash
set -e

PKG_NAME="ov2n"
PKG_PATH="/usr/local/lib/${PKG_NAME}"
BIN_PATH="/usr/local/bin/${PKG_NAME}"
RESOURCES_PATH="${PKG_PATH}/resources"
GEO_DIR="/usr/local/share/v2ray"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}✓${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

echo ""
echo "══════════════════════════════════════"
echo "  ov2n Installation & Configuration"
echo "══════════════════════════════════════"
echo ""

# Step 1: Verify launcher exists
if [ ! -f "${BIN_PATH}" ]; then
    log_error "Launcher script not found at ${BIN_PATH}"
    exit 1
fi
log_info "Launcher script verified"

# Step 2: Make launcher executable
chmod +x "${BIN_PATH}" 2>/dev/null || {
    log_error "Failed to make launcher executable"
    exit 1
}
log_info "Launcher script is executable"

# Step 3: Verify package path exists
if [ ! -d "${PKG_PATH}" ]; then
    log_error "Package directory not found at ${PKG_PATH}"
    exit 1
fi
log_info "Package directory verified"

# Step 4: Create convenient symlink
if [ ! -d "/opt" ]; then
    mkdir -p /opt
fi
ln -sf ${PKG_PATH} /opt/${PKG_NAME} 2>/dev/null || true
log_info "Symlink created at /opt/${PKG_NAME}"

# Step 5: Install polkit files if present
if [ -d "${PKG_PATH}/polkit" ]; then
    echo ""
    echo "Configuring PolicyKit integration..."

    if ls ${PKG_PATH}/polkit/*.policy 1> /dev/null 2>&1; then
        cp ${PKG_PATH}/polkit/*.policy /usr/share/polkit-1/actions/ 2>/dev/null || true
        log_info "PolicyKit policies installed"
    fi

    for script in ${PKG_PATH}/polkit/*.py; do
        if [ -f "$script" ]; then
            cp "$script" /usr/local/bin/ 2>/dev/null || true
            chmod +x /usr/local/bin/$(basename $script) 2>/dev/null || true
        fi
    done
    log_info "Helper scripts installed"
fi

# Step 6: 检查并安装 V2Ray (如果需要)
echo ""
echo "Checking V2Ray/Xray installation..."

if command -v v2ray >/dev/null 2>&1 || command -v xray >/dev/null 2>&1; then
    log_info "V2Ray/Xray is already installed"

    if command -v v2ray >/dev/null 2>&1; then
        V2RAY_VERSION=$(v2ray version 2>/dev/null | head -1 || echo "unknown")
        echo "   Version: $V2RAY_VERSION"
    elif command -v xray >/dev/null 2>&1; then
        XRAY_VERSION=$(xray version 2>/dev/null | head -1 || echo "unknown")
        echo "   Version: $XRAY_VERSION"
    fi
else
    log_warn "V2Ray/Xray not found. Attempting auto-installation..."

    if command -v curl >/dev/null 2>&1; then
        echo "   Downloading V2Ray installer..."
        if curl -L https://raw.githubusercontent.com/v2fly/fhs-install-v2ray/master/install-release.sh -o /tmp/install-v2ray.sh 2>/dev/null; then
            echo "   Running V2Ray installer..."
            if bash /tmp/install-v2ray.sh >/tmp/v2ray-install.log 2>&1; then
                log_info "V2Ray installed successfully"
                rm -f /tmp/install-v2ray.sh /tmp/v2ray-install.log
            else
                log_warn "V2Ray auto-installation failed"
                echo "   Please install manually: bash <(curl -L https://raw.githubusercontent.com/v2fly/fhs-install-v2ray/master/install-release.sh)"
            fi
        else
            log_warn "Failed to download V2Ray installer"
        fi
    else
        log_warn "curl not found, cannot auto-install V2Ray"
        echo "   Please install V2Ray manually or install curl first"
    fi
fi

# Step 7: 【增强】安装 geo 数据文件 - 优先使用预打包文件
echo ""
echo "Installing V2Ray geo data files..."

mkdir -p "$GEO_DIR" 2>/dev/null || true

GEO_FAILED=""

install_geo_file() {
    local filename=$1
    local filepath="$GEO_DIR/$filename"
    local bundled_path="$RESOURCES_PATH/$filename"

    # 优先级 1: 检查目标目录是否已有有效文件
    if [ -f "$filepath" ]; then
        local size=$(stat -c%s "$filepath" 2>/dev/null || stat -f%z "$filepath" 2>/dev/null || echo "0")
        if [ "$size" -gt 102400 ]; then
            log_info "$filename already exists ($(numfmt --to=iec $size 2>/dev/null || echo "${size} bytes"))"
            return 0
        else
            log_warn "$filename exists but is too small, replacing..."
            rm -f "$filepath"
        fi
    fi

    # 优先级 2: 使用预打包的文件
    if [ -f "$bundled_path" ]; then
        local bundled_size=$(stat -c%s "$bundled_path" 2>/dev/null || stat -f%z "$bundled_path" 2>/dev/null || echo "0")
        if [ "$bundled_size" -gt 102400 ]; then
            echo "   Using bundled $filename..."
            cp "$bundled_path" "$filepath"
            log_info "$filename installed from bundled resources ($(numfmt --to=iec $bundled_size 2>/dev/null || echo "${bundled_size} bytes"))"
            return 0
        else
            log_warn "Bundled $filename is too small (${bundled_size} bytes), skipping"
        fi
    else
        echo "   No bundled $filename found"
    fi

    # 优先级 3: 从网络下载
    echo "   Downloading $filename from network..."
    shift
    local urls=("$@")

    for url in "${urls[@]}"; do
        echo "   Trying: $url"

        if command -v wget >/dev/null 2>&1; then
            if wget --timeout=30 --tries=2 -q -O "$filepath" "$url" 2>/dev/null; then
                local size=$(stat -c%s "$filepath" 2>/dev/null || stat -f%z "$filepath" 2>/dev/null || echo "0")
                if [ "$size" -gt 102400 ]; then
                    log_info "$filename downloaded successfully ($(numfmt --to=iec $size 2>/dev/null || echo "${size} bytes"))"
                    return 0
                else
                    rm -f "$filepath"
                fi
            fi
        elif command -v curl >/dev/null 2>&1; then
            if curl -L --max-time 30 --retry 2 -s -o "$filepath" "$url" 2>/dev/null; then
                local size=$(stat -c%s "$filepath" 2>/dev/null || stat -f%z "$filepath" 2>/dev/null || echo "0")
                if [ "$size" -gt 102400 ]; then
                    log_info "$filename downloaded successfully ($(numfmt --to=iec $size 2>/dev/null || echo "${size} bytes"))"
                    return 0
                else
                    rm -f "$filepath"
                fi
            fi
        fi
    done

    log_warn "Failed to install $filename from all sources"
    return 1
}

# 定义下载源
GEOIP_URLS=(
    "https://github.com/v2fly/geoip/releases/latest/download/geoip.dat"
    "https://cdn.jsdelivr.net/gh/v2fly/geoip@release/geoip.dat"
)

GEOSITE_URLS=(
    "https://github.com/v2fly/domain-list-community/releases/latest/download/dlc.dat"
    "https://cdn.jsdelivr.net/gh/v2fly/domain-list-community@release/dlc.dat"
)

# 安装 geoip.dat (优先使用预打包)
install_geo_file "geoip.dat" "${GEOIP_URLS[@]}" || GEO_FAILED=1

# 安装 geosite.dat (优先使用预打包)
install_geo_file "geosite.dat" "${GEOSITE_URLS[@]}" || GEO_FAILED=1

# 创建符号链接
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

# Step 8: Update desktop database
echo ""
echo "Updating desktop database..."
update-desktop-database /usr/share/applications 2>/dev/null || true
gtk-update-icon-cache /usr/share/icons/hicolor 2>/dev/null || true
log_info "Desktop database updated"

# Step 9: 验证 PyQt5 安装
echo ""
echo "Verifying PyQt5 installation..."
if python3 -c "import PyQt5.QtWidgets" 2>/dev/null; then
    log_info "PyQt5 is properly installed"
else
    log_warn "PyQt5 not found!"
    echo "   Please install: sudo apt install python3-pyqt5"
fi

# 最终总结
echo ""
echo "══════════════════════════════════════"
echo "  Installation Summary"
echo "══════════════════════════════════════"

if [ -z "$GEO_FAILED" ]; then
    log_info "All components installed successfully"
else
    log_warn "Some geo files failed to install"
    echo ""
    echo "You can manually download them later:"
    echo "  sudo wget -O /usr/local/share/v2ray/geoip.dat https://github.com/v2fly/geoip/releases/latest/download/geoip.dat"
    echo "  sudo wget -O /usr/local/share/v2ray/geosite.dat https://github.com/v2fly/domain-list-community/releases/latest/download/dlc.dat"
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
echo "║  Geo files: auto-update at runtime     ║"
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

# Remove polkit files
rm -f /usr/share/polkit-1/actions/org.example.vpnclient.policy 2>/dev/null || true
rm -f /usr/local/bin/vpn-helper.py 2>/dev/null || true

# Remove symlink
rm -f /opt/${PKG_NAME} 2>/dev/null || true

echo "✓ Pre-removal cleanup completed"
exit 0
PRERM

chmod +x "${DEB_BUILD_DIR}/DEBIAN/prerm"

# Create postrm script
cat > "${DEB_BUILD_DIR}/DEBIAN/postrm" << 'POSTRM'
#!/bin/bash
set -e

# 注意: 不删除 V2Ray 和 geo 文件,因为其他程序可能需要它们

if [ "$1" = "purge" ]; then
    echo "Purging ov2n configuration..."
    # 可以在这里删除用户配置文件
    # rm -rf /etc/ov2n 2>/dev/null || true
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
echo -e "${YELLOW}[9/9] Building DEB package...${NC}"

DEB_FILE="${DIST_DIR}/${PKG_NAME}_${VERSION}_all.deb"

if fakeroot dpkg-deb --build "${DEB_BUILD_DIR}" "${DEB_FILE}" 2>/dev/null; then
    echo -e "${GREEN}  ✓ DEB package built successfully!${NC}"
    echo ""

    # Display package information
    echo -e "${BLUE}Package Information:${NC}"
    dpkg -I "${DEB_FILE}" 2>/dev/null | head -25
    echo ""

    # Display file size
    SIZE=$(du -h "${DEB_FILE}" | cut -f1)
    echo -e "${BLUE}Package Size:${NC} ${SIZE}"
    echo -e "${BLUE}Package Location:${NC} ${DEB_FILE}"
    echo ""

    # Check if geo files are bundled
    echo -e "${BLUE}Bundled Geo Files:${NC}"
    for geo_file in geoip.dat geosite.dat; do
        if [ -f "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/${geo_file}" ]; then
            geo_size=$(stat -c%s "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/${geo_file}" 2>/dev/null || echo "0")
            echo -e "  ${GREEN}✓ ${geo_file} ($(numfmt --to=iec $geo_size 2>/dev/null || echo "${geo_size} bytes"))${NC}"
        else
            echo -e "  ${YELLOW}⚠ ${geo_file} not bundled (will download on install)${NC}"
        fi
    done
    echo ""

    # Installation instructions
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
    echo -e "${GREEN}New Features in This Build:${NC}"
    echo "  ✓ Bundled geo files (no download needed on first install)"
    echo "  ✓ Auto-check geo file updates at runtime"
    echo "  ✓ Fallback to network download if bundled files missing"
    echo "  ✓ Multiple download mirrors for reliability"
    echo "  ✓ Enhanced error handling and logging"
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
echo "       ov2n v${VERSION} is ready           "
echo "╚════════════════════════════════════════╝"
echo -e "${NC}"

exit 0
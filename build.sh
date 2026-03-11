#!/bin/bash
# Build script for creating DEB packages on Linux (增强版 - 支持打包 v2ray)
# Project: ov2n - OpenVPN + V2Ray Client
# 增强功能: 
# - 自动安装 V2Ray 和 geo 数据文件 (优先使用预打包文件)
# - 支持打包预下载的 v2ray 二进制文件
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
echo "╔═══════════════════════════════════════════╗"
echo "║  ov2n - VPN Client Builder (Enhanced)     ║"
echo "║  OpenVPN + V2Ray/Xray Integration         ║"
echo "║  + Bundled Geo Files & V2Ray Binary       ║"
echo "╚═══════════════════════════════════════════╝"
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

# Step 3: Check bundled v2ray and geo files
echo -e "${YELLOW}[3/10] Checking bundled v2ray and geo files...${NC}"

BUNDLED_V2RAY_OK=false
BUNDLED_GEO_OK=true

# 检查 v2ray 二进制
if [ -f "resources/v2ray/v2ray" ]; then
    V2RAY_SIZE=$(stat -c%s "resources/v2ray/v2ray" 2>/dev/null || stat -f%z "resources/v2ray/v2ray" 2>/dev/null || echo "0")
    if [ "$V2RAY_SIZE" -gt 1048576 ]; then  # > 1MB
        echo -e "${GREEN}  ✓ resources/v2ray/v2ray found ($(numfmt --to=iec $V2RAY_SIZE 2>/dev/null || echo "${V2RAY_SIZE} bytes"))${NC}"
        
        # 检查是否可执行
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

# 检查 geo 文件
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

# 【增强】复制 resources 目录
if [ -d "resources" ]; then
    # 复制 images 目录
    if [ -d "resources/images" ]; then
        mkdir -p "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/images"
        cp -rv resources/images/* "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/images/" 2>/dev/null || true
        echo -e "${GREEN}  ✓ resources/images directory copied${NC}"
    fi
    
    # 复制 v2ray 目录 (包含 v2ray 二进制、geoip.dat、geosite.dat)
    if [ -d "resources/v2ray" ]; then
        mkdir -p "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/v2ray"
        cp -rv resources/v2ray/* "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/v2ray/" 2>/dev/null || true
        echo -e "${GREEN}  ✓ resources/v2ray directory copied${NC}"
        
        # 统计复制的文件
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
echo -e "${YELLOW}[6/10] Creating launcher script...${NC}"

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
Keywords=vpn;openvpn;v2ray;xray;proxy;network;security;

[Desktop Action Help]
Name=Help
Exec=xdg-open https://github.com/alfiy/pyQt_vpnv2ray_client
DESKTOP

echo -e "${GREEN}  ✓ Desktop entry created${NC}"
echo ""

# Step 8: Create DEBIAN control file and scripts
echo -e "${YELLOW}[8/10] Creating DEBIAN metadata...${NC}"

cat > "${DEB_BUILD_DIR}/DEBIAN/control" << CONTROL
Package: ${PKG_NAME}
Version: ${VERSION}
Architecture: all
Maintainer: ${MAINTAINER}
Homepage: https://github.com/alfiy/pyQt_vpnv2ray_client
Depends: python3 (>= 3.8), python3-pyqt5, openvpn, policykit-1, iptables, wget | curl
Recommends: network-manager
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
  - Cross-platform compatibility
CONTROL

# Create postinst script - 增强版 (支持预打包 v2ray)
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

# Step 6: 【优化】安装 V2Ray - 直接复制预打包文件
echo ""
echo "Installing V2Ray..."

BUNDLED_V2RAY="${RESOURCES_PATH}/v2ray/v2ray"

# 检查系统是否已安装 v2ray 或 xray
if command -v v2ray >/dev/null 2>&1; then
    V2RAY_VERSION=$(v2ray version 2>/dev/null | head -1 || echo "unknown")
    log_info "V2Ray already installed: $V2RAY_VERSION"
elif command -v xray >/dev/null 2>&1; then
    XRAY_VERSION=$(xray version 2>/dev/null | head -1 || echo "unknown")
    log_info "Xray already installed: $XRAY_VERSION"
else
    # 系统未安装,使用预打包的 v2ray
    if [ -f "$BUNDLED_V2RAY" ]; then
        echo "   Copying bundled v2ray binary to /usr/local/bin/..."
        cp "$BUNDLED_V2RAY" /usr/local/bin/v2ray
        chmod +x /usr/local/bin/v2ray
        
        # 验证文件是否成功复制
        if [ -f /usr/local/bin/v2ray ] && [ -x /usr/local/bin/v2ray ]; then
            # 尝试获取版本
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
fi

# Step 7: 【优化】安装 geo 数据文件 - 直接复制预打包文件
echo ""
echo "Installing V2Ray geo data files..."

mkdir -p "$GEO_DIR" 2>/dev/null || true

# 直接复制预打包的 geo 文件
for geo_file in geoip.dat geosite.dat; do
    bundled_path="$RESOURCES_PATH/v2ray/$geo_file"
    target_path="$GEO_DIR/$geo_file"
    
    # 检查目标文件是否已存在且有效
    if [ -f "$target_path" ]; then
        size=$(stat -c%s "$target_path" 2>/dev/null || stat -f%z "$target_path" 2>/dev/null || echo "0")
        if [ "$size" -gt 102400 ]; then
            log_info "$geo_file already exists ($(numfmt --to=iec $size 2>/dev/null || echo "${size} bytes"))"
            continue
        fi
    fi
    
    # 复制预打包的文件
    if [ -f "$bundled_path" ]; then
        bundled_size=$(stat -c%s "$bundled_path" 2>/dev/null || stat -f%z "$bundled_path" 2>/dev/null || echo "0")
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

log_info "Installation completed"

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
echo -e "${YELLOW}[9/10] Building DEB package...${NC}"

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

    # Check bundled files
    echo -e "${BLUE}Bundled Components:${NC}"
    
    # V2Ray binary
    if [ -f "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/v2ray/v2ray" ]; then
        v2ray_size=$(stat -c%s "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/v2ray/v2ray" 2>/dev/null || echo "0")
        echo -e "  ${GREEN}✓ v2ray binary ($(numfmt --to=iec $v2ray_size 2>/dev/null || echo "${v2ray_size} bytes"))${NC}"
    else
        echo -e "  ${YELLOW}⚠ v2ray binary not bundled (will download on install)${NC}"
    fi
    
    # Geo files
    for geo_file in geoip.dat geosite.dat; do
        if [ -f "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/v2ray/${geo_file}" ]; then
            geo_size=$(stat -c%s "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/resources/v2ray/${geo_file}" 2>/dev/null || echo "0")
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
    echo -e "${GREEN}Features in This Build:${NC}"
    echo "  ✓ Bundled v2ray binary (offline installation)"
    echo "  ✓ Bundled geo files (no download on first install)"
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
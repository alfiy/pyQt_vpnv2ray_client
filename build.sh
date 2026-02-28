#!/bin/bash
# Build script for creating DEB packages on Linux
# Project: ov2n - OpenVPN + V2Ray Client
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
# Auto version from git tag (NEW)
########################################
if [ -z "$VERSION" ]; then
    if git describe --tags --abbrev=0 >/dev/null 2>&1; then
        VERSION=$(git describe --tags --abbrev=0)
    else
        VERSION="1.0.1"
    fi
fi

########################################
# Clean function (NEW)
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
# Command router (NEW)
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
echo "║       ov2n - VPN Client Builder        ║"
echo "║  OpenVPN + V2Ray/Xray Integration      ║"
echo "╚════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo -e "${BLUE}Version:${NC} $VERSION"
echo -e "${BLUE}Distribution:${NC} $DISTRO"
echo ""



# Step 1: Check dependencies
echo -e "${YELLOW}[1/8] Checking dependencies...${NC}"
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
echo -e "${YELLOW}[2/8] Checking source files...${NC}"
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

# Step 3: Clean and prepare directories
echo -e "${YELLOW}[3/8] Preparing build directories...${NC}"
rm -rf "${DEB_BUILD_DIR}"
mkdir -p "${DEB_BUILD_DIR}/DEBIAN"
mkdir -p "${DEB_BUILD_DIR}/usr/local/bin"
mkdir -p "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}"
mkdir -p "${DEB_BUILD_DIR}/usr/share/applications"
mkdir -p "${DEB_BUILD_DIR}/usr/share/pixmaps"
mkdir -p "${DEB_BUILD_DIR}/usr/share/doc/${PKG_NAME}"
mkdir -p "${DIST_DIR}"

echo -e "${GREEN}  ✓ Directories prepared${NC}"
echo ""

# Step 4: Copy application files
echo -e "${YELLOW}[4/8] Copying application files...${NC}"

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

# Copy documentation
for doc in README.md INSTALL.md LICENSE LICENSE.md COPYING; do
    if [ -f "$doc" ]; then
        cp -v "$doc" "${DEB_BUILD_DIR}/usr/share/doc/${PKG_NAME}/" || true
        echo -e "${GREEN}  ✓ $doc copied${NC}"
    fi
done

echo -e "${GREEN}  ✓ Application files copied${NC}"
echo ""

# Step 5: Create launcher script
echo -e "${YELLOW}[5/8] Creating launcher script...${NC}"

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

# Step 6: Create desktop entry
echo -e "${YELLOW}[6/8] Creating desktop entry...${NC}"

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

# Step 7: Create DEBIAN control file and scripts
echo -e "${YELLOW}[7/8] Creating DEBIAN metadata...${NC}"

cat > "${DEB_BUILD_DIR}/DEBIAN/control" << CONTROL
Package: ${PKG_NAME}
Version: ${VERSION}
Architecture: all
Maintainer: ${MAINTAINER}
Homepage: https://github.com/alfiy/pyQt_vpnv2ray_client
Depends: python3 (>= 3.8), python3-pyqt5, openvpn, policykit-1, iptables
Recommends: xray | v2ray, network-manager
Suggests: gnupg, curl, iptables-persistent
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
  - Cross-platform compatibility
CONTROL

# Create postinst script - 修复后的版本，不再安装 pip 版本的 PyQt5
cat > "${DEB_BUILD_DIR}/DEBIAN/postinst" << 'POSTINST'
#!/bin/bash
set -e

PKG_NAME="ov2n"
PKG_PATH="/usr/local/lib/${PKG_NAME}"
BIN_PATH="/usr/local/bin/${PKG_NAME}"

echo "Setting up ${PKG_NAME}..."
echo ""

# Step 1: Verify launcher exists
if [ ! -f "${BIN_PATH}" ]; then
    echo "ERROR: Launcher script not found at ${BIN_PATH}"
    exit 1
fi
echo "✓ Launcher script verified"

# Step 2: Make launcher executable
chmod +x "${BIN_PATH}" 2>/dev/null || {
    echo "ERROR: Failed to make launcher executable"
    exit 1
}
echo "✓ Launcher script is executable"

# Step 3: Verify package path exists
if [ ! -d "${PKG_PATH}" ]; then
    echo "ERROR: Package directory not found at ${PKG_PATH}"
    exit 1
fi
echo "✓ Package directory verified"

# Step 4: Create convenient symlink
if [ ! -d "/opt" ]; then
    mkdir -p /opt
fi
ln -sf ${PKG_PATH} /opt/${PKG_NAME} 2>/dev/null || true
echo "✓ Symlink created at /opt/${PKG_NAME}"

# Step 5: Install polkit files if present
if [ -d "${PKG_PATH}/polkit" ]; then
    echo "✓ Configuring PolicyKit integration..."
    
    if [ -f "${PKG_PATH}/polkit"/*.policy ]; then
        cp ${PKG_PATH}/polkit/*.policy /usr/share/polkit-1/actions/ 2>/dev/null || true
        echo "  ✓ PolicyKit policies installed"
    fi
    
    # Copy helper scripts
    for script in ${PKG_PATH}/polkit/*.py; do
        if [ -f "$script" ]; then
            cp "$script" /usr/local/bin/ 2>/dev/null || true
            chmod +x /usr/local/bin/$(basename $script) 2>/dev/null || true
        fi
    done
    echo "  ✓ Helper scripts installed"
fi

# Step 6: Update desktop database
echo "✓ Updating desktop database..."
update-desktop-database /usr/share/applications 2>/dev/null || true

# Step 7: 验证 PyQt5 安装 (不再通过 pip 安装)
echo "✓ Verifying PyQt5 installation..."
if python3 -c "import PyQt5.QtWidgets" 2>/dev/null; then
    echo "  ✓ PyQt5 is properly installed"
else
    echo "  ⚠ Warning: PyQt5 not found!"
    echo "    Please install: sudo apt install python3-pyqt5"
fi

echo ""
echo "╔════════════════════════════════════════╗"
echo "║   ov2n Installation Completed!         ║"
echo "╠════════════════════════════════════════╣"
echo "║  Start the application:                ║"
echo "║    $ ov2n                              ║"
echo "║                                        ║"
echo "║  Or search for 'ov2n' in your menu     ║"
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

# Create copyright file
cat > "${DEB_BUILD_DIR}/DEBIAN/copyright" << COPYRIGHT
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: ov2n
Upstream-Contact: Alfiy <your.email@example.com>
Source: https://github.com/alfiy/pyQt_vpnv2ray_client

Files: *
Copyright: 2024 Alfiy
License: MIT

Files: debian/*
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

# Step 8: Build the DEB package
echo -e "${YELLOW}[8/8] Building DEB package...${NC}"

DEB_FILE="${DIST_DIR}/${PKG_NAME}_${VERSION}_all.deb"

if fakeroot dpkg-deb --build "${DEB_BUILD_DIR}" "${DEB_FILE}" 2>/dev/null; then
    echo -e "${GREEN}  ✓ DEB package built successfully!${NC}"
    echo ""
    
    # Display package information
    echo -e "${BLUE}Package Information:${NC}"
    dpkg -I "${DEB_FILE}" 2>/dev/null | head -20
    echo ""
    
    # Display file size
    SIZE=$(du -h "${DEB_FILE}" | cut -f1)
    echo -e "${BLUE}Package Size:${NC} ${SIZE}"
    echo -e "${BLUE}Package Location:${NC} ${DEB_FILE}"
    echo ""
    
    # Installation instructions
    echo -e "${BLUE}═══════════════════════════════════════${NC}"
    echo -e "${GREEN}Installation Instructions:${NC}"
    echo -e "${BLUE}═══════════════════════════════════════${NC}"
    echo ""
    echo "  1. Install the package (recommended, auto-resolves dependencies):"
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
    echo -e "     ${YELLOW}sudo apt-get remove ${PKG_NAME}${NC}"
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════${NC}"
    echo ""
    
else
    echo -e "${RED}✗ Failed to build DEB package${NC}"
    exit 1
fi

echo -e "${BLUE}"
echo "╔════════════════════════════════════════╗"
echo "║         Build Completed!               ║"
echo "║       ov2n v${VERSION} is ready             ║"
echo "╚════════════════════════════════════════╝"
echo -e "${NC}"

exit 0
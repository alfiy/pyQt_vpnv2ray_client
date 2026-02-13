#!/bin/bash
# Build script for creating DEB packages on Linux
# Usage: ./build.sh [version] [distro]

set -e

# Color definitions for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
VERSION="${1:-1.0.0}"
DISTRO="${2:-focal}"  # focal, bionic, jammy, bullseye, bookworm, etc.
PKG_NAME="pyqt-vpnv2ray-client"
MAINTAINER="Your Name <your.email@example.com>"
BUILD_DIR="build"
DEB_BUILD_DIR="${BUILD_DIR}/deb"
DIST_DIR="dist"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}PyQt VPN V2Ray Client - DEB Builder${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Version: $VERSION"
echo "Distribution: $DISTRO"
echo ""

# Step 1: Check dependencies
echo -e "${YELLOW}Step 1/6: Checking dependencies...${NC}"
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo -e "${RED}✗ $1 is not installed${NC}"
        echo "Please install $1 and try again"
        exit 1
    fi
    echo -e "${GREEN}✓ $1 found${NC}"
}

check_command "python3"
check_command "dpkg"
check_command "fakeroot"

# Check for build-essential (optional but recommended)
if ! dpkg -l | grep -q build-essential; then
    echo -e "${YELLOW}⚠ build-essential not installed (optional)${NC}"
    echo "  Run: sudo apt-get install build-essential"
fi

echo ""

# Step 2: Clean and prepare directories
echo -e "${YELLOW}Step 2/6: Preparing build directories...${NC}"
rm -rf "${DEB_BUILD_DIR}"
mkdir -p "${DEB_BUILD_DIR}/DEBIAN"
mkdir -p "${DEB_BUILD_DIR}/usr/local/bin"
mkdir -p "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}"
mkdir -p "${DEB_BUILD_DIR}/usr/share/applications"
mkdir -p "${DEB_BUILD_DIR}/usr/share/icons/hicolor/256x256/apps"
mkdir -p "${DIST_DIR}"

echo -e "${GREEN}✓ Directories prepared${NC}"
echo ""

# Step 3: Copy application files
echo -e "${YELLOW}Step 3/6: Copying application files...${NC}"

# Copy main application files
cp main.py "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/"
cp requirements.txt "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/"
cp -r core "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/"
cp -r ui "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/"
cp -r polkit "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/"

# Copy documentation
if [ -f "README.md" ]; then
    cp README.md "${DEB_BUILD_DIR}/usr/local/lib/${PKG_NAME}/"
fi

echo -e "${GREEN}✓ Application files copied${NC}"
echo ""

# Step 4: Create launcher script
echo -e "${YELLOW}Step 4/6: Creating launcher script...${NC}"

cat > "${DEB_BUILD_DIR}/usr/local/bin/${PKG_NAME}" << 'EOF'
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os

# Add application directory to path
app_dir = "/usr/local/lib/pyqt-vpnv2ray-client"
sys.path.insert(0, app_dir)

# Change to application directory
os.chdir(app_dir)

# Import and run main application
from main import main

if __name__ == "__main__":
    main()
EOF

chmod +x "${DEB_BUILD_DIR}/usr/local/bin/${PKG_NAME}"

echo -e "${GREEN}✓ Launcher script created${NC}"
echo ""

# Step 5: Create desktop entry
echo -e "${YELLOW}Step 5/6: Creating desktop entry...${NC}"

cat > "${DEB_BUILD_DIR}/usr/share/applications/${PKG_NAME}.desktop" << EOF
[Desktop Entry]
Type=Application
Name=PyQt VPN V2Ray Client
Comment=VPN Client with V2Ray/Xray Support
Exec=${PKG_NAME}
Icon=${PKG_NAME}
Categories=Network;Utility;
Terminal=false
StartupNotify=true
EOF

echo -e "${GREEN}✓ Desktop entry created${NC}"
echo ""

# Step 6: Create DEBIAN control file
echo -e "${YELLOW}Step 6/6: Creating DEBIAN control file...${NC}"

cat > "${DEB_BUILD_DIR}/DEBIAN/control" << EOF
Package: ${PKG_NAME}
Version: ${VERSION}
Architecture: all
Maintainer: ${MAINTAINER}
Depends: python3, python3-pyqt5, python3-pip, openvpn, policykit-1
Recommends: xray | v2ray
Suggests: network-manager
Homepage: https://github.com/alfiy/pyQt_vpnv2ray_client
Description: PyQt-based VPN Client with V2Ray/Xray Support
 A PyQt5 GUI application for managing OpenVPN and V2Ray/Xray connections.
 Features include:
  - Simple and intuitive interface
  - Support for OpenVPN protocol
  - Support for V2Ray/Xray proxy protocol
  - Integrated connection management
  - PolicyKit integration for privilege escalation
EOF

# Create postinst script for post-installation tasks
cat > "${DEB_BUILD_DIR}/DEBIAN/postinst" << 'EOF'
#!/bin/bash
set -e

# Make launcher executable
chmod +x /usr/local/bin/pyqt-vpnv2ray-client || true

# Create symlink for convenience
ln -sf /usr/local/lib/pyqt-vpnv2ray-client /opt/pyqt-vpnv2ray-client || true

# Install polkit files
if [ -d "/usr/local/lib/pyqt-vpnv2ray-client/polkit" ]; then
    cp /usr/local/lib/pyqt-vpnv2ray-client/polkit/*.policy /usr/share/polkit-1/actions/ 2>/dev/null || true
    cp /usr/local/lib/pyqt-vpnv2ray-client/polkit/*.py /usr/local/bin/ 2>/dev/null || true
    chmod +x /usr/local/bin/vpn-helper.py 2>/dev/null || true
fi

# Update desktop database
update-desktop-database /usr/share/applications || true

# Install Python dependencies
pip3 install -q -r /usr/local/lib/pyqt-vpnv2ray-client/requirements.txt 2>/dev/null || python3 -m pip install -q -r /usr/local/lib/pyqt-vpnv2ray-client/requirements.txt || true

echo "Installation completed successfully!"
echo "Run 'pyqt-vpnv2ray-client' to start the application"
EOF

chmod +x "${DEB_BUILD_DIR}/DEBIAN/postinst"

# Create prerm script for pre-removal tasks
cat > "${DEB_BUILD_DIR}/DEBIAN/prerm" << 'EOF'
#!/bin/bash
set -e

# Remove polkit files
rm -f /usr/share/polkit-1/actions/org.example.vpnclient.policy 2>/dev/null || true
rm -f /usr/local/bin/vpn-helper.py 2>/dev/null || true

echo "Pre-removal tasks completed"
EOF

chmod +x "${DEB_BUILD_DIR}/DEBIAN/prerm"

echo -e "${GREEN}✓ DEBIAN control file created${NC}"
echo ""

# Step 7: Build the DEB package
echo -e "${YELLOW}Building DEB package...${NC}"

fakeroot dpkg-deb --build "${DEB_BUILD_DIR}" "${DIST_DIR}/${PKG_NAME}_${VERSION}_all.deb"

if [ -f "${DIST_DIR}/${PKG_NAME}_${VERSION}_all.deb" ]; then
    echo -e "${GREEN}✓ DEB package built successfully!${NC}"
    echo ""
    echo -e "${GREEN}Package details:${NC}"
    dpkg -I "${DIST_DIR}/${PKG_NAME}_${VERSION}_all.deb"
    echo ""
    echo -e "${GREEN}Package location: ${DIST_DIR}/${PKG_NAME}_${VERSION}_all.deb${NC}"
    echo ""
    echo -e "${YELLOW}To install the package:${NC}"
    echo "  sudo dpkg -i ${DIST_DIR}/${PKG_NAME}_${VERSION}_all.deb"
    echo ""
    echo -e "${YELLOW}To remove the package:${NC}"
    echo "  sudo apt-get remove ${PKG_NAME}"
else
    echo -e "${RED}✗ Failed to build DEB package${NC}"
    exit 1
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Build completed!${NC}"
echo -e "${GREEN}========================================${NC}"
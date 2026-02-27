#!/bin/bash
# ov2n Diagnostic Tool - 改进版
# 用于诊断 ov2n 安装和运行问题

echo ""
echo "╔═══════════════════════════════════════╗"
echo "║   ov2n - Diagnostic Tool v2.0         ║"
echo "╚═══════════════════════════════════════╝"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ISSUES_FOUND=0

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "System Information"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# OS Information
echo "OS:"
lsb_release -ds 2>/dev/null || cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2
echo ""

# Python version
echo "Python:"
python3 --version
echo ""

# Check PyQt5 installation
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PyQt5 Installation Check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 检查系统 PyQt5
if dpkg -l | grep -q "^ii.*python3-pyqt5"; then
    echo -e "${GREEN}✓ System python3-pyqt5 is installed${NC}"
else
    echo -e "${RED}✗ System python3-pyqt5 is NOT installed${NC}"
    echo "  Install with: sudo apt install python3-pyqt5"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
fi

# 检查 pip PyQt5 (应该没有)
if pip3 list 2>/dev/null | grep -q "^PyQt5"; then
    echo -e "${RED}✗ pip PyQt5 is installed (CONFLICT!)${NC}"
    echo "  This may cause symbol conflicts"
    echo "  Fix with: ./quick-fix.sh"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
else
    echo -e "${GREEN}✓ No pip PyQt5 (good)${NC}"
fi

# 检查 PyQt5 版本
check_pyqt5() {
    python3 -c "import PyQt5; print(f'PyQt5 version: {PyQt5.QtCore.QT_VERSION_STR}')" 2>/dev/null && return 0 || return 1
}

if check_pyqt5; then
    echo -e "${GREEN}✓ PyQt5 is functional${NC}"
    python3 -c "import PyQt5; print(f'  Version: {PyQt5.QtCore.QT_VERSION_STR}')" 2>/dev/null
    python3 -c "import PyQt5; print(f'  Location: {PyQt5.__file__}')" 2>/dev/null
else
    echo -e "${RED}✗ PyQt5 is NOT functional${NC}"
    echo "  Install with: sudo apt install python3-pyqt5"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
fi

# Check Qt libraries
echo ""
echo "Qt Libraries:"
if dpkg -l | grep -q "^ii.*libqt5"; then
    dpkg -l | grep "^ii.*libqt5" | head -3
    echo -e "${GREEN}✓ Qt libraries found${NC}"
else
    echo -e "${RED}✗ Qt libraries NOT found${NC}"
    echo "  Install with: sudo apt install libqt5gui5"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
fi

# 检查残留文件
echo ""
echo "Checking for PyQt5 residual files..."
RESIDUAL_FOUND=0

for py_ver in 3.8 3.9 3.10 3.11 3.12; do
    for location in dist-packages site-packages; do
        dir="/usr/local/lib/python${py_ver}/${location}/PyQt5"
        if [ -d "$dir" ]; then
            echo -e "${YELLOW}⚠ Residual PyQt5 found: $dir${NC}"
            RESIDUAL_FOUND=1
        fi
    done
done

if [ $RESIDUAL_FOUND -eq 0 ]; then
    echo -e "${GREEN}✓ No residual PyQt5 files${NC}"
else
    echo -e "${YELLOW}  Run ./quick-fix.sh to clean up${NC}"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "ov2n Installation Check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if ov2n is installed
if dpkg -l | grep -q "^ii.*ov2n"; then
    echo -e "${GREEN}✓ ov2n package is installed${NC}"
    dpkg -l | grep "^ii.*ov2n"
else
    echo -e "${YELLOW}⚠ ov2n package is NOT installed${NC}"
    echo "  Install with: sudo dpkg -i dist/ov2n_*.deb"
fi

# Check ov2n files
echo ""
echo "ov2n Files:"
if [ -f "/usr/local/bin/ov2n" ]; then
    echo -e "${GREEN}✓ /usr/local/bin/ov2n exists${NC}"
    if [ -x "/usr/local/bin/ov2n" ]; then
        echo -e "${GREEN}  ✓ Executable${NC}"
    else
        echo -e "${RED}  ✗ Not executable${NC}"
        ISSUES_FOUND=$((ISSUES_FOUND + 1))
    fi
else
    echo -e "${RED}✗ /usr/local/bin/ov2n NOT found${NC}"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
fi

if [ -d "/usr/local/lib/ov2n" ]; then
    echo -e "${GREEN}✓ /usr/local/lib/ov2n directory exists${NC}"
    echo "  Contents:"
    ls -la /usr/local/lib/ov2n/ 2>/dev/null | grep -E "^-|^d" | head -10
else
    echo -e "${RED}✗ /usr/local/lib/ov2n directory NOT found${NC}"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
fi

# Check main.py
if [ -f "/usr/local/lib/ov2n/main.py" ]; then
    echo -e "${GREEN}✓ main.py exists${NC}"
else
    echo -e "${RED}✗ main.py NOT found${NC}"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
fi

# Check ui directory
if [ -d "/usr/local/lib/ov2n/ui" ]; then
    echo -e "${GREEN}✓ ui directory exists${NC}"
else
    echo -e "${YELLOW}⚠ ui directory NOT found (may be optional)${NC}"
fi

# Check core directory
if [ -d "/usr/local/lib/ov2n/core" ]; then
    echo -e "${GREEN}✓ core directory exists${NC}"
else
    echo -e "${YELLOW}⚠ core directory NOT found (may be optional)${NC}"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Dependencies Check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

DEPS=("python3" "python3-pyqt5" "openvpn" "policykit-1")

for dep in "${DEPS[@]}"; do
    if dpkg -l | grep -q "^ii.*$dep"; then
        echo -e "${GREEN}✓ $dep is installed${NC}"
    else
        echo -e "${RED}✗ $dep is NOT installed${NC}"
        ISSUES_FOUND=$((ISSUES_FOUND + 1))
    fi
done

# Check optional dependencies
echo ""
echo "Optional Dependencies:"
if command -v xray &> /dev/null; then
    echo -e "${GREEN}✓ xray is installed${NC}"
    xray version 2>/dev/null | head -1
elif command -v v2ray &> /dev/null; then
    echo -e "${GREEN}✓ v2ray is installed${NC}"
    v2ray version 2>/dev/null | head -1
else
    echo -e "${YELLOW}⚠ Neither xray nor v2ray is installed${NC}"
    echo "  V2Ray functionality will not work"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment Variables"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "DISPLAY: ${DISPLAY:-not set}"
if [ -z "$DISPLAY" ]; then
    echo -e "${RED}  ✗ DISPLAY not set (GUI may not work)${NC}"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
fi

echo "QT_QPA_PLATFORM: ${QT_QPA_PLATFORM:-not set}"
echo "QT_QPA_PLATFORM_PLUGIN_PATH: ${QT_QPA_PLATFORM_PLUGIN_PATH:-not set}"
echo ""

# Test PyQt5 import
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PyQt5 Import Test"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

python3 << 'EOF'
import sys
import traceback

modules = [
    'PyQt5',
    'PyQt5.QtCore',
    'PyQt5.QtGui',
    'PyQt5.QtWidgets',
]

failed = False
for module in modules:
    try:
        mod = __import__(module)
        print(f"✓ {module} imported successfully")
        if hasattr(mod, '__file__'):
            print(f"  Location: {mod.__file__}")
    except Exception as e:
        print(f"✗ {module} import failed:")
        print(f"  {e}")
        failed = True

if failed:
    sys.exit(1)
EOF

if [ $? -ne 0 ]; then
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Diagnostic Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ $ISSUES_FOUND -eq 0 ]; then
    echo -e "${GREEN}╔═══════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✓ All checks passed!                ║${NC}"
    echo -e "${GREEN}║  ov2n should work correctly           ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════╝${NC}"
    echo ""
    echo "You can now run: ov2n"
else
    echo -e "${YELLOW}╔═══════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║  ⚠ Found $ISSUES_FOUND issue(s)                     ║${NC}"
    echo -e "${YELLOW}╚═══════════════════════════════════════╝${NC}"
    echo ""
    echo "Recommended actions:"
    echo ""
    
    # 给出具体建议
    if pip3 list 2>/dev/null | grep -q "^PyQt5"; then
        echo "1. Fix PyQt5 conflict:"
        echo -e "   ${YELLOW}./quick-fix.sh${NC}"
        echo ""
    fi
    
    if ! dpkg -l | grep -q "^ii.*ov2n"; then
        echo "2. Install ov2n:"
        echo -e "   ${YELLOW}./build-fixed.sh 1.0.1${NC}"
        echo -e "   ${YELLOW}sudo dpkg -i dist/ov2n_1.0.1_all.deb${NC}"
        echo ""
    fi
    
    if ! dpkg -l | grep -q "^ii.*python3-pyqt5"; then
        echo "3. Install PyQt5:"
        echo -e "   ${YELLOW}sudo apt install python3-pyqt5${NC}"
        echo ""
    fi
fi

echo ""
echo "For more help, see: PROBLEM-ANALYSIS.md"
echo ""
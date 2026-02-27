#!/bin/bash
# 完全重装系统 PyQt5

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════╗"
echo "║   完全重装系统 PyQt5                  ║"
echo "╚═══════════════════════════════════════╝"
echo -e "${NC}"
echo ""

echo -e "${YELLOW}这将完全卸载并重新安装系统 PyQt5 包${NC}"
echo ""
read -p "是否继续? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "已取消"
    exit 0
fi

echo ""
echo -e "${YELLOW}步骤 1: 检查当前 PyQt5 文件...${NC}"
echo ""

echo "检查 QtCore.so 是否存在..."
if [ -f "/usr/lib/python3/dist-packages/PyQt5/QtCore.so" ]; then
    echo -e "${GREEN}✓ QtCore.so 存在${NC}"
    ls -lh /usr/lib/python3/dist-packages/PyQt5/QtCore.so
elif [ -f "/usr/lib/python3/dist-packages/PyQt5/QtCore.abi3.so" ]; then
    echo -e "${GREEN}✓ QtCore.abi3.so 存在${NC}"
    ls -lh /usr/lib/python3/dist-packages/PyQt5/QtCore.abi3.so
else
    echo -e "${RED}✗ QtCore.so 不存在! 系统包已损坏${NC}"
fi

echo ""
echo "PyQt5 目录内容:"
ls -la /usr/lib/python3/dist-packages/PyQt5/ | head -15

echo ""
echo -e "${YELLOW}步骤 2: 完全卸载所有 python3-pyqt5 相关包...${NC}"
echo ""

sudo apt-get remove --purge -y \
    python3-pyqt5 \
    python3-pyqt5.* \
    python3-sip \
    sip-dev \
    pyqt5-dev \
    pyqt5-dev-tools 2>/dev/null || true

echo ""
echo -e "${YELLOW}步骤 3: 清理残留文件...${NC}"
echo ""

sudo rm -rf /usr/lib/python3/dist-packages/PyQt5* 2>/dev/null || true
sudo rm -rf /usr/lib/python3/dist-packages/sip* 2>/dev/null || true

echo -e "${GREEN}✓ 残留文件已清理${NC}"

echo ""
echo -e "${YELLOW}步骤 4: 运行 autoremove...${NC}"
echo ""

sudo apt-get autoremove -y
sudo apt-get clean

echo ""
echo -e "${YELLOW}步骤 5: 更新包列表...${NC}"
echo ""

sudo apt-get update

echo ""
echo -e "${YELLOW}步骤 6: 重新安装 python3-pyqt5...${NC}"
echo ""

sudo apt-get install -y \
    python3-pyqt5 \
    python3-pyqt5.qtcore \
    python3-pyqt5.qtgui \
    python3-pyqt5.qtwidgets \
    python3-pyqt5.qtsql \
    libqt5core5a \
    libqt5gui5 \
    libqt5widgets5

if [ $? -ne 0 ]; then
    echo -e "${RED}✗ 安装失败!${NC}"
    echo ""
    echo "尝试修复依赖:"
    sudo apt-get install -f -y
    echo ""
    echo "再次尝试安装:"
    sudo apt-get install -y python3-pyqt5
fi

echo ""
echo -e "${YELLOW}步骤 7: 验证安装...${NC}"
echo ""

echo "检查包状态:"
dpkg -l | grep python3-pyqt5

echo ""
echo "检查 QtCore.so:"
if [ -f "/usr/lib/python3/dist-packages/PyQt5/QtCore.so" ] || [ -f "/usr/lib/python3/dist-packages/PyQt5/QtCore.abi3.so" ]; then
    echo -e "${GREEN}✓ QtCore.so 已安装${NC}"
    ls -lh /usr/lib/python3/dist-packages/PyQt5/QtCore.*so 2>/dev/null
else
    echo -e "${RED}✗ QtCore.so 仍然不存在!${NC}"
fi

echo ""
echo -e "${YELLOW}步骤 8: 测试 Python 导入...${NC}"
echo ""

python3 << 'EOF'
import sys

print("=" * 50)
print("Python 导入测试")
print("=" * 50)
print()

# 测试 1: 导入 PyQt5
try:
    import PyQt5
    print(f"✓ PyQt5 导入成功")
    print(f"  路径: {PyQt5.__file__}")
except Exception as e:
    print(f"✗ PyQt5 导入失败: {e}")
    sys.exit(1)

# 测试 2: 导入 QtCore
try:
    from PyQt5 import QtCore
    print(f"✓ QtCore 导入成功")
    print(f"  Qt 版本: {QtCore.QT_VERSION_STR}")
    print(f"  PyQt 版本: {QtCore.PYQT_VERSION_STR}")
except Exception as e:
    print(f"✗ QtCore 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 测试 3: 导入 QtWidgets
try:
    from PyQt5.QtWidgets import QApplication, QWidget
    print(f"✓ QtWidgets 导入成功")
except Exception as e:
    print(f"✗ QtWidgets 导入失败: {e}")
    sys.exit(1)

# 测试 4: 创建应用
try:
    app = QApplication([])
    print(f"✓ QApplication 创建成功")
except Exception as e:
    print(f"✗ QApplication 创建失败: {e}")
    sys.exit(1)

print()
print("=" * 50)
print("✓✓✓ 所有测试通过! ✓✓✓")
print("=" * 50)
EOF

RESULT=$?

echo ""
if [ $RESULT -eq 0 ]; then
    echo -e "${GREEN}"
    echo "╔═══════════════════════════════════════╗"
    echo "║     重装成功!                         ║"
    echo "╚═══════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""
    echo "现在可以运行 ov2n:"
    echo "  ov2n"
    echo ""
    
    # 检查 pip 状态
    echo "检查 pip 状态:"
    PIP_PYQT=$(pip3 list 2>/dev/null | grep -i pyqt)
    if [ -n "$PIP_PYQT" ]; then
        echo -e "${YELLOW}注意: pip 仍然显示有 PyQt5:${NC}"
        echo "$PIP_PYQT"
        echo ""
        echo "这是正常的 - pip 识别了系统包"
        echo "只要上面的 Python 测试通过,就没有问题"
    fi
else
    echo -e "${RED}"
    echo "╔═══════════════════════════════════════╗"
    echo "║     重装后仍有问题!                   ║"
    echo "╚═══════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""
    echo "可能的原因:"
    echo "1. 系统包仓库问题"
    echo "2. 依赖冲突"
    echo "3. Python 环境问题"
    echo ""
    echo "建议:"
    echo "1. 检查系统更新:"
    echo "   sudo apt-get update && sudo apt-get upgrade"
    echo ""
    echo "2. 尝试不同的包源"
    echo ""
    echo "3. 检查是否有 PPA 冲突:"
    echo "   ls /etc/apt/sources.list.d/"
    echo ""
fi
#!/bin/bash
# PyQt5 深度诊断脚本

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════╗"
echo "║   PyQt5 深度诊断                      ║"
echo "╚═══════════════════════════════════════╝"
echo -e "${NC}"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1. pip list 详细信息"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "所有 PyQt 相关包:"
pip3 list 2>/dev/null | grep -i pyqt
echo ""

echo "pip3 freeze 输出:"
pip3 freeze 2>/dev/null | grep -i pyqt
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2. 搜索所有 PyQt5 目录"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "在 /usr/local 搜索..."
sudo find /usr/local -type d -name "*PyQt5*" 2>/dev/null || echo "  未找到"

echo ""
echo "在 ~/.local 搜索..."
find ~/.local -type d -name "*PyQt5*" 2>/dev/null || echo "  未找到"

echo ""
echo "在 /usr/lib 搜索..."
find /usr/lib -type d -name "*PyQt5*" 2>/dev/null | head -5

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3. 检查 .so 文件"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "在 /usr/local 搜索 PyQt5 的 .so 文件..."
sudo find /usr/local -name "*.so" -path "*/PyQt5/*" 2>/dev/null | head -10
if [ $? -ne 0 ] || [ -z "$(sudo find /usr/local -name "*.so" -path "*/PyQt5/*" 2>/dev/null)" ]; then
    echo "  未找到(正常)"
fi

echo ""
echo "在 ~/.local 搜索 PyQt5 的 .so 文件..."
find ~/.local -name "*.so" -path "*/PyQt5/*" 2>/dev/null | head -10
if [ $? -ne 0 ] || [ -z "$(find ~/.local -name "*.so" -path "*/PyQt5/*" 2>/dev/null)" ]; then
    echo "  未找到(正常)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4. 检查 dist-info 和 egg-info"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "在 /usr/local 搜索..."
sudo find /usr/local -type d -name "PyQt5*.dist-info" -o -name "PyQt5*.egg-info" 2>/dev/null
if [ $? -ne 0 ] || [ -z "$(sudo find /usr/local -type d -name "PyQt5*.dist-info" -o -name "PyQt5*.egg-info" 2>/dev/null)" ]; then
    echo "  未找到(正常)"
fi

echo ""
echo "在 ~/.local 搜索..."
find ~/.local -type d -name "PyQt5*.dist-info" -o -name "PyQt5*.egg-info" 2>/dev/null
if [ $? -ne 0 ] || [ -z "$(find ~/.local -type d -name "PyQt5*.dist-info" -o -name "PyQt5*.egg-info" 2>/dev/null)" ]; then
    echo "  未找到(正常)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5. Python 模块搜索路径"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

python3 << 'EOF'
import sys
print("Python 搜索路径 (按优先级排序):")
for i, path in enumerate(sys.path, 1):
    print(f"{i}. {path}")
EOF

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6. 尝试导入 PyQt5 并查看路径"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

python3 << 'EOF'
import sys

print("尝试导入 PyQt5...")
try:
    import PyQt5
    print(f"✓ PyQt5 导入成功")
    print(f"  路径: {PyQt5.__file__}")
    print(f"  版本: {PyQt5.QtCore.QT_VERSION_STR}")
    
    # 检查是否是系统路径
    if '/usr/lib/python3/dist-packages' in PyQt5.__file__:
        print("  ✓ 使用的是系统 PyQt5 (正确)")
    elif '/usr/local' in PyQt5.__file__ or '.local' in PyQt5.__file__:
        print("  ✗ 使用的是 pip PyQt5 (错误!)")
    
except Exception as e:
    print(f"✗ PyQt5 导入失败: {e}")
    sys.exit(1)

print()
print("尝试导入 PyQt5.QtWidgets...")
try:
    from PyQt5 import QtWidgets
    print(f"✓ PyQt5.QtWidgets 导入成功")
    print(f"  路径: {QtWidgets.__file__}")
except Exception as e:
    print(f"✗ PyQt5.QtWidgets 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("尝试创建 QApplication...")
try:
    app = QtWidgets.QApplication([])
    print("✓ QApplication 创建成功")
except Exception as e:
    print(f"✗ QApplication 创建失败: {e}")
    sys.exit(1)
EOF

RESULT=$?

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "7. 总结"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ $RESULT -eq 0 ]; then
    echo -e "${GREEN}✓ PyQt5 工作正常!${NC}"
else
    echo -e "${RED}✗ PyQt5 有问题,请查看上面的详细信息${NC}"
fi

echo ""
echo "如果发现 pip PyQt5 残留,请手动删除:"
echo "  sudo rm -rf /usr/local/lib/python*/dist-packages/PyQt5*"
echo "  sudo rm -rf ~/.local/lib/python*/site-packages/PyQt5*"
echo ""
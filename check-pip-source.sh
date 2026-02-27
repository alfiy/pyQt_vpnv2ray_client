#!/bin/bash
# 检查 pip 为什么会列出系统包

echo "检查 pip 如何识别 PyQt5..."
echo ""

echo "1. pip show PyQt5 详细信息:"
pip3 show PyQt5
echo ""

echo "2. pip show PyQt5-sip 详细信息:"
pip3 show PyQt5-sip
echo ""

echo "3. 检查系统 PyQt5 的 dist-info:"
ls -la /usr/lib/python3/dist-packages/ | grep -i pyqt
echo ""

echo "4. 检查 EXTERNALLY-MANAGED 文件:"
if [ -f "/usr/lib/python3.10/EXTERNALLY-MANAGED" ]; then
    echo "存在 EXTERNALLY-MANAGED 文件:"
    cat /usr/lib/python3.10/EXTERNALLY-MANAGED
else
    echo "不存在 EXTERNALLY-MANAGED 文件"
fi
echo ""

echo "5. 测试 QtCore 模块:"
python3 << 'EOF'
import sys
import os

print("尝试直接导入 QtCore...")
try:
    from PyQt5 import QtCore
    print(f"✓ QtCore 导入成功")
    print(f"  文件: {QtCore.__file__}")
    print(f"  版本: {QtCore.QT_VERSION_STR}")
except Exception as e:
    print(f"✗ QtCore 导入失败: {e}")
    print()
    print("检查 PyQt5 目录内容:")
    pyqt5_path = "/usr/lib/python3/dist-packages/PyQt5"
    if os.path.exists(pyqt5_path):
        files = os.listdir(pyqt5_path)
        print(f"  找到 {len(files)} 个文件:")
        for f in sorted(files)[:20]:
            print(f"    {f}")
        
        # 检查是否有 QtCore
        if "QtCore.so" in files or "QtCore.abi3.so" in files:
            print()
            print("  ✓ QtCore.so 存在")
        else:
            print()
            print("  ✗ QtCore.so 不存在!")
    
    import traceback
    print()
    print("详细错误:")
    traceback.print_exc()
EOF
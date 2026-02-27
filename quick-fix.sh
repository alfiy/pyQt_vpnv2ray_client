#!/bin/bash
# 快速清理 pip PyQt5 残留文件

echo "正在清理 pip PyQt5 残留文件..."
echo ""

# 卸载 pip 包
echo "1. 卸载 pip PyQt5 包..."
pip3 uninstall -y PyQt5 PyQt5-sip PyQt5-Qt5 PyQtWebEngine 2>/dev/null || true

echo ""
echo "2. 删除残留目录..."

# 删除所有可能的 PyQt5 目录
for py_ver in 3.8 3.9 3.10 3.11 3.12; do
    for location in dist-packages site-packages; do
        dir="/usr/local/lib/python${py_ver}/${location}/PyQt5"
        if [ -d "$dir" ]; then
            echo "  删除: $dir"
            sudo rm -rf "$dir"
        fi
        
        dir="$HOME/.local/lib/python${py_ver}/${location}/PyQt5"
        if [ -d "$dir" ]; then
            echo "  删除: $dir"
            rm -rf "$dir"
        fi
    done
done

echo ""
echo "3. 删除 egg-info 和 dist-info..."
sudo find /usr/local/lib -name "PyQt5*.egg-info" -o -name "PyQt5*.dist-info" 2>/dev/null | xargs -r sudo rm -rf
find "$HOME/.local/lib" -name "PyQt5*.egg-info" -o -name "PyQt5*.dist-info" 2>/dev/null | xargs -r rm -rf

echo ""
echo "4. 重新安装系统 PyQt5..."
sudo apt-get install --reinstall -y python3-pyqt5

echo ""
echo "5. 验证安装..."
if python3 -c "from PyQt5.QtWidgets import QApplication" 2>/dev/null; then
    echo "✓ PyQt5 安装成功!"
    python3 -c "import PyQt5; print('PyQt5 路径:', PyQt5.__file__)"
else
    echo "✗ PyQt5 仍有问题"
    exit 1
fi

echo ""
echo "完成! 现在可以运行 ov2n 了"
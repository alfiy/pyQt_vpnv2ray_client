#!/bin/bash
# 超级清理脚本 - 彻底删除所有 pip PyQt5

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════╗"
echo "║   PyQt5 超级清理工具                  ║"
echo "║   WARNING: This will remove ALL pip  ║"
echo "║   PyQt5 installations!               ║"
echo "╚═══════════════════════════════════════╝"
echo -e "${NC}"
echo ""

read -p "是否继续? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "已取消"
    exit 0
fi

echo ""
echo -e "${YELLOW}步骤 1: 卸载所有 pip PyQt 相关包...${NC}"
echo ""

# 列出所有 PyQt 包
PYQT_PACKAGES=$(pip3 list 2>/dev/null | grep -i pyqt | awk '{print $1}')

if [ -n "$PYQT_PACKAGES" ]; then
    echo "发现以下 pip PyQt 包:"
    echo "$PYQT_PACKAGES"
    echo ""
    
    for pkg in $PYQT_PACKAGES; do
        echo "卸载 $pkg..."
        pip3 uninstall -y "$pkg" 2>/dev/null || true
    done
    echo -e "${GREEN}✓ pip 包已卸载${NC}"
else
    echo "未发现 pip PyQt 包"
fi

echo ""
echo -e "${YELLOW}步骤 2: 删除 /usr/local 中的残留...${NC}"
echo ""

# 删除所有可能的 PyQt5 目录和文件
for py_ver in 3.6 3.7 3.8 3.9 3.10 3.11 3.12; do
    for location in dist-packages site-packages; do
        base_dir="/usr/local/lib/python${py_ver}/${location}"
        
        if [ -d "$base_dir" ]; then
            # 删除 PyQt5 目录
            if [ -d "$base_dir/PyQt5" ]; then
                echo "  删除: $base_dir/PyQt5"
                sudo rm -rf "$base_dir/PyQt5"
            fi
            
            # 删除 PyQt5*.dist-info
            for dir in "$base_dir"/PyQt5*.dist-info; do
                if [ -d "$dir" ]; then
                    echo "  删除: $dir"
                    sudo rm -rf "$dir"
                fi
            done
            
            # 删除 PyQt5*.egg-info
            for dir in "$base_dir"/PyQt5*.egg-info; do
                if [ -d "$dir" ]; then
                    echo "  删除: $dir"
                    sudo rm -rf "$dir"
                fi
            done
            
            # 删除 sip* 相关
            for item in "$base_dir"/sip* "$base_dir"/PyQt5_sip*; do
                if [ -e "$item" ]; then
                    echo "  删除: $item"
                    sudo rm -rf "$item"
                fi
            done
        fi
    done
done

echo -e "${GREEN}✓ /usr/local 清理完成${NC}"

echo ""
echo -e "${YELLOW}步骤 3: 删除 ~/.local 中的残留...${NC}"
echo ""

for py_ver in 3.6 3.7 3.8 3.9 3.10 3.11 3.12; do
    for location in site-packages lib; do
        base_dir="$HOME/.local/lib/python${py_ver}/${location}"
        
        if [ -d "$base_dir" ]; then
            # 删除 PyQt5 目录
            if [ -d "$base_dir/PyQt5" ]; then
                echo "  删除: $base_dir/PyQt5"
                rm -rf "$base_dir/PyQt5"
            fi
            
            # 删除相关文件
            for pattern in "PyQt5*.dist-info" "PyQt5*.egg-info" "sip*" "PyQt5_sip*"; do
                for item in "$base_dir"/$pattern; do
                    if [ -e "$item" ]; then
                        echo "  删除: $item"
                        rm -rf "$item"
                    fi
                done
            done
        fi
    done
done

echo -e "${GREEN}✓ ~/.local 清理完成${NC}"

echo ""
echo -e "${YELLOW}步骤 4: 清理 pip 缓存...${NC}"
echo ""

pip3 cache purge 2>/dev/null || pip3 cache remove PyQt5 2>/dev/null || true
echo -e "${GREEN}✓ pip 缓存已清理${NC}"

echo ""
echo -e "${YELLOW}步骤 5: 清理 Python 缓存...${NC}"
echo ""

# 清理 __pycache__
find /usr/local/lib/python* -type d -name "__pycache__" -path "*/PyQt5/*" -exec sudo rm -rf {} + 2>/dev/null || true
find ~/.local/lib/python* -type d -name "__pycache__" -path "*/PyQt5/*" -exec rm -rf {} + 2>/dev/null || true

echo -e "${GREEN}✓ Python 缓存已清理${NC}"

echo ""
echo -e "${YELLOW}步骤 6: 重新安装系统 PyQt5...${NC}"
echo ""

# 先卸载再安装,确保干净
sudo apt-get remove --purge python3-pyqt5* -y 2>/dev/null || true
sudo apt-get autoremove -y 2>/dev/null || true
sudo apt-get clean

echo "安装系统 PyQt5..."
sudo apt-get update -qq
sudo apt-get install -y \
    python3-pyqt5 \
    python3-pyqt5.qtcore \
    python3-pyqt5.qtgui \
    python3-pyqt5.qtwidgets \
    libqt5core5a \
    libqt5gui5 \
    libqt5widgets5

echo -e "${GREEN}✓ 系统 PyQt5 已安装${NC}"

echo ""
echo -e "${YELLOW}步骤 7: 验证安装...${NC}"
echo ""

python3 << 'EOF'
import sys

print("验证 PyQt5...")
try:
    import PyQt5
    print(f"✓ PyQt5 路径: {PyQt5.__file__}")
    
    if '/usr/lib/python3/dist-packages' in PyQt5.__file__:
        print("✓ 正确使用系统 PyQt5")
    else:
        print(f"✗ 错误! 仍在使用: {PyQt5.__file__}")
        sys.exit(1)
    
    from PyQt5.QtWidgets import QApplication
    print("✓ QtWidgets 导入成功")
    
    app = QApplication([])
    print("✓ QApplication 创建成功")
    
    print()
    print("✓✓✓ 所有测试通过! ✓✓✓")
    
except Exception as e:
    print(f"✗ 验证失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}"
    echo "╔═══════════════════════════════════════╗"
    echo "║     清理完成! PyQt5 已修复            ║"
    echo "╚═══════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""
    echo "现在可以运行 ov2n 了:"
    echo "  ov2n"
    echo ""
else
    echo ""
    echo -e "${RED}"
    echo "╔═══════════════════════════════════════╗"
    echo "║     清理后仍有问题                    ║"
    echo "╚═══════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""
    echo "请运行深度诊断:"
    echo "  ./deep-diagnose.sh"
    echo ""
fi
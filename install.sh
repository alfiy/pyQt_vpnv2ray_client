#!/bin/bash
# 自动安装脚本

set -e

echo "=========================================="
echo "OpenVPN + V2Ray Client 安装脚本"
echo "=========================================="
echo ""

# 检测发行版
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    echo "无法检测操作系统类型"
    exit 1
fi

echo "检测到操作系统: $OS"
echo ""

# 安装系统依赖
echo "步骤 1/5: 安装系统依赖..."
case $OS in
    ubuntu|debian)
        sudo apt-get update
        sudo apt-get install -y python3 python3-pip python3-pyqt5 policykit-1 openvpn
        ;;
    fedora|rhel|centos)
        sudo dnf install -y python3 python3-pip python3-qt5 polkit openvpn
        ;;
    arch|manjaro)
        sudo pacman -S --noconfirm python python-pip python-pyqt5 polkit openvpn
        ;;
    *)
        echo "不支持的操作系统: $OS"
        echo "请手动安装依赖,参考 INSTALL.md"
        exit 1
        ;;
esac

echo "✓ 系统依赖安装完成"
echo ""

# 安装 Python 依赖
echo "步骤 2/5: 安装 Python 依赖..."
pip3 install --user PyQt5
echo "✓ Python 依赖安装完成"
echo ""

# 安装 Polkit 配置
echo "步骤 3/5: 安装 Polkit 配置..."
sudo cp polkit/org.example.vpnclient.policy /usr/share/polkit-1/actions/
sudo cp polkit/vpn-helper.py /usr/local/bin/
sudo chmod +x /usr/local/bin/vpn-helper.py
echo "✓ Polkit 配置安装完成"
echo ""

# 验证安装
echo "步骤 4/5: 验证安装..."
if [ -f /usr/share/polkit-1/actions/org.example.vpnclient.policy ]; then
    echo "✓ Polkit 策略文件已安装"
else
    echo "✗ Polkit 策略文件安装失败"
    exit 1
fi

if [ -x /usr/local/bin/vpn-helper.py ]; then
    echo "✓ Helper 脚本已安装"
else
    echo "✗ Helper 脚本安装失败"
    exit 1
fi

# 检查 Xray/V2Ray
echo ""
echo "步骤 5/5: 检查 V2Ray/Xray..."
if command -v xray &> /dev/null; then
    echo "✓ Xray 已安装"
elif command -v v2ray &> /dev/null; then
    echo "✓ V2Ray 已安装"
else
    echo "⚠ 未检测到 Xray 或 V2Ray"
    echo ""
    read -p "是否现在安装 Xray? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
        echo "✓ Xray 安装完成"
    else
        echo "跳过 Xray 安装"
        echo "您可以稍后手动安装: https://github.com/XTLS/Xray-install"
    fi
fi

echo ""
echo "=========================================="
echo "安装完成!"
echo "=========================================="
echo ""
echo "下一步:"
echo "1. 将 OpenVPN 配置文件放到: core/openvpn/"
echo "2. 将 V2Ray 配置文件放到: core/xray/"
echo "3. 运行程序: python3 main.py"
echo ""
echo "详细文档请查看 README.md 和 INSTALL.md"
echo ""
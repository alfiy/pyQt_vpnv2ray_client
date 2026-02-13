# 安装指南

## 快速安装

### 1. 克隆或下载项目

```bash
git clone <repository-url>
cd openvpn-v2ray-client
```

### 2. 运行自动安装脚本

```bash
chmod +x install.sh
./install.sh
```

## 手动安装

### 1. 安装系统依赖

#### Ubuntu/Debian

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-pyqt5 policykit-1 openvpn
```

#### Fedora/RHEL

```bash
sudo dnf install -y python3 python3-pip python3-qt5 polkit openvpn
```

#### Arch Linux

```bash
sudo pacman -S python python-pip python-pyqt5 polkit openvpn
```

### 2. 安装 Xray-core (可选,如果使用 V2Ray)

```bash
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
```

或者安装 V2Ray:

```bash
bash <(curl -L https://raw.githubusercontent.com/v2fly/fhs-install-v2ray/master/install-release.sh)
```

### 3. 安装 Python 依赖

```bash
pip3 install PyQt5
```

### 4. 安装 Polkit 配置

```bash
# 复制策略文件
sudo cp polkit/org.example.vpnclient.policy /usr/share/polkit-1/actions/

# 复制 helper 脚本
sudo cp polkit/vpn-helper.py /usr/local/bin/
sudo chmod +x /usr/local/bin/vpn-helper.py

# 验证安装
ls -l /usr/share/polkit-1/actions/org.example.vpnclient.policy
ls -l /usr/local/bin/vpn-helper.py
```

### 5. 添加配置文件

将您的配置文件放到相应目录:

```bash
# OpenVPN 配置
cp your-vpn-config.ovpn core/openvpn/client.ovpn

# V2Ray/Xray 配置
cp your-v2ray-config.json core/xray/config.json
```

### 6. 运行程序

```bash
python3 main.py
```

## 验证安装

### 检查 Polkit 策略

```bash
pkaction --action-id org.example.vpnclient.start --verbose
```

应该显示策略详情。

### 测试 Helper 脚本

```bash
# 这会弹出密码输入对话框
pkexec /usr/local/bin/vpn-helper.py
```

如果提示 "用法: vpn-helper.py <start|stop> [参数...]",说明安装成功。

## 故障排除

### 问题 1: "pkexec 未找到"

**解决方案**: 安装 polkit

```bash
# Ubuntu/Debian
sudo apt-get install policykit-1

# Fedora
sudo dnf install polkit
```

### 问题 2: "策略文件未找到"

**解决方案**: 确认策略文件路径

```bash
ls /usr/share/polkit-1/actions/org.example.vpnclient.policy
```

如果不存在,重新复制:

```bash
sudo cp polkit/org.example.vpnclient.policy /usr/share/polkit-1/actions/
```

### 问题 3: "Helper 脚本无执行权限"

**解决方案**: 设置执行权限

```bash
sudo chmod +x /usr/local/bin/vpn-helper.py
```

### 问题 4: "OpenVPN 未找到"

**解决方案**: 安装 OpenVPN

```bash
# Ubuntu/Debian
sudo apt-get install openvpn

# Fedora
sudo dnf install openvpn
```

### 问题 5: "Xray/V2Ray 未找到"

**解决方案**: 安装 Xray 或 V2Ray (选择其一)

```bash
# 安装 Xray
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install

# 或安装 V2Ray
bash <(curl -L https://raw.githubusercontent.com/v2fly/fhs-install-v2ray/master/install-release.sh)
```

### 问题 6: PyQt5 导入错误

**解决方案**: 重新安装 PyQt5

```bash
pip3 uninstall PyQt5
pip3 install PyQt5
```

## 卸载

```bash
# 删除 Polkit 配置
sudo rm /usr/share/polkit-1/actions/org.example.vpnclient.policy
sudo rm /usr/local/bin/vpn-helper.py

# 删除项目文件
cd ..
rm -rf openvpn-v2ray-client
```

## 权限说明

- **Polkit 策略**: 允许普通用户通过密码认证执行特权操作
- **Helper 脚本**: 以 root 权限运行,但只能执行预定义的操作
- **应用程序**: 以普通用户权限运行,通过 polkit 请求权限提升

这种设计确保了安全性,避免了 setuid 或 sudo 配置的风险。
# OpenVPN + V2Ray Client with Polkit

这是一个使用 PyQt5 开发的 OpenVPN + V2Ray 客户端,通过 polkit 实现权限提升,避免直接使用 sudo。

## 功能特性

- ✅ 通过 polkit 安全地执行需要 root 权限的操作
- ✅ 用户友好的图形界面密码输入提示
- ✅ 支持 OpenVPN 和 V2Ray/Xray 配置文件选择
- ✅ 实时状态显示和进度条
- ✅ 安全的进程管理和清理

## 系统要求

- Linux 系统(Ubuntu/Debian/Fedora 等)
- Python 3.8+
- PyQt5
- polkit
- openvpn
- v2ray 或 xray-core

## 安装步骤

### 1. 安装系统依赖

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install python3-pyqt5 policykit-1 openvpn

# Fedora
sudo dnf install python3-qt5 polkit openvpn

# 安装 xray-core (可选)
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
```

### 2. 安装 Python 依赖

```bash
pip3 install PyQt5
```

### 3. 安装 Polkit 配置

```bash
# 复制 polkit 策略文件
sudo cp polkit/org.example.vpnclient.policy /usr/share/polkit-1/actions/

# 复制 helper 脚本
sudo cp polkit/vpn-helper.py /usr/local/bin/
sudo chmod +x /usr/local/bin/vpn-helper.py
```

### 4. 创建配置目录

```bash
mkdir -p core/openvpn core/xray
```

### 5. 添加配置文件

将您的 OpenVPN 配置文件放到 `core/openvpn/client.ovpn`
将您的 V2Ray/Xray 配置文件放到 `core/xray/config.json`

## 使用方法

```bash
python3 main.py
```

1. 点击 "Select OpenVPN Config" 选择 OpenVPN 配置文件
2. 点击 "Select V2Ray Config" 选择 V2Ray 配置文件
3. 点击 "Start VPN + V2Ray" 启动连接
4. 系统会弹出 polkit 密码输入窗口,输入您的用户密码
5. 连接成功后状态栏会显示相关信息

## 项目结构

```
.
├── main.py                 # 程序入口
├── ui/
│   └── main_window.py      # 主窗口界面
├── core/
│   ├── worker.py           # 后台工作线程
│   ├── polkit_helper.py    # Polkit 集成模块
│   ├── openvpn/            # OpenVPN 配置目录
│   └── xray/               # V2Ray/Xray 配置目录
├── polkit/
│   ├── org.example.vpnclient.policy  # Polkit 策略文件
│   └── vpn-helper.py       # Polkit helper 脚本
└── README.md

```
## 构建方法

```
# 构建默认版本(1.0.0)
./build.sh
# 构建指定版本  
./build.sh --version 1.0.1  

# 清理
./build.sh clean

# 重建
./build.sh rebuild --version 1.0.1

# 调试模式
./build.sh debug

```
## 工作原理

1. **权限提升流程**:
   - 用户点击启动按钮
   - 应用通过 D-Bus 调用 polkit
   - Polkit 弹出密码输入对话框
   - 验证成功后执行 helper 脚本
   - Helper 脚本以 root 权限启动 OpenVPN 和 V2Ray

2. **安全性**:
   - 不需要 setuid 或 sudo 配置
   - 使用系统标准的 polkit 认证
   - Helper 脚本权限受限,只能执行特定操作
   - 进程管理和清理由应用程序控制

## 故障排除

### Polkit 认证失败
- 确保已正确安装策略文件: `ls /usr/share/polkit-1/actions/org.example.vpnclient.policy`
- 检查 helper 脚本权限: `ls -l /usr/local/bin/vpn-helper.py`

### OpenVPN 连接失败
- 检查配置文件路径和内容
- 查看日志: `journalctl -xe | grep openvpn`

### V2Ray 启动失败
- 确认 xray-core 已安装: `which xray`
- 验证配置文件格式: `xray -test -config core/xray/config.json`

## 许可证

MIT License

# TAP-Windows 驱动

## 说明

此目录用于存放 Windows 版本所需的 TAP-Windows 网络适配器驱动。
OpenVPN 在 Windows 上需要 TAP 虚拟网卡驱动才能建立 VPN 隧道。

## 驱动来源

推荐使用 OpenVPN 官方提供的 TAP-Windows 驱动：

- **tap-windows6**: https://github.com/OpenVPN/tap-windows6/releases
- **wintun** (新一代，性能更好): https://www.wintun.net/

## 目录结构

安装后此目录应包含以下文件：

```
tap-windows/
├── README.md          # 本文件
├── amd64/             # 64 位驱动
│   ├── OemVista.inf
│   ├── tap0901.cat
│   └── tap0901.sys
├── i386/              # 32 位驱动
│   ├── OemVista.inf
│   ├── tap0901.cat
│   └── tap0901.sys
├── tapinstall.exe     # 驱动安装工具 (64位)
└── addtap.bat         # 安装脚本
```

## 安装方式

### 自动安装（推荐）

应用首次运行时会检测 TAP 驱动是否已安装，若未安装则自动执行：

```batch
tapinstall.exe install OemVista.inf tap0901
```

### 手动安装

以管理员身份运行命令提示符：

```batch
cd resources\tap-windows\amd64
tapinstall.exe install OemVista.inf tap0901
```

### 卸载

```batch
tapinstall.exe remove tap0901
```

## 替代方案：Wintun

如果使用 OpenVPN 2.5+ 或 Xray/V2Ray 的 TUN 模式，可以使用 Wintun 驱动：

1. 下载 wintun.dll: https://www.wintun.net/
2. 将 wintun.dll 放置到应用目录或 System32
3. 在 OpenVPN 配置中添加 `windows-driver wintun`

## 注意事项

- TAP 驱动安装需要管理员权限
- 安装后可能需要重启网络适配器
- 某些杀毒软件可能阻止驱动安装，请添加白名单
- 建议使用 Windows 10 1903+ 以获得最佳兼容性
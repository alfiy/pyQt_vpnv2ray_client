# Windows Service 设计文档

## 概述

`ov2n-service` 是一个 Windows 后台服务，用于执行需要管理员权限的操作，
避免每次启停 VPN 时弹出 UAC 对话框。

## 架构设计

```
┌──────────────────┐     命名管道/TCP      ┌──────────────────────┐
│   ov2n GUI       │  ──────────────────►  │   ov2n-service       │
│   (用户权限)      │  ◄──────────────────  │   (SYSTEM 权限)       │
│                  │     JSON-RPC          │                      │
│  - PyQt5 界面    │                       │  - 启动/停止 OpenVPN  │
│  - 配置管理      │                       │  - 启动/停止 V2Ray    │
│  - 状态显示      │                       │  - 设置系统代理       │
│                  │                       │  - TAP 驱动管理       │
└──────────────────┘                       └──────────────────────┘
```

## 通信协议

GUI 与 Service 之间使用 JSON-RPC 2.0 协议通过命名管道通信：

### 管道名称
```
\\.\pipe\ov2n-service
```

### 请求格式
```json
{
    "jsonrpc": "2.0",
    "method": "start_vpn",
    "params": {
        "vpn_config": "C:\\Users\\xxx\\.config\\ov2n\\client.ovpn",
        "v2ray_config": "C:\\Users\\xxx\\.config\\ov2n\\config.json"
    },
    "id": 1
}
```

### 响应格式
```json
{
    "jsonrpc": "2.0",
    "result": {
        "success": true,
        "pids": {"openvpn": 1234, "v2ray": 5678}
    },
    "id": 1
}
```

## 支持的方法

| 方法 | 参数 | 说明 |
|------|------|------|
| `start_vpn` | vpn_config, v2ray_config | 启动 OpenVPN + V2Ray |
| `stop_vpn` | openvpn_pid, v2ray_pid | 停止 VPN 进程 |
| `start_vpn_only` | vpn_config | 仅启动 OpenVPN |
| `start_v2ray_only` | v2ray_config | 仅启动 V2Ray |
| `set_proxy` | socks_port, http_port, bypass | 设置系统代理 |
| `clear_proxy` | - | 清除系统代理 |
| `install_tap` | driver_path | 安装 TAP 驱动 |
| `get_status` | - | 获取所有服务状态 |

## 安装/卸载

### 安装服务
```batch
sc create ov2n-service binPath= "C:\Program Files\ov2n\vpn-helper-service.exe" ^
    DisplayName= "Ov2n VPN Helper Service" ^
    start= demand ^
    obj= LocalSystem
sc description ov2n-service "Ov2n VPN 客户端辅助服务，用于管理 VPN 连接和代理设置"
```

### 启动服务
```batch
sc start ov2n-service
```

### 停止并卸载
```batch
sc stop ov2n-service
sc delete ov2n-service
```

## 开发计划

1. [ ] 实现 vpn-helper-service.exe (Python + pywin32 或 Go)
2. [ ] 实现命名管道 JSON-RPC 服务端
3. [ ] 实现 GUI 端命名管道客户端
4. [ ] TAP 驱动自动检测和安装
5. [ ] 系统代理设置 (netsh + 注册表)
6. [ ] 安装包集成 (NSIS/Inno Setup)
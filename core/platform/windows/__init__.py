"""
Windows 平台实现包。

当前状态：架构骨架（stub），所有方法抛出 NotImplementedError。
后续逐步填充具体实现。

Windows 适配要点：
- 权限提升: UAC (runas) + Windows Service 注册
- 代理: netsh 系统代理 / v2rayN 集成（放弃 TProxy）
- 进程管理: taskkill / TerminateProcess
- TAP 驱动: 安装 tap-windows 驱动
- 图标: Qt 原生支持，无需 X11 hack
"""
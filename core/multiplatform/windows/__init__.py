"""
Windows 平台实现模块。

提供以下组件：
- WindowsPaths: 路径常量
- WindowsPrivilegeHandler: 权限提升（UAC + NSSM 服务注册）
- WindowsProcessManager: 进程管理（taskkill/tasklist）
- WindowsProxyManager: 代理管理（Xray TUN 透明代理）
- WindowsIconHandler: 图标处理
- WindowsShellHelper: Shell 辅助工具
"""

from core.multiplatform.windows.paths import WindowsPaths
from core.multiplatform.windows.privilege import WindowsPrivilegeHandler
from core.multiplatform.windows.process_manager import WindowsProcessManager
from core.multiplatform.windows.proxy import WindowsProxyManager
from core.multiplatform.windows.icon import WindowsIconHandler
from core.multiplatform.windows.shell_helper import WindowsShellHelper

__all__ = [
    "WindowsPaths",
    "WindowsPrivilegeHandler",
    "WindowsProcessManager",
    "WindowsProxyManager",
    "WindowsIconHandler",
    "WindowsShellHelper",
]
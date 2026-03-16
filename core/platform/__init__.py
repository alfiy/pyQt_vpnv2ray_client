"""
平台抽象层
根据运行时操作系统自动选择对应的平台实现。

使用方式:
    from core.platform import get_privilege_handler, get_process_manager, \
                              get_proxy_manager, get_icon_handler, get_shell_helper

每个 get_xxx() 返回对应平台的具体实现实例，均遵循 base.py 中定义的抽象接口。
"""
import sys

_current_platform: str = ""


def detect_platform() -> str:
    """检测当前操作系统平台。"""
    global _current_platform
    if _current_platform:
        return _current_platform
    if sys.platform.startswith("win"):
        _current_platform = "windows"
    elif sys.platform.startswith("linux"):
        _current_platform = "linux"
    elif sys.platform.startswith("darwin"):
        _current_platform = "darwin"
    else:
        _current_platform = "unknown"
    return _current_platform


def is_windows() -> bool:
    return detect_platform() == "windows"


def is_linux() -> bool:
    return detect_platform() == "linux"


def get_privilege_handler():
    """获取当前平台的权限提升处理器。"""
    from core.platform.base import PrivilegeHandler
    if is_windows():
        from core.platform.windows.privilege import WindowsPrivilegeHandler
        return WindowsPrivilegeHandler()
    else:
        from core.platform.linux.privilege import LinuxPrivilegeHandler
        return LinuxPrivilegeHandler()


def get_process_manager():
    """获取当前平台的进程管理器。"""
    from core.platform.base import ProcessManager
    if is_windows():
        from core.platform.windows.process_manager import WindowsProcessManager
        return WindowsProcessManager()
    else:
        from core.platform.linux.process_manager import LinuxProcessManager
        return LinuxProcessManager()


def get_proxy_manager():
    """获取当前平台的代理管理器。"""
    from core.platform.base import ProxyManager
    if is_windows():
        from core.platform.windows.proxy import WindowsProxyManager
        return WindowsProxyManager()
    else:
        from core.platform.linux.proxy import LinuxProxyManager
        return LinuxProxyManager()


def get_icon_handler():
    """获取当前平台的图标处理器。"""
    from core.platform.base import IconHandler
    if is_windows():
        from core.platform.windows.icon import WindowsIconHandler
        return WindowsIconHandler()
    else:
        from core.platform.linux.icon import LinuxIconHandler
        return LinuxIconHandler()


def get_shell_helper():
    """获取当前平台的 Shell 辅助工具。"""
    from core.platform.base import ShellHelper
    if is_windows():
        from core.platform.windows.shell_helper import WindowsShellHelper
        return WindowsShellHelper()
    else:
        from core.platform.linux.shell_helper import LinuxShellHelper
        return LinuxShellHelper()


def get_paths():
    """获取当前平台的路径常量。"""
    if is_windows():
        from core.platform.windows.paths import WindowsPaths
        return WindowsPaths()
    else:
        from core.platform.linux.paths import LinuxPaths
        return LinuxPaths()
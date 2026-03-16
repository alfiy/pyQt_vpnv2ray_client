"""
平台抽象基类
定义所有平台相关操作的统一接口。
Linux 和 Windows 的具体实现必须继承并实现这些抽象方法。
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple

from PyQt5.QtGui import QIcon


class PlatformPaths(ABC):
    """平台相关路径常量的抽象基类。"""

    @property
    @abstractmethod
    def config_dir(self) -> str:
        """用户配置目录路径 (如 ~/.config/ov2n 或 %APPDATA%/ov2n)。"""
        ...

    @property
    @abstractmethod
    def log_dir(self) -> str:
        """日志文件目录路径。"""
        ...

    @property
    @abstractmethod
    def helper_script(self) -> str:
        """权限提升辅助脚本/程序路径。"""
        ...

    @property
    @abstractmethod
    def openvpn_log(self) -> str:
        """OpenVPN 日志文件路径。"""
        ...

    @property
    @abstractmethod
    def v2ray_log(self) -> str:
        """V2Ray 日志文件路径。"""
        ...

    @property
    @abstractmethod
    def tap_driver_dir(self) -> str:
        """TAP 驱动目录路径（仅 Windows 有效，Linux 返回空字符串）。"""
        ...

    @property
    @abstractmethod
    def system_icon_paths(self) -> list:
        """系统图标搜索路径列表。"""
        ...


class PrivilegeHandler(ABC):
    """
    权限提升抽象基类。
    Linux: 通过 pkexec (polkit) 实现
    Windows: 通过 UAC (runas) 或 Windows 服务实现
    """

    @abstractmethod
    def check_available(self) -> bool:
        """检查权限提升机制是否可用。"""
        ...

    @abstractmethod
    def check_helper_installed(self) -> bool:
        """检查辅助脚本/服务是否已安装。"""
        ...

    @abstractmethod
    def run_privileged(self, cmd: list, timeout: int = 60) -> Tuple[int, str, str]:
        """
        以提升的权限执行命令。

        Args:
            cmd: 要执行的命令列表
            timeout: 超时时间（秒）

        Returns:
            (returncode, stdout, stderr) 三元组
        """
        ...

    @abstractmethod
    def start_vpn(self, vpn_config_path: str, v2ray_config_path: str
                   ) -> Tuple[bool, str, Dict]:
        """
        启动 VPN 和 V2Ray。

        Returns:
            (success, message, pids_dict)
        """
        ...

    @abstractmethod
    def stop_vpn(self, pids: Dict) -> Tuple[bool, str]:
        """
        停止 VPN 进程。

        Args:
            pids: 进程 ID 字典，如 {'openvpn': pid, 'v2ray': pid}

        Returns:
            (success, message)
        """
        ...

    @abstractmethod
    def install_service(self) -> Tuple[bool, str]:
        """
        安装系统服务（Windows: 注册 Windows Service 以避免频繁 UAC 弹窗）。
        Linux 实现可返回 (True, "不需要安装服务")。

        Returns:
            (success, message)
        """
        ...

    @abstractmethod
    def uninstall_service(self) -> Tuple[bool, str]:
        """
        卸载系统服务。

        Returns:
            (success, message)
        """
        ...


class ProcessManager(ABC):
    """
    进程管理抽象基类。
    封装进程启动、停止、查询等操作的平台差异。
    """

    @abstractmethod
    def start_process(self, cmd: list, log_file: Optional[str] = None,
                      daemon: bool = True) -> Optional[int]:
        """
        启动进程。

        Args:
            cmd: 命令列表
            log_file: 日志文件路径（可选）
            daemon: 是否以守护进程方式启动

        Returns:
            进程 PID，失败返回 None
        """
        ...

    @abstractmethod
    def stop_process(self, pid: int) -> bool:
        """
        停止指定 PID 的进程。

        Args:
            pid: 进程 ID

        Returns:
            是否成功停止
        """
        ...

    @abstractmethod
    def is_process_alive(self, pid: int) -> bool:
        """检查进程是否仍在运行。"""
        ...

    @abstractmethod
    def find_process_by_name(self, name: str) -> Optional[int]:
        """
        按名称查找进程。

        Args:
            name: 进程名称或匹配模式

        Returns:
            进程 PID，未找到返回 None
        """
        ...


class ProxyManager(ABC):
    """
    代理管理抽象基类。
    Linux: TProxy (iptables/ip rule) 透明代理
    Windows: 系统代理 (netsh) 或第三方工具 (v2rayN) 集成
    """

    @abstractmethod
    def get_proxy_type(self) -> str:
        """
        获取当前平台支持的代理类型。

        Returns:
            "tproxy" (Linux) 或 "system_proxy" (Windows)
        """
        ...

    @abstractmethod
    def start_proxy(self, **kwargs) -> Tuple[bool, str]:
        """
        启动/配置代理。

        Linux kwargs: v2ray_port, vps_ip, mark, table
        Windows kwargs: socks_port, http_port, bypass_list

        Returns:
            (success, message)
        """
        ...

    @abstractmethod
    def stop_proxy(self, **kwargs) -> Tuple[bool, str]:
        """
        停止/清理代理配置。

        Returns:
            (success, message)
        """
        ...

    @abstractmethod
    def get_proxy_status(self) -> Dict:
        """
        获取当前代理状态。

        Returns:
            包含代理状态信息的字典
        """
        ...


class IconHandler(ABC):
    """
    图标处理抽象基类。
    Linux: 需要 X11/Xlib 兼容层处理标题栏图标
    Windows: Qt 原生图标支持即可
    """

    @abstractmethod
    def load_window_icon(self, app_root: str) -> QIcon:
        """
        加载窗口图标。

        Args:
            app_root: 应用根目录路径

        Returns:
            QIcon 实例
        """
        ...

    @abstractmethod
    def apply_window_icon(self, window) -> None:
        """
        将图标应用到窗口（处理平台特定的图标显示问题）。

        Args:
            window: QMainWindow 实例
        """
        ...

    @abstractmethod
    def cleanup_icons(self) -> None:
        """清理历史遗留的错误图标文件（仅 Linux 需要）。"""
        ...


class ShellHelper(ABC):
    """
    Shell/系统操作辅助抽象基类。
    封装打开文件、打开 URL 等平台差异操作。
    """

    @abstractmethod
    def open_file_with_default_app(self, filepath: str) -> bool:
        """
        使用系统默认应用打开文件。
        Linux: xdg-open
        Windows: os.startfile 或 start

        Args:
            filepath: 文件路径

        Returns:
            是否成功打开
        """
        ...

    @abstractmethod
    def open_url(self, url: str) -> bool:
        """
        使用系统默认浏览器打开 URL。

        Args:
            url: 要打开的 URL

        Returns:
            是否成功打开
        """
        ...

    @abstractmethod
    def check_command_exists(self, command: str) -> bool:
        """
        检查系统命令是否存在。
        Linux: which
        Windows: where

        Args:
            command: 命令名称

        Returns:
            命令是否存在
        """
        ...

    @abstractmethod
    def get_temp_dir(self) -> str:
        """获取系统临时目录路径。"""
        ...
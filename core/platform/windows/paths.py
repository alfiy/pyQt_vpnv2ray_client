"""
Windows 平台路径常量。

TODO: 后续填充具体实现。
"""
import os
import sys

from core.platform.base import PlatformPaths


class WindowsPaths(PlatformPaths):
    """Windows 平台路径实现。"""

    @property
    def config_dir(self) -> str:
        """使用 %APPDATA%/ov2n 作为配置目录。"""
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(appdata, "ov2n")

    @property
    def log_dir(self) -> str:
        """日志存放在配置目录下的 logs 子目录。"""
        return os.path.join(self.config_dir, "logs")

    @property
    def helper_script(self) -> str:
        """
        Windows 辅助程序路径。
        TODO: 实现为 Windows Service 可执行文件路径。
        """
        if getattr(sys, 'frozen', False):
            return os.path.join(os.path.dirname(sys.executable),
                                "vpn-helper-service.exe")
        return os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))),
            "service", "vpn-helper-service.exe")

    @property
    def openvpn_log(self) -> str:
        return os.path.join(self.log_dir, "openvpn.log")

    @property
    def v2ray_log(self) -> str:
        return os.path.join(self.log_dir, "v2ray.log")

    @property
    def tap_driver_dir(self) -> str:
        """TAP-Windows 驱动目录，位于 resources/tap-windows 下。"""
        if getattr(sys, 'frozen', False):
            app_root = os.path.dirname(sys.executable)
        else:
            app_root = os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(app_root, "resources", "tap-windows")

    @property
    def system_icon_paths(self) -> list:
        """Windows 不需要系统图标路径，使用应用内嵌图标。"""
        return []
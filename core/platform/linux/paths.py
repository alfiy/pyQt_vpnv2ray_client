"""
Linux 平台路径常量。
将原来散落在各模块中的 Linux 路径集中定义。
"""
import os

from core.platform.base import PlatformPaths


class LinuxPaths(PlatformPaths):
    """Linux 平台路径实现。"""

    @property
    def config_dir(self) -> str:
        return os.path.expanduser("~/.config/ov2n")

    @property
    def log_dir(self) -> str:
        return "/tmp"

    @property
    def helper_script(self) -> str:
        return "/usr/local/bin/vpn-helper.py"

    @property
    def openvpn_log(self) -> str:
        return "/tmp/openvpn.log"

    @property
    def v2ray_log(self) -> str:
        return "/tmp/v2ray.log"

    @property
    def tap_driver_dir(self) -> str:
        return ""  # Linux 不需要 TAP 驱动

    @property
    def system_icon_paths(self) -> list:
        return [
            "/usr/share/icons/hicolor/256x256/apps/ov2n.png",
            "/usr/share/icons/hicolor/128x128/apps/ov2n.png",
            "/usr/share/icons/hicolor/64x64/apps/ov2n.png",
            "/usr/share/icons/hicolor/48x48/apps/ov2n.png",
            "/usr/share/icons/hicolor/22x22/apps/ov2n.png",
            "/usr/share/pixmaps/ov2n256.png",
            "/usr/share/pixmaps/ov2n.png",
        ]
"""
Windows 平台路径常量。
"""
import os
import sys

from core.platform.base import PlatformPaths


def _app_root() -> str:
    """获取应用根目录。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    # 开发模式: core/platform/windows/paths.py -> 项目根目录
    return os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class WindowsPaths(PlatformPaths):
    """Windows 平台路径实现。"""

    def __init__(self):
        self._root = _app_root()

    @property
    def app_root(self) -> str:
        return self._root

    @property
    def config_dir(self) -> str:
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(appdata, "ov2n")

    @property
    def log_dir(self) -> str:
        return os.path.join(self._root, "logs")

    @property
    def helper_script(self) -> str:
        """Windows 下无 polkit helper，返回空。"""
        return ""

    @property
    def openvpn_log(self) -> str:
        return os.path.join(self.log_dir, "openvpn.log")

    @property
    def v2ray_log(self) -> str:
        return os.path.join(self.log_dir, "xray.log")

    @property
    def tap_driver_dir(self) -> str:
        return os.path.join(self._root, "resources", "tap-windows")

    @property
    def system_icon_paths(self) -> list:
        return []

    # ---- Windows 专有路径 ----

    @property
    def xray_exe(self) -> str:
        return os.path.join(self._root, "resources", "xray", "xray.exe")

    @property
    def xray_dir(self) -> str:
        return os.path.join(self._root, "resources", "xray")

    @property
    def xray_config(self) -> str:
        return os.path.join(self._root, "resources", "xray", "config.json")

    @property
    def xray_runtime_config(self) -> str:
        return os.path.join(self._root, "resources", "xray", "config.runtime.json")

    @property
    def openvpn_exe(self) -> str:
        return os.path.join(self._root, "resources", "openvpn", "bin", "openvpn.exe")

    @property
    def openvpn_dir(self) -> str:
        return os.path.join(self._root, "resources", "openvpn")

    @property
    def nssm_exe(self) -> str:
        return os.path.join(self._root, "resources", "nssm", "nssm.exe")

    @property
    def wintun_dll(self) -> str:
        return os.path.join(self._root, "resources", "xray", "wintun.dll")

    @property
    def scripts_dir(self) -> str:
        return os.path.join(self._root, "scripts")
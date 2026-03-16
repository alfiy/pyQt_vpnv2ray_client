"""
Windows 代理管理实现（骨架）。

Windows 版本放弃 TProxy，改用以下方案：
1. 系统代理 (netsh): 设置 HTTP/SOCKS 系统代理
2. 第三方工具集成 (v2rayN): 检测并调用 v2rayN 的代理设置

TODO: 后续逐步填充具体实现。
"""
from typing import Dict, Tuple

from core.platform.base import ProxyManager


class WindowsProxyManager(ProxyManager):
    """
    Windows 代理管理器。

    代理模式：
    1. 系统代理模式 (netsh):
       - 设置 IE/系统级 HTTP 代理
       - 通过注册表 HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings
       - 或 netsh winhttp set proxy proxy-server="socks=127.0.0.1:1080"

    2. v2rayN 集成模式:
       - 检测 v2rayN 是否安装
       - 通过 v2rayN 的 API 或配置文件设置代理

    注意：Windows 版本不支持 TProxy 透明代理。
    """

    def get_proxy_type(self) -> str:
        return "system_proxy"

    def start_proxy(self, **kwargs) -> Tuple[bool, str]:
        """
        设置系统代理。

        kwargs:
            socks_port (int): SOCKS5 代理端口，默认 1080
            http_port (int): HTTP 代理端口，默认 1081
            bypass_list (str): 代理绕过列表，默认 "localhost;127.*;10.*;172.16.*"

        实现步骤：
        1. 通过注册表设置系统代理:
           reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings"
               /v ProxyEnable /t REG_DWORD /d 1 /f
           reg add "..." /v ProxyServer /t REG_SZ /d "socks=127.0.0.1:1080" /f
           reg add "..." /v ProxyOverride /t REG_SZ /d "localhost;127.*" /f

        2. 或使用 netsh:
           netsh winhttp set proxy proxy-server="socks=127.0.0.1:1080"
               bypass-list="localhost;127.*"

        TODO: 实现具体逻辑。
        """
        raise NotImplementedError(
            "Windows 系统代理设置尚未实现。\n"
            "计划: netsh winhttp + 注册表设置")

    def stop_proxy(self, **kwargs) -> Tuple[bool, str]:
        """
        清除系统代理设置。

        实现步骤：
        1. reg add "..." /v ProxyEnable /t REG_DWORD /d 0 /f
        2. 或 netsh winhttp reset proxy

        TODO: 实现具体逻辑。
        """
        raise NotImplementedError("Windows 系统代理清除尚未实现")

    def get_proxy_status(self) -> Dict:
        """
        获取当前系统代理状态。

        实现：读取注册表 ProxyEnable 和 ProxyServer 值。

        TODO: 实现具体逻辑。
        """
        return {
            "type": "system_proxy",
            "active": False,
            "description": "Windows 系统代理 (netsh/注册表)",
            "note": "不支持 TProxy 透明代理",
        }
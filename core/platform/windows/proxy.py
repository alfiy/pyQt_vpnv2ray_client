"""
Windows 代理管理实现。

Windows 版使用 Xray TUN 模式实现透明代理（增强版），
不再使用 netsh 系统代理。TUN 模式通过虚拟网卡接管全部流量。
"""
import json
import os
import re
import subprocess
import time
from typing import Dict, Tuple

from core.platform.base import ProxyManager


CREATE_NO_WINDOW = 0x08000000


class WindowsProxyManager(ProxyManager):
    """
    Windows 代理管理器 - Xray TUN 模式。

    工作原理：
    1. xray 创建 xray-tun 虚拟网卡
    2. 添加路由规则将流量导向 TUN
    3. VPS 流量走物理网卡直连（避免回环）
    """

    def __init__(self):
        from core.platform.windows.paths import WindowsPaths
        self._paths = WindowsPaths()

    def get_proxy_type(self) -> str:
        return "tun"

    def start_proxy(self, **kwargs) -> Tuple[bool, str]:
        """
        配置 TUN 路由。xray 进程应已启动并创建了 xray-tun 网卡。

        kwargs:
            vps_ip (str): VPS 服务器 IP
            wait_tun (int): 等待 TUN 网卡出现的秒数，默认 20
        """
        vps_ip = kwargs.get("vps_ip", "")
        wait_seconds = kwargs.get("wait_tun", 20)

        if not vps_ip:
            # 尝试从配置文件读取
            vps_ip = self._get_vps_ip_from_config()
            if not vps_ip:
                return False, "无法获取 VPS 地址"

        # 获取物理网卡信息
        gw_info = self._get_default_gateway()
        if not gw_info:
            return False, "找不到默认网关"

        gateway = gw_info["gateway"]
        real_idx = gw_info["if_index"]

        # 等待 xray-tun 网卡出现
        tun_idx = self._wait_for_tun(wait_seconds)
        if not tun_idx:
            return False, f"xray-tun 网卡未出现（等待 {wait_seconds}s）"

        # 配置 IP
        self._run_cmd(["netsh", "interface", "ip", "set", "address",
                       "name=xray-tun", "static", "10.0.0.1", "255.255.255.0"])
        time.sleep(1)

        # 重新获取 TUN 索引（可能变化）
        tun_idx = self._get_adapter_index("xray-tun") or tun_idx

        # 清理旧路由
        for dest in ["0.0.0.0 mask 0.0.0.0 10.0.0.0",
                      "0.0.0.0 mask 0.0.0.0 10.0.0.1", vps_ip]:
            self._run_cmd(["route", "delete"] + dest.split())

        # 添加路由
        self._run_cmd(["route", "add", vps_ip, "mask", "255.255.255.255",
                       gateway, "metric", "1", "if", str(real_idx)])
        self._run_cmd(["route", "add", gateway, "mask", "255.255.255.255",
                       gateway, "metric", "1", "if", str(real_idx)])
        self._run_cmd(["route", "add", "0.0.0.0", "mask", "0.0.0.0",
                       "10.0.0.0", "metric", "5", "if", str(tun_idx)])

        # 设置 DNS
        self._run_cmd(["netsh", "interface", "ip", "set", "dns",
                       f"name={gw_info['alias']}", "static", "114.114.114.114"])
        self._run_cmd(["netsh", "interface", "ip", "add", "dns",
                       f"name={gw_info['alias']}", "8.8.8.8", "index=2"])
        self._run_cmd(["ipconfig", "/flushdns"])

        return True, (f"TUN 代理已配置 (VPS={vps_ip}, "
                       f"网关={gateway}, TUN索引={tun_idx})")

    def stop_proxy(self, **kwargs) -> Tuple[bool, str]:
        """清理 TUN 路由和 DNS 设置。"""
        vps_ip = kwargs.get("vps_ip", "")
        if not vps_ip:
            vps_ip = self._get_vps_ip_from_config()

        # 清理路由
        for dest in ["0.0.0.0 mask 0.0.0.0 10.0.0.0",
                      "0.0.0.0 mask 0.0.0.0 10.0.0.1"]:
            self._run_cmd(["route", "delete"] + dest.split())
        if vps_ip:
            self._run_cmd(["route", "delete", vps_ip])

        # 恢复 DNS 为 DHCP
        gw_info = self._get_default_gateway()
        if gw_info:
            self._run_cmd(["netsh", "interface", "ip", "set", "dns",
                           f"name={gw_info['alias']}", "dhcp"])

        self._run_cmd(["ipconfig", "/flushdns"])
        return True, "TUN 代理已清理"

    def get_proxy_status(self) -> Dict:
        """获取当前 TUN 代理状态。"""
        tun_idx = self._get_adapter_index("xray-tun")
        xray_running = self._is_xray_running()
        return {
            "type": "tun",
            "active": bool(tun_idx and xray_running),
            "tun_adapter": "xray-tun" if tun_idx else None,
            "tun_index": tun_idx,
            "xray_running": xray_running,
            "description": "Xray TUN 透明代理",
        }

    # ---- 内部方法 ----

    def _run_cmd(self, cmd: list) -> Tuple[int, str]:
        """执行系统命令，忽略错误。"""
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               creationflags=CREATE_NO_WINDOW)
            return r.returncode, r.stdout
        except Exception:
            return -1, ""

    def _get_default_gateway(self) -> dict:
        """
        获取默认网关、物理网卡索引和别名。
        使用 PowerShell Get-NetRoute 命令。
        """
        try:
            ps_cmd = (
                'Get-NetRoute -DestinationPrefix "0.0.0.0/0" | '
                'Where-Object { $_.NextHop -ne "0.0.0.0" -and '
                '$_.InterfaceAlias -ne "xray-tun" } | '
                'Sort-Object RouteMetric | Select-Object -First 1 | '
                'ConvertTo-Json'
            )
            r = subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True, text=True, creationflags=CREATE_NO_WINDOW,
            )
            if r.returncode != 0 or not r.stdout.strip():
                return {}

            data = json.loads(r.stdout)
            if_index = data.get("InterfaceIndex", 0)

            # 获取网卡别名
            ps_alias = (
                f'(Get-NetAdapter -InterfaceIndex {if_index}).Name'
            )
            r2 = subprocess.run(
                ["powershell", "-Command", ps_alias],
                capture_output=True, text=True, creationflags=CREATE_NO_WINDOW,
            )
            alias = r2.stdout.strip() if r2.returncode == 0 else ""

            return {
                "gateway": data.get("NextHop", ""),
                "if_index": if_index,
                "alias": alias,
            }
        except Exception:
            return {}

    def _get_adapter_index(self, name: str) -> int:
        """获取指定名称网卡的接口索引。"""
        try:
            ps_cmd = f'(Get-NetAdapter -Name "{name}" -ErrorAction SilentlyContinue).InterfaceIndex'
            r = subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True, text=True, creationflags=CREATE_NO_WINDOW,
            )
            if r.returncode == 0 and r.stdout.strip():
                return int(r.stdout.strip())
        except Exception:
            pass
        return 0

    def _wait_for_tun(self, max_seconds: int = 20) -> int:
        """等待 xray-tun 网卡出现，返回接口索引。"""
        for i in range(max_seconds):
            idx = self._get_adapter_index("xray-tun")
            if idx:
                return idx
            time.sleep(1)
        return 0

    def _get_vps_ip_from_config(self) -> str:
        """从 xray config.json 中提取 VPS 地址。"""
        try:
            config_path = self._paths.xray_config
            if not os.path.isfile(config_path):
                return ""
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
            content = re.sub(r'(?m)^\s*//.*$', '', content)
            config = json.loads(content)
            for ob in config.get("outbounds", []):
                if ob.get("tag") == "proxy":
                    servers = ob.get("settings", {}).get("servers", [])
                    if servers:
                        return servers[0].get("address", "")
        except Exception:
            pass
        return ""

    def _is_xray_running(self) -> bool:
        """检查 xray 进程是否在运行。"""
        from core.platform.windows.process_manager import WindowsProcessManager
        pm = WindowsProcessManager()
        return pm.find_process_by_name("xray.exe") is not None
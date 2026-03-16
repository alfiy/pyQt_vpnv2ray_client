"""
Linux 代理管理实现。
使用 iptables + ip rule 实现 TProxy 透明代理。
实际的 iptables 操作委托给 vpn-helper.py 脚本（需要 root 权限）。
"""
from typing import Dict, Tuple

from core.platform.base import ProxyManager


class LinuxProxyManager(ProxyManager):
    """Linux TProxy 透明代理管理器。"""

    def get_proxy_type(self) -> str:
        return "tproxy"

    def start_proxy(self, **kwargs) -> Tuple[bool, str]:
        """
        启动 TProxy 透明代理。

        kwargs:
            v2ray_port (int): V2Ray TPROXY 监听端口
            vps_ip (str): VPS 服务器 IP
            mark (int): fwmark 值，默认 1
            table (int): 路由表编号，默认 100
        """
        # 延迟导入，避免循环依赖
        from core.platform.linux.privilege import LinuxPrivilegeHandler

        handler = LinuxPrivilegeHandler()
        if not handler.check_available():
            return False, "系统未安装 pkexec (polkit)"
        if not handler.check_helper_installed():
            return False, f"Helper 脚本未安装: {handler.helper_script}"

        v2ray_port = kwargs.get("v2ray_port", 12345)
        vps_ip = kwargs.get("vps_ip", "")
        mark = kwargs.get("mark", 1)
        table = kwargs.get("table", 100)

        cmd = [
            handler.helper_script, "tproxy-start",
            "--port", str(v2ray_port),
            "--vps-ip", str(vps_ip),
            "--mark", str(mark),
            "--table", str(table),
        ]

        rc, stdout, stderr = handler.run_privileged(cmd, timeout=30)
        if rc == 0:
            return True, "透明代理规则已配置"
        else:
            error_msg = stderr.strip() if stderr else "未知错误"
            if "dismissed" in error_msg.lower() or "cancelled" in error_msg.lower():
                return False, "用户取消了权限授权"
            return False, f"配置透明代理失败:\n{error_msg}"

    def stop_proxy(self, **kwargs) -> Tuple[bool, str]:
        """
        停止 TProxy 透明代理。

        kwargs: 同 start_proxy
        """
        from core.platform.linux.privilege import LinuxPrivilegeHandler

        handler = LinuxPrivilegeHandler()
        if not handler.check_available():
            return False, "系统未安装 pkexec (polkit)"
        if not handler.check_helper_installed():
            return False, f"Helper 脚本未安装: {handler.helper_script}"

        v2ray_port = kwargs.get("v2ray_port", 12345)
        vps_ip = kwargs.get("vps_ip", "0.0.0.0")
        mark = kwargs.get("mark", 1)
        table = kwargs.get("table", 100)

        cmd = [
            handler.helper_script, "tproxy-stop",
            "--port", str(v2ray_port),
            "--vps-ip", str(vps_ip),
            "--mark", str(mark),
            "--table", str(table),
        ]

        rc, stdout, stderr = handler.run_privileged(cmd, timeout=30)
        if rc == 0:
            return True, "透明代理规则已清理"
        else:
            error_msg = stderr.strip() if stderr else "未知错误"
            if "dismissed" in error_msg.lower() or "cancelled" in error_msg.lower():
                return False, "用户取消了权限授权"
            return False, f"清理透明代理失败:\n{error_msg}"

    def get_proxy_status(self) -> Dict:
        """获取 TProxy 代理状态。"""
        return {
            "type": "tproxy",
            "active": False,  # 需要检查 iptables 规则，此处为默认值
            "description": "Linux TProxy 透明代理 (iptables + ip rule)",
        }
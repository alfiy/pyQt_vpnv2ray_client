"""
Linux 权限提升实现。
封装现有的 polkit/pkexec 逻辑，实现 PrivilegeHandler 接口。
"""
import os
import subprocess
from typing import Dict, Tuple

from core.platform.base import PrivilegeHandler
from core.platform.linux.paths import LinuxPaths


class LinuxPrivilegeHandler(PrivilegeHandler):
    """通过 pkexec (polkit) 实现的 Linux 权限提升。"""

    def __init__(self):
        self._paths = LinuxPaths()

    @property
    def helper_script(self) -> str:
        return self._paths.helper_script

    def check_available(self) -> bool:
        """检查 polkit (pkexec) 是否可用。"""
        try:
            result = subprocess.run(
                ["which", "pkexec"],
                capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except Exception as e:
            print(f"检查 polkit 失败: {e}")
            return False

    def check_helper_installed(self) -> bool:
        """检查 helper 脚本是否已安装且可执行。"""
        return (os.path.exists(self.helper_script)
                and os.access(self.helper_script, os.X_OK))

    def run_privileged(self, cmd: list, timeout: int = 60) -> Tuple[int, str, str]:
        """通过 pkexec 以 root 权限执行命令。"""
        full_cmd = ["pkexec"] + cmd
        try:
            result = subprocess.run(
                full_cmd, capture_output=True, text=True, timeout=timeout)
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "操作超时"
        except Exception as e:
            return -1, "", str(e)

    def start_vpn(self, vpn_config_path: str, v2ray_config_path: str
                   ) -> Tuple[bool, str, Dict]:
        """使用 pkexec 启动 VPN 和 V2Ray。"""
        if not self.check_available():
            return False, "系统未安装 pkexec (polkit),无法执行权限提升操作", {}
        if not self.check_helper_installed():
            return (False,
                    f"Helper 脚本未安装或无执行权限:\n{self.helper_script}\n\n"
                    "请参考 README.md 完成安装", {})
        if not os.path.exists(vpn_config_path):
            return False, f"OpenVPN 配置文件不存在: {vpn_config_path}", {}
        if not os.path.exists(v2ray_config_path):
            return False, f"V2Ray 配置文件不存在: {v2ray_config_path}", {}

        try:
            cmd = [self.helper_script, "start",
                   vpn_config_path, v2ray_config_path]
            rc, stdout, stderr = self.run_privileged(cmd, timeout=60)

            if rc == 0:
                pids = {}
                for line in stdout.split('\n'):
                    if 'OpenVPN PID:' in line:
                        pids['openvpn'] = int(line.split(':')[1].strip())
                    elif 'V2Ray PID:' in line:
                        pids['v2ray'] = int(line.split(':')[1].strip())
                return True, "VPN 启动成功", pids
            else:
                error_msg = stderr.strip() if stderr else "未知错误"
                if "dismissed" in error_msg.lower() or "cancelled" in error_msg.lower():
                    return False, "用户取消了权限授权", {}
                elif "authentication" in error_msg.lower():
                    return False, "密码验证失败,请重试", {}
                else:
                    return False, f"启动失败:\n{error_msg}", {}

        except Exception as e:
            return False, f"执行失败: {str(e)}", {}

    def stop_vpn(self, pids: Dict) -> Tuple[bool, str]:
        """使用 pkexec 停止 VPN 进程。"""
        if not pids:
            return True, "没有运行中的进程"
        try:
            cmd = [self.helper_script, "stop"]
            if 'openvpn' in pids:
                cmd.extend(["--openvpn-pid", str(pids['openvpn'])])
            if 'v2ray' in pids:
                cmd.extend(["--v2ray-pid", str(pids['v2ray'])])

            rc, stdout, stderr = self.run_privileged(cmd, timeout=30)
            if rc == 0:
                return True, "VPN 已停止"
            else:
                return False, f"停止失败: {stderr}"
        except Exception as e:
            return False, f"停止失败: {str(e)}"

    def install_service(self) -> Tuple[bool, str]:
        """Linux 不需要安装服务（使用 polkit 即可）。"""
        return True, "Linux 平台使用 polkit，无需安装服务"

    def uninstall_service(self) -> Tuple[bool, str]:
        """Linux 不需要卸载服务。"""
        return True, "Linux 平台无服务需要卸载"
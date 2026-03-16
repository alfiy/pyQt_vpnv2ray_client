"""
后台工作线程模块
包含所有 VPN/V2Ray 启停操作的 QThread 子类：
- SingleVPNThread: 独立启动 OpenVPN
- SingleV2RayThread: 独立启动 V2Ray（可选 TProxy）
- CombinedStartThread: 联合启动 OpenVPN + V2Ray + TProxy
"""
import subprocess
import time

from PyQt5.QtCore import QThread, pyqtSignal

from core.polkit_helper import PolkitHelper


# ============================================
# 公共辅助函数
# ============================================

def parse_pid_from_output(stdout: str, keyword: str) -> int | None:
    """
    从 helper 脚本的 stdout 中解析 PID。

    Args:
        stdout: 命令标准输出
        keyword: PID 标识关键字，如 'OpenVPN PID' 或 'V2Ray PID'

    Returns:
        解析到的 PID 整数，未找到返回 None。
    """
    for line in stdout.split('\n'):
        if keyword in line:
            try:
                return int(line.split(':')[1].strip())
            except (IndexError, ValueError):
                continue
    return None


def format_process_error(result: subprocess.CompletedProcess,
                         fallback_log: str) -> str:
    """
    格式化进程启动失败的错误信息。

    Args:
        result: subprocess.run 的返回结果
        fallback_log: 建议查看的日志文件路径

    Returns:
        格式化后的错误详情字符串。
    """
    err = result.stderr.strip() if result.stderr else ""
    out = result.stdout.strip() if result.stdout else ""
    detail = ""
    if err:
        detail += f"stderr:\n{err}\n"
    if out:
        detail += f"stdout:\n{out}\n"
    return detail or f"无详细输出，请查看: {fallback_log}"


def check_user_cancelled(stderr: str) -> bool:
    """检查是否为用户取消授权。"""
    lower = stderr.lower() if stderr else ""
    return "dismissed" in lower or "cancelled" in lower


# ============================================
# 独立启动 OpenVPN 线程
# ============================================

class SingleVPNThread(QThread):
    """在后台线程中启动 OpenVPN。"""

    update_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    success_signal = pyqtSignal(int)  # VPN PID

    def __init__(self, vpn_config_path: str):
        super().__init__()
        self.vpn_config_path = vpn_config_path

    def run(self):
        try:
            self.update_signal.emit("正在启动 OpenVPN...")
            cmd = ["pkexec", PolkitHelper.HELPER_SCRIPT,
                   "start-vpn-only", self.vpn_config_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                pid = parse_pid_from_output(result.stdout, 'OpenVPN PID')
                if pid:
                    self.success_signal.emit(pid)
                else:
                    self.error_signal.emit(
                        "无法获取 OpenVPN PID\n\n日志: cat /tmp/openvpn.log")
            else:
                if check_user_cancelled(result.stderr):
                    self.error_signal.emit("用户取消了权限授权")
                else:
                    detail = format_process_error(result, "cat /tmp/openvpn.log")
                    self.error_signal.emit(
                        f"OpenVPN 启动失败 (退出码 {result.returncode}):\n\n{detail}")

        except subprocess.TimeoutExpired:
            self.error_signal.emit("OpenVPN 启动超时（60s），请检查配置文件是否正确")
        except Exception as e:
            self.error_signal.emit(f"OpenVPN 启动异常: {e}")


# ============================================
# 独立启动 V2Ray 线程
# ============================================

class SingleV2RayThread(QThread):
    """在后台线程中启动 V2Ray，可选配置 TProxy。"""

    update_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    success_signal = pyqtSignal(dict)  # {'pid': int, 'tproxy_ok': bool}

    def __init__(self, v2ray_config_path: str, tproxy_enabled: bool = False,
                 tproxy_port: int = 12345, tproxy_vps_ip: str = "",
                 tproxy_mark: int = 1, tproxy_table: int = 100):
        super().__init__()
        self.v2ray_config_path = v2ray_config_path
        self.tproxy_enabled = tproxy_enabled
        self.tproxy_port = tproxy_port
        self.tproxy_vps_ip = tproxy_vps_ip
        self.tproxy_mark = tproxy_mark
        self.tproxy_table = tproxy_table

    def run(self):
        try:
            self.update_signal.emit("正在启动 V2Ray...")
            cmd = ["pkexec", PolkitHelper.HELPER_SCRIPT,
                   "start-v2ray-only", self.v2ray_config_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode != 0:
                if check_user_cancelled(result.stderr):
                    self.error_signal.emit("用户取消了权限授权")
                else:
                    detail = format_process_error(result, "cat /tmp/v2ray.log")
                    self.error_signal.emit(
                        f"V2Ray 启动失败 (退出码 {result.returncode}):\n\n{detail}")
                return

            v2ray_pid = parse_pid_from_output(result.stdout, 'V2Ray PID')
            if not v2ray_pid:
                self.error_signal.emit(
                    "无法获取 V2Ray PID\n\n日志: cat /tmp/v2ray.log")
                return

            tproxy_ok = False
            if self.tproxy_enabled:
                self.update_signal.emit("正在配置透明代理...")
                time.sleep(1)
                ok, msg = PolkitHelper.start_tproxy(
                    self.tproxy_port, self.tproxy_vps_ip,
                    self.tproxy_mark, self.tproxy_table)
                tproxy_ok = ok
                self.update_signal.emit(
                    "✓ 透明代理已配置" if ok else f"⚠ 透明代理配置失败: {msg}")

            self.success_signal.emit({'pid': v2ray_pid, 'tproxy_ok': tproxy_ok})

        except subprocess.TimeoutExpired:
            self.error_signal.emit("V2Ray 启动超时（60s）")
        except Exception as e:
            self.error_signal.emit(f"V2Ray 启动异常: {e}")


# ============================================
# 联合启动线程 (OpenVPN + V2Ray + TProxy)
# ============================================

class CombinedStartThread(QThread):
    """在后台线程中依次启动 OpenVPN 和 V2Ray，可选配置 TProxy。"""

    update_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    success_signal = pyqtSignal(dict)  # {'vpn_pid', 'v2ray_pid', 'tproxy_ok'}

    def __init__(self, vpn_config_path: str, v2ray_config_path: str,
                 current_vpn_pid: int | None, current_v2ray_pid: int | None,
                 tproxy_enabled: bool = False, tproxy_port: int = 12345,
                 tproxy_vps_ip: str = "", tproxy_mark: int = 1,
                 tproxy_table: int = 100):
        super().__init__()
        self.vpn_config_path = vpn_config_path
        self.v2ray_config_path = v2ray_config_path
        self.current_vpn_pid = current_vpn_pid
        self.current_v2ray_pid = current_v2ray_pid
        self.tproxy_enabled = tproxy_enabled
        self.tproxy_port = tproxy_port
        self.tproxy_vps_ip = tproxy_vps_ip
        self.tproxy_mark = tproxy_mark
        self.tproxy_table = tproxy_table

    def run(self):
        try:
            res_vpn_pid = self.current_vpn_pid
            res_v2ray_pid = self.current_v2ray_pid
            tproxy_ok = False

            # 步骤 1: 启动 OpenVPN
            if not self.current_vpn_pid:
                self.update_signal.emit("正在启动 OpenVPN...")
                r = subprocess.run(
                    ["pkexec", PolkitHelper.HELPER_SCRIPT,
                     "start-vpn-only", self.vpn_config_path],
                    capture_output=True, text=True, timeout=60)
                if r.returncode != 0:
                    self.error_signal.emit(
                        f"OpenVPN 启动失败 (退出码 {r.returncode}):\n\n"
                        + format_process_error(r, "cat /tmp/openvpn.log"))
                    return
                res_vpn_pid = parse_pid_from_output(r.stdout, 'OpenVPN PID')
                if not res_vpn_pid:
                    self.error_signal.emit(
                        "无法获取 OpenVPN PID\n\n日志: cat /tmp/openvpn.log")
                    return
            else:
                self.update_signal.emit("OpenVPN 已在运行，跳过启动")

            # 步骤 2: 启动 V2Ray
            if not self.current_v2ray_pid:
                self.update_signal.emit("正在启动 V2Ray...")
                r = subprocess.run(
                    ["pkexec", PolkitHelper.HELPER_SCRIPT,
                     "start-v2ray-only", self.v2ray_config_path],
                    capture_output=True, text=True, timeout=60)
                if r.returncode != 0:
                    self.error_signal.emit(
                        f"V2Ray 启动失败 (退出码 {r.returncode}):\n\n"
                        + format_process_error(r, "cat /tmp/v2ray.log"))
                    # 回滚：如果本次新启动了 VPN，则停止
                    if res_vpn_pid and not self.current_vpn_pid:
                        self._stop_process(res_vpn_pid, "openvpn")
                    return
                res_v2ray_pid = parse_pid_from_output(r.stdout, 'V2Ray PID')
                if not res_v2ray_pid:
                    self.error_signal.emit(
                        "无法获取 V2Ray PID\n\n日志: cat /tmp/v2ray.log")
                    if res_vpn_pid and not self.current_vpn_pid:
                        self._stop_process(res_vpn_pid, "openvpn")
                    return
            else:
                self.update_signal.emit("V2Ray 已在运行，跳过启动")

            # 步骤 3: 配置 TProxy
            if self.tproxy_enabled:
                self.update_signal.emit("正在配置透明代理...")
                time.sleep(1)
                ok, msg = PolkitHelper.start_tproxy(
                    self.tproxy_port, self.tproxy_vps_ip,
                    self.tproxy_mark, self.tproxy_table)
                tproxy_ok = ok
                if not ok:
                    self.update_signal.emit(f"⚠ 透明代理配置失败: {msg}")

            self.success_signal.emit({
                'vpn_pid': res_vpn_pid,
                'v2ray_pid': res_v2ray_pid,
                'tproxy_ok': tproxy_ok,
            })

        except subprocess.TimeoutExpired:
            self.error_signal.emit("启动超时（60s），请检查配置文件是否正确")
        except Exception as e:
            self.error_signal.emit(f"启动异常: {e}")

    def _stop_process(self, pid: int, name: str) -> None:
        """回滚辅助：停止指定进程。"""
        try:
            subprocess.run(
                ["pkexec", PolkitHelper.HELPER_SCRIPT,
                 "stop", f"--{name}-pid", str(pid)],
                capture_output=True, text=True, timeout=30)
        except Exception:
            pass
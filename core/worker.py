"""
后台工作线程模块
包含所有 VPN/Xray 启停操作的 QThread 子类：
  - SingleVPNThread:      独立启动 OpenVPN（不影响 Xray）
  - SingleV2RayThread:    独立启动 Xray（不影响 OpenVPN）
  - CombinedStartThread:  联合启动 OpenVPN + Xray

Windows / Linux 双平台：
  Linux   → pkexec + PolkitHelper（原有逻辑不变）
  Windows → WindowsPrivilegeHandler
              OpenVPN: register-openvpn-service.bat → net start OV2NService
              Xray:    powershell start-xray.ps1 / stop-xray.ps1
              两者完全独立，缺少任一配置不影响另一个的启动/停止
"""
import os
import platform
import subprocess
import time

from PyQt5.QtCore import QThread, pyqtSignal

IS_WINDOWS = platform.system() == "Windows"

if not IS_WINDOWS:
    from core.polkit_helper import PolkitHelper


# ============================================================
# 公共辅助函数
# ============================================================

def parse_pid_from_output(stdout: str, keyword: str) -> int | None:
    for line in stdout.split('\n'):
        if keyword in line:
            try:
                return int(line.split(':')[1].strip())
            except (IndexError, ValueError):
                continue
    return None


def format_process_error(result: subprocess.CompletedProcess,
                         fallback_log: str) -> str:
    err = result.stderr.strip() if result.stderr else ""
    out = result.stdout.strip() if result.stdout else ""
    detail = ""
    if err:
        detail += f"stderr:\n{err}\n"
    if out:
        detail += f"stdout:\n{out}\n"
    return detail or f"无详细输出，请查看: {fallback_log}"


def check_user_cancelled(stderr: str) -> bool:
    lower = stderr.lower() if stderr else ""
    return "dismissed" in lower or "cancelled" in lower


def _get_windows_handler():
    from core.platform.windows.privilege import WindowsPrivilegeHandler
    return WindowsPrivilegeHandler()


# ============================================================
# 独立启动 OpenVPN 线程
# ============================================================

class SingleVPNThread(QThread):
    """
    独立启动 OpenVPN，不涉及 Xray。

    Windows 流程：
      register-openvpn-service.bat <config.ovpn> → net start OV2NService
    success_signal 发送 True（服务模式无进程 PID）。
    """

    update_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    success_signal = pyqtSignal(bool)   # Windows: True=启动成功; Linux: 兼容旧 int PID

    def __init__(self, vpn_config_path: str):
        super().__init__()
        self.vpn_config_path = vpn_config_path

    def run(self):
        if IS_WINDOWS:
            self._run_windows()
        else:
            self._run_linux()

    def _run_windows(self):
        try:
            self.update_signal.emit("正在注册并启动 OpenVPN 服务...")
            handler = _get_windows_handler()
            ok, msg = handler.start_openvpn(self.vpn_config_path)
            if ok:
                self.success_signal.emit(True)
            else:
                self.error_signal.emit(f"OpenVPN 启动失败: {msg}")
        except Exception as e:
            self.error_signal.emit(f"OpenVPN 启动异常: {e}")

    def _run_linux(self):
        try:
            self.update_signal.emit("正在启动 OpenVPN...")
            cmd = ["pkexec", PolkitHelper.HELPER_SCRIPT,
                   "start-vpn-only", self.vpn_config_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                pid = parse_pid_from_output(result.stdout, 'OpenVPN PID')
                if pid:
                    self.success_signal.emit(True)
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
            self.error_signal.emit("OpenVPN 启动超时（60s）")
        except Exception as e:
            self.error_signal.emit(f"OpenVPN 启动异常: {e}")


# ============================================================
# 独立启动 Xray 线程
# ============================================================

class SingleV2RayThread(QThread):
    """
    独立启动 Xray，不涉及 OpenVPN。

    Windows 流程：
      powershell start-xray.ps1
      脚本内部处理 sendThrough 注入、路由、DNS、TUN 适配器。
      TProxy 仅 Linux 适用，Windows 上忽略 tproxy_* 参数。
    success_signal 发送 {'pid': 0, 'tproxy_ok': False}（服务模式无 PID）。
    """

    update_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    success_signal = pyqtSignal(dict)

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
        if IS_WINDOWS:
            self._run_windows()
        else:
            self._run_linux()

    def _run_windows(self):
        try:
            self.update_signal.emit("正在启动 Xray（TUN 模式）...")
            handler = _get_windows_handler()
            # 把用户导入的配置路径传给 ps1，ps1 优先使用此路径，
            # 其次是 %APPDATA%\ov2n\config.json，最后才是内置模板
            ok, msg = handler.start_xray(self.v2ray_config_path)
            if ok:
                # Windows 服务模式无进程 PID，用 0 占位
                self.success_signal.emit({'pid': 0, 'tproxy_ok': False})
            else:
                self.error_signal.emit(f"Xray 启动失败: {msg}")
        except Exception as e:
            self.error_signal.emit(f"Xray 启动异常: {e}")

    def _run_linux(self):
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


# ============================================================
# 联合启动线程
# ============================================================

class CombinedStartThread(QThread):
    """
    联合启动 OpenVPN + Xray。

    Windows:
      两者完全独立启动，任一缺失/失败不阻断另一个。
      success_signal 额外携带 'warnings' 列表供 UI 显示部分失败提示。
    Linux:
      保持原有 pkexec 流程，OpenVPN 失败则中止（原逻辑）。
    """

    update_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    success_signal = pyqtSignal(dict)

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
        if IS_WINDOWS:
            self._run_windows()
        else:
            self._run_linux()

    def _run_windows(self):
        """
        OpenVPN 和 Xray 独立启动，互不依赖。
        已在运行的服务直接跳过，不重复启动。
        """
        try:
            handler = _get_windows_handler()
            openvpn_started = bool(self.current_vpn_pid)
            xray_started = bool(self.current_v2ray_pid)
            errors = []

            # 启动 OpenVPN（可选）
            if openvpn_started:
                self.update_signal.emit("OpenVPN 已在运行，跳过启动")
            elif self.vpn_config_path and os.path.isfile(self.vpn_config_path):
                self.update_signal.emit("正在注册并启动 OpenVPN 服务...")
                ok, msg = handler.start_openvpn(self.vpn_config_path)
                if ok:
                    openvpn_started = True
                else:
                    errors.append(f"OpenVPN: {msg}")
            else:
                self.update_signal.emit("未提供 OpenVPN 配置，跳过")

            # 启动 Xray（可选）
            if xray_started:
                self.update_signal.emit("Xray 已在运行，跳过启动")
            elif self.v2ray_config_path or os.path.isfile(
                    os.path.join(handler._paths.app_root,
                                 "resources", "xray", "config.json")):
                self.update_signal.emit("正在启动 Xray（TUN 模式）...")
                ok, msg = handler.start_xray(self.v2ray_config_path)
                if ok:
                    xray_started = True
                else:
                    errors.append(f"Xray: {msg}")
            else:
                self.update_signal.emit("未提供 Xray 配置，跳过")

            if not openvpn_started and not xray_started:
                self.error_signal.emit(
                    "没有任何服务成功启动。\n" + "\n".join(errors))
                return

            self.success_signal.emit({
                'vpn_pid': 1 if openvpn_started else 0,   # 服务模式用 1 表示运行中
                'v2ray_pid': 1 if xray_started else 0,
                'tproxy_ok': False,
                'warnings': errors,
            })

        except Exception as e:
            self.error_signal.emit(f"启动异常: {e}")

    def _run_linux(self):
        try:
            res_vpn_pid = self.current_vpn_pid
            res_v2ray_pid = self.current_v2ray_pid
            tproxy_ok = False

            # 启动 OpenVPN
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

            # 启动 V2Ray
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

            # TProxy
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
                'warnings': [],
            })

        except subprocess.TimeoutExpired:
            self.error_signal.emit("启动超时（60s）")
        except Exception as e:
            self.error_signal.emit(f"启动异常: {e}")

    def _stop_process(self, pid: int, name: str) -> None:
        try:
            subprocess.run(
                ["pkexec", PolkitHelper.HELPER_SCRIPT,
                 "stop", f"--{name}-pid", str(pid)],
                capture_output=True, text=True, timeout=30)
        except Exception:
            pass

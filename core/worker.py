"""
后台工作线程模块
包含所有 VPN/Xray 启停操作的 QThread 子类：
  - SingleVPNThread:      独立启动 OpenVPN（不影响 Xray）
  - SingleV2RayThread:    独立启动 Xray（不影响 OpenVPN）
  - CombinedStartThread:  联合启动 OpenVPN + Xray

Windows / Linux 双平台：
  Linux   → pkexec + PolkitHelper（原有逻辑不变）
  Windows → vpn_process.py 中的 OpenVPNManager / XrayManager
             - 完全替代 PowerShell 脚本和 NSSM 服务
             - 直接 subprocess 启动进程，更轻量更安全
"""
import os
import platform
import subprocess
import time
import logging
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QThread, pyqtSignal

from vpn_process import create_managers

IS_WINDOWS = platform.system() == "Windows"

log = logging.getLogger("ov2n.worker")

if not IS_WINDOWS:
    from core.polkit_helper import PolkitHelper


# ============================================================
# 公共辅助函数
# ============================================================

def parse_pid_from_output(stdout: str, keyword: str) -> Optional[int]:
    """从脚本输出中解析 PID。"""
    for line in stdout.split('\n'):
        if keyword in line:
            try:
                return int(line.split(':')[1].strip())
            except (IndexError, ValueError):
                continue
    return None


def format_process_error(result: subprocess.CompletedProcess,
                         fallback_log: str) -> str:
    """格式化进程错误信息。"""
    err = result.stderr.strip() if result.stderr else ""
    out = result.stdout.strip() if result.stdout else ""
    detail = ""
    if err:
        detail += f"stderr:\n{err}\n"
    if out:
        detail += f"stdout:\n{out}\n"
    return detail or f"无详细输出，请查看: {fallback_log}"


def check_user_cancelled(stderr: str) -> bool:
    """检查用户是否取消了权限授权（Linux）。"""
    lower = stderr.lower() if stderr else ""
    return "dismissed" in lower or "cancelled" in lower


# ============================================================
# 独立启动 OpenVPN 线程
# ============================================================

class SingleVPNThread(QThread):
    """独立启动 OpenVPN（不涉及 Xray）。"""
    update_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    success_signal = pyqtSignal(int)  # Windows: 1(占位); Linux: 真实 PID

    def __init__(self, vpn_config_path: str):
        super().__init__()
        self.vpn_config_path = vpn_config_path

    def run(self):
        if IS_WINDOWS:
            self._run_windows()
        else:
            self._run_linux()

    def _run_windows(self):
        """Windows: 使用 vpn_process.py 的 OpenVPNManager。"""
        try:
            self.update_signal.emit("正在启动 OpenVPN...")
            
            # 获取项目根目录
            app_root = Path(__file__).resolve().parent.parent
            openvpn_mgr, _ = create_managers(app_root)
            
            config_path = Path(self.vpn_config_path)
            if not config_path.exists():
                self.error_signal.emit(f"配置文件不存在: {self.vpn_config_path}")
                return
            
            if openvpn_mgr.start(config_path):
                pid = openvpn_mgr.get_pid() or 1
                self.update_signal.emit("✓ OpenVPN 启动成功")
                self.success_signal.emit(pid)
            else:
                self.error_signal.emit("OpenVPN 启动失败，请检查配置文件")
        except Exception as e:
            log.exception("OpenVPN 启动异常")
            self.error_signal.emit(f"OpenVPN 启动异常: {e}")

    def _run_linux(self):
        """Linux: 保持原有 pkexec 流程。"""
        try:
            self.update_signal.emit("正在启动 OpenVPN...")
            cmd = ["pkexec", PolkitHelper.HELPER_SCRIPT,
                   "start-vpn-only", self.vpn_config_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                pid = parse_pid_from_output(result.stdout, 'OpenVPN PID')
                if pid:
                    self.update_signal.emit("✓ OpenVPN 启动成功")
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
            self.error_signal.emit("OpenVPN 启动超时（60s）")
        except Exception as e:
            log.exception("OpenVPN 启动异常")
            self.error_signal.emit(f"OpenVPN 启动异常: {e}")


# ============================================================
# 独立启动 Xray 线程
# ============================================================

class SingleV2RayThread(QThread):
    """
    独立启动 Xray（不涉及 OpenVPN）。
    
    Windows:
      - 使用 vpn_process.py 的 XrayManager
      - 完整处理：配置选择、sendThrough 注入、TUN 网卡、IP 配置、路由、DNS
      - TProxy 参数在 Windows 上被忽略（Windows 使用 TUN 模式）
    
    Linux:
      - 原有 pkexec + PolkitHelper 流程
      - 支持 TProxy 配置
    """

    update_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    success_signal = pyqtSignal(dict)  # {"pid": int, "tproxy_ok": bool}

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
        """
        Windows: 使用 vpn_process.py 的 XrayManager。
        完全替代 start-xray.ps1，包括：
          - 配置文件优先级处理（用户 > APPDATA > 内置）
          - 注入 sendThrough
          - 启动 xray.exe
          - 创建 xray-tun 虚拟网卡
          - 配置 IP (10.0.0.1/24)
          - 设置路由表（VPS、网关、默认路由）
          - 配置 DNS (114.114.114.114, 8.8.8.8)
        """
        try:
            self.update_signal.emit("正在启动 Xray（TUN 模式）...")
            
            # 获取项目根目录
            app_root = Path(__file__).resolve().parent.parent
            _, xray_mgr = create_managers(app_root)
            
            config_path = Path(self.v2ray_config_path) if self.v2ray_config_path else None
            
            if xray_mgr.start(config_path):
                pid = xray_mgr.get_pid() or 1
                self.update_signal.emit("✓ Xray 启动成功（TUN 模式自动配置）")
                self.success_signal.emit({
                    'pid': pid,
                    'tproxy_ok': False  # Windows TUN 模式不使用 TProxy
                })
            else:
                self.error_signal.emit(
                    "Xray 启动失败，请检查配置文件和网络设置。\n"
                    "查看日志: logs/xray.log")
        except Exception as e:
            log.exception("Xray 启动异常")
            self.error_signal.emit(f"Xray 启动异常: {e}")

    def _run_linux(self):
        """Linux: 原有 pkexec + PolkitHelper 流程，支持 TProxy。"""
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
                if ok:
                    self.update_signal.emit("✓ 透明代理已配置")
                else:
                    self.update_signal.emit(f"⚠ 透明代理配置失败: {msg}")

            self.success_signal.emit({'pid': v2ray_pid, 'tproxy_ok': tproxy_ok})
        except subprocess.TimeoutExpired:
            self.error_signal.emit("V2Ray 启动超时（60s）")
        except Exception as e:
            log.exception("V2Ray 启动异常")
            self.error_signal.emit(f"V2Ray 启动异常: {e}")


# ============================================================
# 联合启动线程
# ============================================================

class CombinedStartThread(QThread):
    """
    联合启动 OpenVPN + Xray。

    Windows:
      - 使用 vpn_process.py 的管理器，完全替代旧脚本
      - OpenVPN 和 Xray 独立启动，任一缺失/失败不阻断另一个
      - success_signal 携带 'warnings' 列表供 UI 显示部分失败提示

    Linux:
      - 原有 pkexec 流程
      - OpenVPN 失败则中止（原逻辑）
    """

    update_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    success_signal = pyqtSignal(dict)

    def __init__(self, vpn_config_path: str, v2ray_config_path: str,
                 current_vpn_pid: Optional[int], current_v2ray_pid: Optional[int],
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
        Windows: 完全使用 vpn_process.py。
        OpenVPN 和 Xray 独立启动，互不依赖。
        """
        try:
            app_root = Path(__file__).resolve().parent.parent
            openvpn_mgr, xray_mgr = create_managers(app_root)
            
            openvpn_started = bool(self.current_vpn_pid)
            xray_started = bool(self.current_v2ray_pid)
            errors = []

            # ── 启动 OpenVPN（可选）──
            if openvpn_started:
                self.update_signal.emit("OpenVPN 已在运行，跳过启动")
            else:
                vpn_cfg = Path(self.vpn_config_path) if self.vpn_config_path else None
                if vpn_cfg and vpn_cfg.exists():
                    self.update_signal.emit("正在启动 OpenVPN...")
                    try:
                        if openvpn_mgr.start(vpn_cfg):
                            openvpn_started = True
                            self.update_signal.emit("✓ OpenVPN 启动成功")
                        else:
                            errors.append("OpenVPN 启动失败")
                    except Exception as e:
                        errors.append(f"OpenVPN 异常: {e}")
                else:
                    self.update_signal.emit("未提供 OpenVPN 配置，跳过")

            # ── 启动 Xray（可选）──
            if xray_started:
                self.update_signal.emit("Xray 已在运行，跳过启动")
            else:
                xray_cfg = Path(self.v2ray_config_path) if self.v2ray_config_path else None
                if xray_cfg and xray_cfg.exists():
                    self.update_signal.emit("正在启动 Xray（TUN 模式）...")
                    try:
                        if xray_mgr.start(xray_cfg):
                            xray_started = True
                            self.update_signal.emit("✓ Xray 启动成功")
                        else:
                            errors.append("Xray 启动失败")
                    except Exception as e:
                        errors.append(f"Xray 异常: {e}")
                else:
                    self.update_signal.emit("未提供 Xray 配置，跳过")

            # ── 检查结果──
            if not openvpn_started and not xray_started:
                self.error_signal.emit(
                    "没有任何服务成功启动。\n\n" +
                    "\n".join(f"• {e}" for e in errors))
                return

            self.success_signal.emit({
                'vpn_pid': 1 if openvpn_started else 0,
                'v2ray_pid': 1 if xray_started else 0,
                'tproxy_ok': False,
                'warnings': errors,
            })

        except Exception as e:
            log.exception("联合启动异常")
            self.error_signal.emit(f"启动异常: {e}")

    def _run_linux(self):
        """Linux: 原有 pkexec 流程。"""
        try:
            res_vpn_pid = self.current_vpn_pid
            res_v2ray_pid = self.current_v2ray_pid
            tproxy_ok = False

            # ── 启动 OpenVPN ──
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
                self.update_signal.emit("✓ OpenVPN 启动成功")
            else:
                self.update_signal.emit("OpenVPN 已在运行，跳过启动")

            # ── 启动 V2Ray ──
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
                self.update_signal.emit("✓ V2Ray 启动成功")
            else:
                self.update_signal.emit("V2Ray 已在运行，跳过启动")

            # ── 配置 TProxy（Linux 仅）──
            if self.tproxy_enabled:
                self.update_signal.emit("正在配置透明代理...")
                time.sleep(1)
                ok, msg = PolkitHelper.start_tproxy(
                    self.tproxy_port, self.tproxy_vps_ip,
                    self.tproxy_mark, self.tproxy_table)
                tproxy_ok = ok
                if ok:
                    self.update_signal.emit("✓ 透明代理已配置")
                else:
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
            log.exception("联合启动异常")
            self.error_signal.emit(f"启动异常: {e}")

    def _stop_process(self, pid: int, name: str) -> None:
        """紧急停止进程（回滚）。"""
        try:
            subprocess.run(
                ["pkexec", PolkitHelper.HELPER_SCRIPT,
                 "stop", f"--{name}-pid", str(pid)],
                capture_output=True, text=True, timeout=30)
        except Exception as e:
            log.warning("回滚停止进程失败: %s", e)
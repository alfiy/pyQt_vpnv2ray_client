"""
Windows 权限提升实现。

控制流设计：
  OpenVPN:
    注册服务 → register-openvpn-service.bat <config.ovpn>
    启动     → net start OV2NService
    停止     → net stop OV2NService

  Xray (TUN 模式，需要管理员权限):
    启动 → powershell -File scripts/windows/start-xray.ps1
    停止 → powershell -File scripts/windows/stop-xray.ps1

说明：
  - OpenVPN 通过 NSSM 注册为 Windows Service，由 SCM 管理生命周期
  - Xray 通过 PowerShell 脚本启动，脚本内部负责路由、DNS、TUN 适配器配置
  - privilege.py 不重复实现路由/DNS/sendThrough 注入，全部由 ps1 脚本负责
  - 所有 subprocess 调用均使用 CREATE_NO_WINDOW 避免弹出控制台窗口
"""
import os
import subprocess
from typing import Dict, Tuple

from core.platform.base import PrivilegeHandler

CREATE_NO_WINDOW = 0x08000000


class WindowsPrivilegeHandler(PrivilegeHandler):

    def __init__(self):
        from core.platform.windows.paths import WindowsPaths
        self._paths = WindowsPaths()

    # ══════════════════════════════════════════
    # PrivilegeHandler 基类接口
    # ══════════════════════════════════════════

    def check_available(self) -> bool:
        return True

    def check_helper_installed(self) -> bool:
        """检查 NSSM 是否存在。"""
        return os.path.isfile(self._paths.nssm_exe)

    def run_privileged(self, cmd: list, timeout: int = 60) -> Tuple[int, str, str]:
        """以管理员权限执行命令（UAC）。"""
        try:
            ps_cmd = (
                f'Start-Process -FilePath "{cmd[0]}" '
                f'-ArgumentList \'{" ".join(cmd[1:])}\' '
                f'-Verb RunAs -Wait -PassThru'
            )
            result = subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=timeout,
                creationflags=CREATE_NO_WINDOW,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "执行超时"
        except Exception as e:
            return -1, "", str(e)

    # ══════════════════════════════════════════
    # OpenVPN 服务管理
    # ══════════════════════════════════════════

    def register_openvpn_service(self, vpn_config_path: str) -> Tuple[bool, str]:
        """
        调用 register-openvpn-service.bat 注册 OV2NService。
        bat 内部会先 remove 旧服务再重新注册，每次启动前调用。

        Args:
            vpn_config_path: .ovpn 配置文件的绝对路径

        Returns:
            (success, message)
        """
        bat = os.path.join(
            self._paths.scripts_dir, "windows", "register-openvpn-service.bat")
        if not os.path.isfile(bat):
            return False, f"注册脚本未找到: {bat}"
        if not vpn_config_path or not os.path.isfile(vpn_config_path):
            return False, f"VPN 配置文件不存在: {vpn_config_path}"

        try:
            # 直接调用 bat（已移除 pause，不会阻塞）。
            # 不使用 CREATE_NO_WINDOW，确保 NSSM install 能正确执行。
            # encoding='utf-8' + errors='replace' 防止 GBK 输出崩溃。
            result = subprocess.run(
                [bat, vpn_config_path],
                capture_output=True, text=True,
                encoding='utf-8', errors='replace',
                timeout=60,
            )
            if result.returncode == 0:
                return True, "OV2NService 注册成功"
            detail = result.stdout.strip() or result.stderr.strip()
            return False, f"服务注册失败 (exit {result.returncode}): {detail}"
        except subprocess.TimeoutExpired:
            return False, "服务注册超时（60s）"
        except Exception as e:
            return False, f"服务注册异常: {e}"

    def start_openvpn(self, vpn_config_path: str) -> Tuple[bool, str]:
        """
        注册并启动 OpenVPN 服务。
        流程：register-openvpn-service.bat → net start OV2NService

        Args:
            vpn_config_path: .ovpn 配置文件绝对路径

        Returns:
            (success, message)
        """
        ok, msg = self.register_openvpn_service(vpn_config_path)
        if not ok:
            return False, msg
        return self._net_start("OV2NService")

    def stop_openvpn(self) -> Tuple[bool, str]:
        """
        停止 OpenVPN 服务（net stop OV2NService）。

        Returns:
            (success, message)
        """
        return self._net_stop("OV2NService")

    def is_openvpn_running(self) -> bool:
        """查询 OV2NService 是否处于 RUNNING 状态。"""
        return self._is_service_running("OV2NService")

    # ══════════════════════════════════════════
    # Xray 管理（通过 PowerShell 脚本）
    # ══════════════════════════════════════════

    def start_xray(self, v2ray_config_path: str = "") -> Tuple[bool, str]:
        """
        调用 start-xray.ps1 启动 Xray TUN 模式。
        脚本内部负责：sendThrough 注入、路由设置、DNS 配置、TUN 适配器。
        需要管理员权限（脚本自身会检查）。

        Args:
            v2ray_config_path: 用户导入的 config.json 路径，
                               不传则 ps1 自动按优先级查找。

        Returns:
            (success, message)
        """
        ps1 = os.path.join(
            self._paths.scripts_dir, "windows", "start-xray.ps1")
        if not os.path.isfile(ps1):
            return False, f"Xray 启动脚本未找到: {ps1}"

        try:
            # 构建命令：有用户配置路径时通过 -ConfigPath 传入 ps1
            cmd = [
                "powershell",
                "-NonInteractive",
                "-ExecutionPolicy", "Bypass",
                "-File", ps1,
            ]
            if v2ray_config_path and os.path.isfile(v2ray_config_path):
                cmd += ["-ConfigPath", v2ray_config_path]
            result = subprocess.run(
                cmd,
                capture_output=True, text=True,
                encoding='utf-8', errors='replace',
                timeout=120,
            )
            output = result.stdout.strip()
            stderr = result.stderr.strip()
            if result.returncode == 0 and "启动完成" in output:
                return True, "Xray 已启动"
            # 收集所有 error: 行，无则返回完整输出方便排查
            error_lines = [l for l in output.splitlines() if l.startswith("error:")]
            if not error_lines and stderr:
                detail = stderr
            else:
                detail = "\n".join(error_lines) if error_lines else output
            return False, f"Xray 启动失败: {detail}"
        except subprocess.TimeoutExpired:
            return False, "Xray 启动超时（120s），请检查 config.json 及网络"
        except Exception as e:
            return False, f"Xray 启动异常: {e}"

    def stop_xray(self) -> Tuple[bool, str]:
        """
        调用 stop-xray.ps1 停止 Xray，清理路由和 DNS。

        Returns:
            (success, message)
        """
        ps1 = os.path.join(
            self._paths.scripts_dir, "windows", "stop-xray.ps1")
        if not os.path.isfile(ps1):
            return self._taskkill_xray()

        try:
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", ps1],
                capture_output=True, text=True,
                encoding='utf-8', errors='replace',
                timeout=60,
                creationflags=CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                return True, "Xray 已停止"
            detail = result.stdout.strip() or result.stderr.strip()
            return False, f"Xray 停止失败: {detail}"
        except subprocess.TimeoutExpired:
            return self._taskkill_xray()
        except Exception as e:
            return False, f"Xray 停止异常: {e}"

    def is_xray_running(self) -> bool:
        """检查 xray.exe 进程是否存在。"""
        from core.platform.windows.process_manager import WindowsProcessManager
        pm = WindowsProcessManager()
        return pm.find_process_by_name("xray.exe") is not None

    # ══════════════════════════════════════════
    # 联合启停（供 CombinedStartThread 调用）
    # ══════════════════════════════════════════

    def start_vpn(self, vpn_config_path: str, v2ray_config_path: str
                  ) -> Tuple[bool, str, Dict]:
        """
        联合启动 OpenVPN + Xray，两者完全独立互不影响。

        Args:
            vpn_config_path:   .ovpn 路径，空或不存在则跳过 OpenVPN
            v2ray_config_path: 不为空则尝试启动 Xray（实际配置由 ps1 读取）

        Returns:
            (success, message, info_dict)
            info_dict: {'openvpn_started', 'xray_started', 'warnings'}
        """
        info = {"openvpn_started": False, "xray_started": False, "warnings": []}
        errors = []

        # OpenVPN（可选）
        if vpn_config_path and os.path.isfile(vpn_config_path):
            ok, msg = self.start_openvpn(vpn_config_path)
            if ok:
                info["openvpn_started"] = True
            else:
                errors.append(f"OpenVPN: {msg}")

        # Xray（可选）：把用户配置路径传给 start_xray，ps1 会优先使用
        xray_config = os.path.join(
            self._paths.app_root, "resources", "xray", "config.json")
        if v2ray_config_path or os.path.isfile(xray_config):
            ok, msg = self.start_xray(v2ray_config_path)
            if ok:
                info["xray_started"] = True
            else:
                errors.append(f"Xray: {msg}")

        info["warnings"] = errors

        if not info["openvpn_started"] and not info["xray_started"]:
            return False, "没有任何服务成功启动:\n" + "\n".join(errors), info

        parts = []
        if info["openvpn_started"]:
            parts.append("OpenVPN")
        if info["xray_started"]:
            parts.append("Xray")
        msg = " + ".join(parts) + " 启动成功"
        if errors:
            msg += f"（警告: {'; '.join(errors)}）"
        return True, msg, info

    def stop_vpn(self, info: Dict = None) -> Tuple[bool, str]:
        """
        联合停止 OpenVPN + Xray。

        Args:
            info: start_vpn() 返回的 info_dict。为 None 时尝试停止全部。
        """
        errors = []
        stop_openvpn = info.get("openvpn_started", True) if info else True
        stop_xray = info.get("xray_started", True) if info else True

        if stop_openvpn and self.is_openvpn_running():
            ok, msg = self.stop_openvpn()
            if not ok:
                errors.append(f"OpenVPN: {msg}")

        if stop_xray and self.is_xray_running():
            ok, msg = self.stop_xray()
            if not ok:
                errors.append(f"Xray: {msg}")

        if errors:
            return False, "部分服务停止失败:\n" + "\n".join(errors)
        return True, "所有服务已停止"

    # ══════════════════════════════════════════
    # NSSM 服务管理（供安装脚本调用）
    # ══════════════════════════════════════════

    def install_service(self) -> Tuple[bool, str]:
        """注册服务框架（无 config），供 install.bat 调用。"""
        nssm = self._paths.nssm_exe
        if not os.path.isfile(nssm):
            return False, f"NSSM 未找到: {nssm}"
        openvpn_exe = self._paths.openvpn_exe
        if not os.path.isfile(openvpn_exe):
            return False, f"OpenVPN 未找到: {openvpn_exe}"
        service_name = "OV2NService"
        try:
            subprocess.run([nssm, "remove", service_name, "confirm"],
                           capture_output=True, creationflags=CREATE_NO_WINDOW)
            result = subprocess.run([nssm, "install", service_name, openvpn_exe],
                                    capture_output=True, text=True,
                                    creationflags=CREATE_NO_WINDOW)
            if result.returncode != 0:
                return False, f"NSSM install 失败: {result.stderr}"
            subprocess.run([nssm, "set", service_name, "Start", "SERVICE_DEMAND_START"],
                           capture_output=True, creationflags=CREATE_NO_WINDOW)
            return True, f"服务 {service_name} 已注册"
        except Exception as e:
            return False, f"注册失败: {e}"

    def uninstall_service(self) -> Tuple[bool, str]:
        """卸载 OV2NService。"""
        nssm = self._paths.nssm_exe
        service_name = "OV2NService"
        try:
            subprocess.run(["net", "stop", service_name],
                           capture_output=True, creationflags=CREATE_NO_WINDOW)
            if os.path.isfile(nssm):
                subprocess.run([nssm, "remove", service_name, "confirm"],
                               capture_output=True, creationflags=CREATE_NO_WINDOW)
            else:
                subprocess.run(["sc", "delete", service_name],
                               capture_output=True, creationflags=CREATE_NO_WINDOW)
            return True, f"服务 {service_name} 已卸载"
        except Exception as e:
            return False, f"卸载失败: {e}"

    def set_service_autostart(self, enabled: bool) -> Tuple[bool, str]:
        """设置 OV2NService 是否开机自启。"""
        nssm = self._paths.nssm_exe
        service_name = "OV2NService"
        start_type = "SERVICE_AUTO_START" if enabled else "SERVICE_DEMAND_START"
        try:
            if os.path.isfile(nssm):
                subprocess.run([nssm, "set", service_name, "Start", start_type],
                               capture_output=True, creationflags=CREATE_NO_WINDOW)
            else:
                subprocess.run(["sc", "config", service_name,
                                "start=", "auto" if enabled else "demand"],
                               capture_output=True, creationflags=CREATE_NO_WINDOW)
            return True, f"服务已设为{'开机自启' if enabled else '手动启动'}"
        except Exception as e:
            return False, f"设置失败: {e}"

    # ══════════════════════════════════════════
    # 内部工具方法
    # ══════════════════════════════════════════

    def _net_start(self, service_name: str) -> Tuple[bool, str]:
        try:
            result = subprocess.run(
                ["net", "start", service_name],
                capture_output=True, text=True, timeout=30,
                encoding='utf-8', errors='replace',
                creationflags=CREATE_NO_WINDOW)
            if result.returncode == 0:
                return True, f"{service_name} 已启动"
            if "已经启动" in result.stdout or "already been started" in result.stdout:
                return True, f"{service_name} 已在运行"
            detail = result.stdout.strip() or result.stderr.strip()
            return False, f"{service_name} 启动失败: {detail}"
        except subprocess.TimeoutExpired:
            return False, f"{service_name} 启动超时"
        except Exception as e:
            return False, f"{service_name} 启动异常: {e}"

    def _net_stop(self, service_name: str) -> Tuple[bool, str]:
        try:
            result = subprocess.run(
                ["net", "stop", service_name],
                capture_output=True, text=True, timeout=30,
                encoding='utf-8', errors='replace',
                creationflags=CREATE_NO_WINDOW)
            if result.returncode == 0:
                return True, f"{service_name} 已停止"
            if "未启动" in result.stdout or "not started" in result.stdout:
                return True, f"{service_name} 本未运行"
            detail = result.stdout.strip() or result.stderr.strip()
            return False, f"{service_name} 停止失败: {detail}"
        except subprocess.TimeoutExpired:
            return False, f"{service_name} 停止超时"
        except Exception as e:
            return False, f"{service_name} 停止异常: {e}"

    def _is_service_running(self, service_name: str) -> bool:
        try:
            result = subprocess.run(
                ["sc", "query", service_name],
                capture_output=True, text=True,
                creationflags=CREATE_NO_WINDOW)
            return "RUNNING" in result.stdout
        except Exception:
            return False

    def _taskkill_xray(self) -> Tuple[bool, str]:
        """降级：直接 taskkill xray.exe（不清理路由/DNS）。"""
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/IM", "xray.exe"],
                capture_output=True, text=True,
                creationflags=CREATE_NO_WINDOW)
            if result.returncode == 0:
                return True, "xray 进程已强制终止（路由/DNS 未清理）"
            return False, f"taskkill 失败: {result.stderr.strip()}"
        except Exception as e:
            return False, f"taskkill 异常: {e}"
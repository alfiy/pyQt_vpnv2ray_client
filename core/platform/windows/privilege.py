"""
Windows 权限提升实现。

控制流设计（v2，无脚本版）：
  OpenVPN:
    启动 → OpenVPNManager.start(config.ovpn)   [subprocess.Popen 直接管理进程]
    停止 → OpenVPNManager.stop()

  Xray (TUN 模式，需要管理员权限):
    启动 → XrayManager.start(config.json)      [subprocess.Popen 直接管理进程]
    停止 → XrayManager.stop()                  [同时清理路由/DNS]

变更说明（对比 v1）：
  - 完全移除对 start-xray.ps1 / stop-xray.ps1 的调用
  - 完全移除对 register-openvpn-service.bat 的调用
  - 完全移除对 NSSM 服务注册 / net start / net stop 的依赖
  - 路由、DNS、sendThrough 注入全部由 vpn_process.XrayManager 内部处理
  - OpenVPN 进程生命周期由 vpn_process.OpenVPNManager 直接管理

杀软友好原因：
  - 不调用任何 .ps1 脚本（-ExecutionPolicy Bypass 消失）
  - 不写注册表服务项（NSSM install 行为消失）
  - 不使用 DETACHED_PROCESS flag（隐藏进程特征消失）
  - 只做 subprocess.Popen(openvpn.exe / xray.exe)，白名单行为
"""
import os
from typing import Dict, Optional, Tuple

from core.platform.base import PrivilegeHandler

# vpn_process.py 与本文件同属项目根目录
# 如果你的 privilege.py 位于 core/platform/windows/，需要调整相对导入路径
try:
    from vpn_process import OpenVPNManager, XrayManager, create_managers
except ImportError:
    # 回退：尝试从项目根目录导入
    import sys
    import pathlib
    _root = pathlib.Path(__file__).resolve().parent.parent.parent.parent
    sys.path.insert(0, str(_root))
    from vpn_process import OpenVPNManager, XrayManager, create_managers


class WindowsPrivilegeHandler(PrivilegeHandler):

    def __init__(self):
        from core.platform.windows.paths import WindowsPaths
        self._paths = WindowsPaths()

        # 创建进程管理器（懒初始化，首次调用时构建）
        self._openvpn_mgr: Optional[OpenVPNManager] = None
        self._xray_mgr: Optional[XrayManager] = None

    # ── 进程管理器懒初始化 ──────────────────────────────────
    def _get_managers(self) -> Tuple[OpenVPNManager, XrayManager]:
        """首次调用时构建管理器，之后复用同一实例（保留进程句柄）。"""
        if self._openvpn_mgr is None or self._xray_mgr is None:
            import pathlib
            self._openvpn_mgr, self._xray_mgr = create_managers(
                app_root=pathlib.Path(self._paths.app_root)
            )
        return self._openvpn_mgr, self._xray_mgr

    # ══════════════════════════════════════════
    # PrivilegeHandler 基类接口
    # ══════════════════════════════════════════

    def check_available(self) -> bool:
        return True

    def check_helper_installed(self) -> bool:
        """
        v1 检查 NSSM 是否存在。
        v2 改为检查 openvpn.exe 是否存在（服务注册已不再需要 NSSM）。
        """
        return os.path.isfile(self._paths.openvpn_exe)

    def run_privileged(self, cmd: list, timeout: int = 60) -> Tuple[int, str, str]:
        """
        以管理员权限执行命令（UAC 提升）。
        仅用于需要提权的零散系统命令，不用于 OpenVPN/Xray 启停。
        """
        import subprocess
        _CREATE_NO_WINDOW = 0x08000000
        try:
            ps_cmd = (
                f'Start-Process -FilePath "{cmd[0]}" '
                f'-ArgumentList \'{" ".join(cmd[1:])}\' '
                f'-Verb RunAs -Wait -PassThru'
            )
            result = subprocess.run(
                ["powershell", "-NonInteractive", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=timeout,
                creationflags=_CREATE_NO_WINDOW,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "执行超时"
        except Exception as e:
            return -1, "", str(e)

    # ══════════════════════════════════════════
    # OpenVPN 管理（直接进程，不经过 NSSM）
    # ══════════════════════════════════════════

    def start_openvpn(self, vpn_config_path: str) -> Tuple[bool, str]:
        """
        直接用 OpenVPNManager 启动 openvpn.exe，不注册系统服务。

        Args:
            vpn_config_path: .ovpn 配置文件的绝对路径
        """
        if not vpn_config_path or not os.path.isfile(vpn_config_path):
            return False, f"VPN 配置文件不存在: {vpn_config_path}"

        import pathlib
        openvpn_mgr, _ = self._get_managers()
        ok = openvpn_mgr.start(pathlib.Path(vpn_config_path))
        if ok:
            return True, "OpenVPN 已启动"
        return False, "OpenVPN 启动失败，请检查 logs/openvpn.log"

    def stop_openvpn(self) -> Tuple[bool, str]:
        """停止 OpenVPN 进程。"""
        openvpn_mgr, _ = self._get_managers()
        openvpn_mgr.stop()
        return True, "OpenVPN 已停止"

    def is_openvpn_running(self) -> bool:
        """检查 OpenVPN 进程是否在运行。"""
        openvpn_mgr, _ = self._get_managers()
        return openvpn_mgr.is_running

    # ══════════════════════════════════════════
    # Xray 管理（直接进程，含路由/DNS 管理）
    # ══════════════════════════════════════════

    def start_xray(self, v2ray_config_path: str = "") -> Tuple[bool, str]:
        """
        用 XrayManager 直接启动 xray.exe。
        XrayManager 内部完整处理：
          - sendThrough 注入
          - config.runtime.json 写入（无 BOM UTF-8）
          - 等待 xray-tun 网卡出现
          - route add / netsh 路由和 DNS 配置

        Args:
            v2ray_config_path: 用户导入的 config.json 路径（可为空，会自动查找）
        """
        import pathlib
        _, xray_mgr = self._get_managers()

        # 按优先级确定配置文件路径
        config_path = self._resolve_xray_config(v2ray_config_path)
        if config_path is None:
            return False, "未找到 Xray 配置文件（已检查 -ConfigPath、APPDATA、resources/xray）"

        ok = xray_mgr.start(config_path)
        if ok:
            return True, "Xray 已启动"
        return False, "Xray 启动失败，请检查 logs/xray.log"

    def stop_xray(self) -> Tuple[bool, str]:
        """
        停止 Xray，同时清理路由和恢复 DNS。
        完整替代 stop-xray.ps1 的所有功能。
        """
        _, xray_mgr = self._get_managers()
        xray_mgr.stop()
        return True, "Xray 已停止"

    def is_xray_running(self) -> bool:
        """检查 xray.exe 进程是否在运行。"""
        _, xray_mgr = self._get_managers()
        return xray_mgr.is_running

    # ══════════════════════════════════════════
    # 联合启停（供 CombinedStartThread 调用）
    # ══════════════════════════════════════════

    def start_vpn(self, vpn_config_path: str, v2ray_config_path: str
                  ) -> Tuple[bool, str, Dict]:
        """
        联合启动 OpenVPN + Xray，两者完全独立互不影响。

        Args:
            vpn_config_path:   .ovpn 路径，空或不存在则跳过 OpenVPN
            v2ray_config_path: config.json 路径，空则自动查找

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

        # Xray（可选）
        xray_config_fallback = os.path.join(
            self._paths.app_root, "resources", "xray", "config.json")
        if v2ray_config_path or os.path.isfile(xray_config_fallback):
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
        stop_xray    = info.get("xray_started",    True) if info else True

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
    # 服务管理（向后兼容保留接口，内部已不依赖 NSSM）
    # ══════════════════════════════════════════

    def install_service(self) -> Tuple[bool, str]:
        """
        v2：无需安装系统服务，OpenVPN 进程由 GUI 直接管理。
        保留此接口以免调用方报错，直接返回成功。
        """
        return True, "v2 不使用系统服务，OpenVPN 由 GUI 进程直接管理"

    def uninstall_service(self) -> Tuple[bool, str]:
        """
        v2：清理可能残留的旧版 OV2NService（如果存在）。
        """
        import subprocess
        _CREATE_NO_WINDOW = 0x08000000
        service_name = "OV2NService"
        try:
            # 先尝试停止
            subprocess.run(
                ["net", "stop", service_name],
                capture_output=True, creationflags=_CREATE_NO_WINDOW,
                timeout=15,
            )
            # 再删除
            nssm = getattr(self._paths, "nssm_exe", "")
            if nssm and os.path.isfile(nssm):
                subprocess.run(
                    [nssm, "remove", service_name, "confirm"],
                    capture_output=True, creationflags=_CREATE_NO_WINDOW,
                    timeout=15,
                )
            else:
                subprocess.run(
                    ["sc", "delete", service_name],
                    capture_output=True, creationflags=_CREATE_NO_WINDOW,
                    timeout=15,
                )
            return True, f"旧版服务 {service_name} 已清理"
        except Exception as e:
            return True, f"服务清理（忽略错误）: {e}"

    def register_openvpn_service(self, vpn_config_path: str) -> Tuple[bool, str]:
        """
        v2：不再使用 register-openvpn-service.bat。
        保留接口，直接委托给 start_openvpn()。
        """
        return self.start_openvpn(vpn_config_path)

    def set_service_autostart(self, enabled: bool) -> Tuple[bool, str]:
        """
        v2：不依赖系统服务，无开机自启概念。
        如需实现开机自启，应通过任务计划程序（schtasks）而非服务。
        """
        return False, "v2 不使用系统服务，开机自启功能待实现（建议通过任务计划程序）"

    # ══════════════════════════════════════════
    # 内部工具
    # ══════════════════════════════════════════

    def _resolve_xray_config(self, user_config_path: str) -> "Optional[pathlib.Path]":
        """
        按优先级查找 Xray 配置文件，等价于 start-xray.ps1 的配置查找逻辑：
          1. 调用方传入的 user_config_path（用户从 GUI 导入的配置）
          2. %APPDATA%\ov2n\config.json（持久化的用户配置）
          3. resources/xray/config.json（内置配置）
        """
        import pathlib

        # 1. 用户传入
        if user_config_path and os.path.isfile(user_config_path):
            return pathlib.Path(user_config_path)

        # 2. APPDATA
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            appdata_cfg = pathlib.Path(appdata) / "ov2n" / "config.json"
            if appdata_cfg.exists():
                return appdata_cfg

        # 3. 内置
        builtin = pathlib.Path(self._paths.app_root) / "resources" / "xray" / "config.json"
        if builtin.exists():
            return builtin

        return None
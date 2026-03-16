"""
Windows 权限提升实现（骨架）。

实现策略：
1. 首选：注册 Windows Service，通过命名管道/TCP 与 GUI 通信
   - 安装时一次性 UAC 授权，后续操作无需再次弹窗
2. 备选：每次操作通过 runas 提升权限

TODO: 后续逐步填充具体实现。
"""
from typing import Dict, Tuple

from core.platform.base import PrivilegeHandler


class WindowsPrivilegeHandler(PrivilegeHandler):
    """
    Windows 权限提升处理器。

    设计思路：
    - install_service(): 使用 sc.exe 或 pywin32 注册 Windows Service
    - run_privileged(): 优先通过 Service 通信，降级为 runas
    - start_vpn()/stop_vpn(): 委托给 Service 或直接 runas 执行
    """

    def check_available(self) -> bool:
        """
        检查权限提升机制是否可用。
        Windows 始终支持 UAC，但检查 Service 是否已注册。

        TODO: 检查 ov2n-service 是否已注册并运行。
        """
        raise NotImplementedError(
            "Windows 权限提升尚未实现。\n"
            "计划: UAC (runas) + Windows Service 注册")

    def check_helper_installed(self) -> bool:
        """
        检查辅助服务是否已安装。

        TODO: 查询 Windows Service 注册状态。
        """
        raise NotImplementedError("Windows helper 检查尚未实现")

    def run_privileged(self, cmd: list, timeout: int = 60) -> Tuple[int, str, str]:
        """
        以管理员权限执行命令。

        实现方案：
        方案 A (Service 模式):
            通过命名管道发送命令到已注册的 ov2n-service
        方案 B (UAC 模式):
            使用 ctypes.windll.shell32.ShellExecuteW(None, "runas", ...)

        TODO: 实现具体逻辑。
        """
        raise NotImplementedError("Windows 权限提升执行尚未实现")

    def start_vpn(self, vpn_config_path: str, v2ray_config_path: str
                   ) -> Tuple[bool, str, Dict]:
        """
        启动 VPN 和 V2Ray。

        Windows 流程：
        1. 检查 TAP-Windows 驱动是否已安装
        2. 通过 Service 或 runas 启动 openvpn.exe
        3. 启动 v2ray.exe / xray.exe
        4. 返回进程 PID

        TODO: 实现具体逻辑。
        """
        raise NotImplementedError("Windows VPN 启动尚未实现")

    def stop_vpn(self, pids: Dict) -> Tuple[bool, str]:
        """
        停止 VPN 进程。

        Windows 流程：
        1. 通过 Service 发送停止命令，或
        2. 使用 taskkill /PID xxx /F

        TODO: 实现具体逻辑。
        """
        raise NotImplementedError("Windows VPN 停止尚未实现")

    def install_service(self) -> Tuple[bool, str]:
        """
        注册 Windows Service。

        实现步骤：
        1. 将 vpn-helper-service.exe 复制到 Program Files
        2. 使用 sc.exe create 或 pywin32 注册服务
        3. 配置服务为手动启动
        4. 启动服务

        命令示例：
            sc create ov2n-service binPath= "C:\\Program Files\\ov2n\\vpn-helper-service.exe"
            sc config ov2n-service start= demand
            sc start ov2n-service

        TODO: 实现具体逻辑。
        """
        raise NotImplementedError("Windows Service 注册尚未实现")

    def uninstall_service(self) -> Tuple[bool, str]:
        """
        卸载 Windows Service。

        命令示例：
            sc stop ov2n-service
            sc delete ov2n-service

        TODO: 实现具体逻辑。
        """
        raise NotImplementedError("Windows Service 卸载尚未实现")
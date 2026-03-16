"""
Windows 进程管理实现（骨架）。

使用 taskkill、TerminateProcess 等 Windows 原生 API。

TODO: 后续逐步填充具体实现。
"""
from typing import Optional

from core.platform.base import ProcessManager


class WindowsProcessManager(ProcessManager):
    """
    Windows 进程管理器。

    实现要点：
    - start_process: subprocess.Popen + CREATE_NEW_PROCESS_GROUP
    - stop_process: taskkill /PID /F 或 ctypes TerminateProcess
    - is_process_alive: OpenProcess 检查 或 tasklist 查询
    - find_process_by_name: tasklist /FI "IMAGENAME eq xxx"
    """

    def start_process(self, cmd: list, log_file: Optional[str] = None,
                      daemon: bool = True) -> Optional[int]:
        """
        启动进程。

        Windows 特殊处理：
        - 使用 CREATE_NEW_PROCESS_GROUP 和 DETACHED_PROCESS 标志
        - 可选隐藏控制台窗口 (CREATE_NO_WINDOW)

        TODO: 实现具体逻辑。
        """
        raise NotImplementedError("Windows 进程启动尚未实现")

    def stop_process(self, pid: int) -> bool:
        """
        停止进程。

        方案：
        1. taskkill /PID {pid} /F
        2. 或 ctypes.windll.kernel32.TerminateProcess(handle, 0)

        TODO: 实现具体逻辑。
        """
        raise NotImplementedError("Windows 进程停止尚未实现")

    def is_process_alive(self, pid: int) -> bool:
        """
        检查进程是否存在。

        方案：
        1. ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, ...)
        2. 或 tasklist /FI "PID eq {pid}"

        TODO: 实现具体逻辑。
        """
        raise NotImplementedError("Windows 进程检查尚未实现")

    def find_process_by_name(self, name: str) -> Optional[int]:
        """
        按名称查找进程。

        方案：
        tasklist /FI "IMAGENAME eq {name}" /FO CSV /NH

        TODO: 实现具体逻辑。
        """
        raise NotImplementedError("Windows 进程查找尚未实现")
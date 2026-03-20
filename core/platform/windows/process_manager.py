"""
Windows 进程管理实现。
使用 subprocess + taskkill 实现进程生命周期管理。
"""
import os
import subprocess
from typing import Optional

from core.platform.base import ProcessManager


# Windows 进程创建标志
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


class WindowsProcessManager(ProcessManager):
    """Windows 进程管理器。"""

    def start_process(self, cmd: list, log_file: Optional[str] = None,
                      daemon: bool = True) -> Optional[int]:
        """
        启动进程，可选将输出重定向到日志文件。
        使用 CREATE_NO_WINDOW 避免弹出控制台窗口。
        """
        try:
            kwargs = {
                "creationflags": CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
            }

            if log_file:
                os.makedirs(os.path.dirname(log_file), exist_ok=True)
                fout = open(log_file, "a", encoding="utf-8")
                kwargs["stdout"] = fout
                kwargs["stderr"] = subprocess.STDOUT
            else:
                kwargs["stdout"] = subprocess.DEVNULL
                kwargs["stderr"] = subprocess.DEVNULL

            kwargs["stdin"] = subprocess.DEVNULL

            proc = subprocess.Popen(cmd, **kwargs)
            return proc.pid

        except FileNotFoundError:
            print(f"[ProcessManager] 可执行文件未找到: {cmd[0]}")
            return None
        except Exception as e:
            print(f"[ProcessManager] 启动进程失败: {e}")
            return None

    def stop_process(self, pid: int) -> bool:
        """使用 taskkill /F /PID 强制终止进程。"""
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True, text=True,
                creationflags=CREATE_NO_WINDOW,
            )
            return result.returncode == 0
        except Exception as e:
            print(f"[ProcessManager] 停止进程 {pid} 失败: {e}")
            return False

    def is_process_alive(self, pid: int) -> bool:
        """通过 tasklist 查询进程是否存在。"""
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True,
                creationflags=CREATE_NO_WINDOW,
            )
            # tasklist 输出包含 PID 则进程存在
            return str(pid) in result.stdout
        except Exception:
            return False

    def find_process_by_name(self, name: str) -> Optional[int]:
        """按进程名查找，返回第一个匹配的 PID。"""
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True,
                creationflags=CREATE_NO_WINDOW,
            )
            for line in result.stdout.strip().split("\n"):
                if name.lower() in line.lower():
                    # CSV 格式: "name","pid","session","session#","mem"
                    parts = line.strip().replace('"', '').split(",")
                    if len(parts) >= 2:
                        try:
                            return int(parts[1])
                        except ValueError:
                            continue
            return None
        except Exception:
            return None

    def stop_process_by_name(self, name: str) -> bool:
        """按名称终止所有匹配的进程。"""
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/IM", name],
                capture_output=True, text=True,
                creationflags=CREATE_NO_WINDOW,
            )
            return result.returncode == 0
        except Exception:
            return False
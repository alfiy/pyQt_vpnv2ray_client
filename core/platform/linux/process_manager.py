"""
Linux 进程管理实现。
使用 POSIX 信号和 pgrep 等 Linux 原生工具。
"""
import os
import signal
import subprocess
from typing import Optional

from core.platform.base import ProcessManager


class LinuxProcessManager(ProcessManager):
    """Linux 进程管理器实现。"""

    def start_process(self, cmd: list, log_file: Optional[str] = None,
                      daemon: bool = True) -> Optional[int]:
        """启动进程，可选重定向输出到日志文件。"""
        try:
            kwargs = {}
            if log_file:
                log_fh = open(log_file, "w")
                kwargs["stdout"] = log_fh
                kwargs["stderr"] = log_fh

            if daemon:
                kwargs["start_new_session"] = True

            process = subprocess.Popen(cmd, **kwargs)
            return process.pid
        except Exception as e:
            print(f"启动进程失败: {e}")
            return None

    def stop_process(self, pid: int) -> bool:
        """通过 SIGTERM -> SIGKILL 停止进程。"""
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return True  # 进程已不存在
        except OSError as e:
            print(f"SIGTERM 失败: {e}")
            # 尝试 kill 命令
            try:
                subprocess.run(["kill", str(pid)],
                               capture_output=True, timeout=5)
            except Exception:
                pass

        # 等待进程退出
        import time
        for _ in range(10):
            if not self.is_process_alive(pid):
                return True
            time.sleep(0.5)

        # SIGKILL 强制终止
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return True
        except OSError:
            try:
                subprocess.run(["kill", "-9", str(pid)],
                               capture_output=True, timeout=5)
            except Exception:
                pass

        import time
        time.sleep(1)
        return not self.is_process_alive(pid)

    def is_process_alive(self, pid: int) -> bool:
        """检查进程是否存在。"""
        try:
            os.kill(pid, 0)  # 信号 0 不实际发送，仅检查进程是否存在
            return True
        except (ProcessLookupError, PermissionError):
            return False
        except OSError:
            return False

    def find_process_by_name(self, name: str) -> Optional[int]:
        """使用 pgrep 按名称查找进程。"""
        try:
            result = subprocess.run(
                ["pgrep", "-f", name],
                capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip().split('\n')[0])
        except Exception:
            pass
        return None
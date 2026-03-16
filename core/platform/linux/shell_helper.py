"""
Linux Shell 辅助工具实现。
"""
import os
import subprocess
import tempfile

from core.platform.base import ShellHelper


class LinuxShellHelper(ShellHelper):
    """Linux Shell 辅助工具。"""

    def open_file_with_default_app(self, filepath: str) -> bool:
        """使用 xdg-open 打开文件。"""
        try:
            subprocess.Popen(["xdg-open", filepath])
            return True
        except Exception as e:
            print(f"xdg-open 打开文件失败: {e}")
            return False

    def open_url(self, url: str) -> bool:
        """使用 xdg-open 打开 URL。"""
        try:
            subprocess.Popen(["xdg-open", url])
            return True
        except Exception as e:
            print(f"xdg-open 打开 URL 失败: {e}")
            return False

    def check_command_exists(self, command: str) -> bool:
        """使用 which 检查命令是否存在。"""
        try:
            result = subprocess.run(
                ["which", command],
                capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False

    def get_temp_dir(self) -> str:
        """返回 /tmp 目录。"""
        return tempfile.gettempdir()
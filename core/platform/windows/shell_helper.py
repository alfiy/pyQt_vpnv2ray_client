"""
Windows Shell 辅助工具实现（骨架）。

TODO: 后续逐步填充具体实现。
"""
import os
import subprocess
import tempfile

from core.platform.base import ShellHelper


class WindowsShellHelper(ShellHelper):
    """
    Windows Shell 辅助工具。

    使用 os.startfile、start 命令、where 等 Windows 原生工具。
    """

    def open_file_with_default_app(self, filepath: str) -> bool:
        """
        使用系统默认应用打开文件。

        实现：os.startfile(filepath)

        TODO: 实现具体逻辑。
        """
        try:
            os.startfile(filepath)  # type: ignore[attr-defined]
            return True
        except AttributeError:
            # 非 Windows 平台 fallback
            try:
                subprocess.Popen(["start", filepath], shell=True)
                return True
            except Exception:
                return False
        except Exception as e:
            print(f"打开文件失败: {e}")
            return False

    def open_url(self, url: str) -> bool:
        """
        使用系统默认浏览器打开 URL。

        实现：os.startfile(url) 或 webbrowser.open(url)
        """
        try:
            import webbrowser
            webbrowser.open(url)
            return True
        except Exception as e:
            print(f"打开 URL 失败: {e}")
            return False

    def check_command_exists(self, command: str) -> bool:
        """
        使用 where 检查命令是否存在。

        TODO: 实现具体逻辑。
        """
        try:
            result = subprocess.run(
                ["where", command],
                capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False

    def get_temp_dir(self) -> str:
        """返回 Windows 临时目录。"""
        return tempfile.gettempdir()
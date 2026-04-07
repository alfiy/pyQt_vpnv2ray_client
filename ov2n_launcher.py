"""
ov2n VPN Client Launcher
========================
Shortcut target:
  pythonw.exe "C:\path\to\ov2n_launcher.py"

职责变更：
  旧版：launcher 提权 -> 整个 GUI 以管理员运行 -> 拖拽失败
  新版：launcher 以普通权限启动 GUI，提权由 process_manager 按需触发

  GUI 保持普通权限 -> 拖拽正常工作
  点击启动 VPN -> process_manager 弹 UAC -> admin_helper 以管理员运行
"""
import os
import subprocess
import sys


def find_python() -> str:
    d = os.path.dirname(sys.executable)
    py = os.path.join(d, "python.exe")
    if os.path.exists(py):
        return py
    import shutil
    found = shutil.which("python")
    return found if found else sys.executable


def main() -> None:
    app_dir = os.path.dirname(os.path.abspath(__file__))
    main_py = os.path.join(app_dir, "main.py")

    if not os.path.exists(main_py):
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            f"main.py not found:\n{main_py}",
            "ov2n",
            0x10,
        )
        sys.exit(1)

    # 普通权限启动 GUI，不提权
    # CREATE_NEW_PROCESS_GROUP (0x200): 子进程独立，父进程退出不影响子进程
    # CREATE_NO_WINDOW (0x8000000):     不弹控制台黑框
    proc = subprocess.Popen(
        [find_python(), main_py],
        cwd=app_dir,
        creationflags=0x00000200 | 0x08000000,
    )
    proc.wait()
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
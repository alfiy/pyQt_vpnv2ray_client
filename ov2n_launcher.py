"""
ov2n VPN Client Launcher
========================
替代 ov2n.vbs，避免 wscript.exe 触发杀毒误报。

使用方式：
  - 直接双击运行（需关联 pythonw.exe 或 python.exe）
  - 或在桌面快捷方式中指向此文件：
      目标: pythonw.exe "C:\path\to\ov2n_launcher.py"

原理：
  - 不使用 wscript.exe / cscript.exe
  - 不使用 cmd /c start /b（隐藏窗口启动）
  - 使用 subprocess.Popen 以 DETACHED 方式启动 main.py
  - 进程可在任务管理器中正常看到，行为透明
"""

import sys
import os
import subprocess

def find_python() -> str:
    """
    找到系统中可用的 pythonw.exe（无控制台窗口）。
    优先用与本启动器相同的解释器，保证依赖一致。
    """
    # 1. 优先使用当前解释器同目录下的 pythonw.exe
    current_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(current_dir, "pythonw.exe")
    if os.path.exists(pythonw):
        return pythonw

    # 2. 回退：尝试 PATH 中的 pythonw
    import shutil
    found = shutil.which("pythonw")
    if found:
        return found

    # 3. 最后回退：用当前解释器（会有短暂黑框）
    return sys.executable


def main():
    # 本文件所在目录即应用根目录
    app_dir = os.path.dirname(os.path.abspath(__file__))
    main_py = os.path.join(app_dir, "main.py")

    if not os.path.exists(main_py):
        # 只有找不到文件时才弹窗，正常启动全程无 UI
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            f"main.py 未找到：\n{main_py}",
            "ov2n 启动失败",
            0x10,  # MB_ICONERROR
        )
        sys.exit(1)

    pythonw = find_python()

    # DETACHED_PROCESS: 子进程脱离当前进程组，关闭启动器后 main.py 继续运行
    # CREATE_NO_WINDOW: 不创建控制台窗口（pythonw 本身已无窗口，双保险）
    DETACHED_PROCESS = 0x00000008
    CREATE_NO_WINDOW = 0x08000000

    subprocess.Popen(
        [pythonw, main_py],
        cwd=app_dir,
        creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
        # 不捕获 stdout/stderr，让 main.py 自己管理日志
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # 启动器立即退出，main.py 在后台独立运行
    sys.exit(0)


if __name__ == "__main__":
    main()
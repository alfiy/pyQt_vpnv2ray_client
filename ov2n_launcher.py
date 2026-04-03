r"""
ov2n VPN Client Launcher
========================
Shortcut target:
  pythonw.exe "C:\path\to\ov2n_launcher.py"

提权流程：
  1. 普通权限启动 -> 检测到非管理员
  2. ShellExecuteW runas 触发 Windows 标准 UAC 弹窗
  3. 用户点「是」-> Windows 以管理员权限重新运行本脚本
  4. 检测到已是管理员 -> subprocess.Popen 启动 main.py 后退出

os.execv 在 Windows 上不可靠（管理员 token 不继承），
改用 subprocess.Popen 继承当前进程的管理员权限。
"""
import ctypes
import os
import subprocess
import sys


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def find_pythonw() -> str:
    d = os.path.dirname(sys.executable)
    pw = os.path.join(d, "pythonw.exe")
    if os.path.exists(pw):
        return pw
    import shutil
    found = shutil.which("pythonw")
    return found if found else sys.executable


def elevate_and_restart(script: str, app_dir: str) -> None:
    """触发 UAC 弹窗，以管理员身份重新运行本脚本。"""
    pythonw = find_pythonw()

    # ShellExecuteW(hwnd, verb, file, params, dir, show)
    # runas -> 触发系统 UAC 弹窗，Windows 负责提权，行为完全透明
    ret = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        pythonw,
        f'"{script}"',
        app_dir,
        1,          # SW_SHOWNORMAL
    )

    if ret <= 32:
        ctypes.windll.user32.MessageBoxW(
            0,
            "ov2n 需要管理员权限才能管理 VPN 网络接口。\n\n"
            "请在 UAC 弹窗中点击「是」，\n"
            "或右键桌面快捷方式选择「以管理员身份运行」。",
            "ov2n - 需要管理员权限",
            0x30,   # MB_ICONWARNING
        )

    # 无论 UAC 成功与否，当前非管理员进程退出
    sys.exit(0)


def main() -> None:
    script  = os.path.abspath(__file__)
    app_dir = os.path.dirname(script)
    main_py = os.path.join(app_dir, "main.py")

    if not os.path.exists(main_py):
        ctypes.windll.user32.MessageBoxW(
            0,
            f"main.py not found:\n{main_py}",
            "ov2n",
            0x10,   # MB_ICONERROR
        )
        sys.exit(1)

    if not is_admin():
        # 非管理员 -> 触发 UAC，以管理员重新运行本脚本
        elevate_and_restart(script, app_dir)
        # 上面内部调用 sys.exit，此行不会执行

    # 已是管理员 -> 用 subprocess.Popen 启动 main.py
    # 不加任何 creationflags，直接继承当前进程的管理员 token
    pythonw = find_pythonw()
    subprocess.Popen(
        [pythonw, main_py],
        cwd=app_dir,
    )
    # launcher 使命完成，退出
    sys.exit(0)


if __name__ == "__main__":
    main()
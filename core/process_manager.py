"""
ov2n Process Manager - 跨平台进程管理器
"""
import json
import logging
import os
import platform
import secrets
import sys
import time
from pathlib import Path
from threading import Lock
from typing import Callable, Optional

log = logging.getLogger("ov2n.process_manager")
IS_WINDOWS = platform.system() == "Windows"

# ==================== Windows 实现 ====================

class _WindowsProcessManager:
    """Windows: 命名管道 + ShellExecuteW runas"""

    def __init__(self, app_root: Path):
        self.app_root = app_root
        self._token = secrets.token_hex(8)
        self._pipe_name = r"\\.\pipe\ov2n_" + self._token
        self._lock = Lock()
        self._helper_started = False
        self._ready_file = Path(os.environ.get("TEMP", "C:/Temp")) / f"ov2n_ready_{self._token}.txt"
        self.xray_pid: int = 0
        self.openvpn_pid: int = 0
        log.info("ProcessManager(Windows) init, pipe=%s", self._pipe_name)

    def ensure_helper_running(self) -> bool:
        if self._helper_started and self._ready_file.exists():
            return True
        return self._start_helper()

    def send_command(self, cmd: dict, on_log: Optional[Callable[[str], None]] = None) -> dict:
        with self._lock:
            if not self.ensure_helper_running():
                return {"ok": False, "message": "admin_helper 启动失败，请检查是否授权了 UAC"}
            return self._pipe_call(cmd, on_log)

    def stop_helper(self) -> None:
        try:
            with self._lock:
                self._pipe_call({"action": "exit"})
        except Exception:
            pass
        self._helper_started = False
        self._ready_file.unlink(missing_ok=True)

    def is_helper_running(self) -> bool:
        return self._helper_started and self._ready_file.exists()

    def _start_helper(self) -> bool:
        import ctypes
        helper_script = self.app_root / "core" / "admin_helper.py"
        if not helper_script.exists():
            log.error("admin_helper.py not found: %s", helper_script)
            return False

        pythonw = self._find_pythonw()
        params = f'"{helper_script}" --pipe-name {self._pipe_name}'

        log.info("launching admin_helper via ShellExecuteW runas...")
        self._ready_file.unlink(missing_ok=True)

        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", pythonw, params, str(self.app_root), 0,
        )
        if ret <= 32:
            log.error("ShellExecuteW failed: %d", ret)
            return False

        for i in range(60):  # 30秒超时
            if self._ready_file.exists():
                self._helper_started = True
                return True
            time.sleep(0.5)

        log.error("admin_helper did not become ready within 30s")
        return False

    def _pipe_call(self, cmd: dict, on_log: Optional[Callable[[str], None]] = None) -> dict:
        import ctypes
        import ctypes.wintypes as wintypes
        kernel32 = ctypes.windll.kernel32

        GENERIC_READ_WRITE = 0xC0000000
        OPEN_EXISTING = 3
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
        ERROR_PIPE_BUSY = 231
        PIPE_TIMEOUT_MS = 10000

        pipe = INVALID_HANDLE_VALUE
        deadline = time.time() + PIPE_TIMEOUT_MS / 1000
        while time.time() < deadline:
            pipe = kernel32.CreateFileW(
                self._pipe_name, GENERIC_READ_WRITE, 0, None, OPEN_EXISTING, 0, None,
            )
            if pipe != INVALID_HANDLE_VALUE:
                break
            err = kernel32.GetLastError()
            if err == ERROR_PIPE_BUSY:
                kernel32.WaitNamedPipeW(self._pipe_name, 1000)
            else:
                return {"ok": False, "message": f"cannot connect to pipe (err={err})"}

        if pipe == INVALID_HANDLE_VALUE:
            return {"ok": False, "message": "pipe connect timeout"}

        try:
            cmd_bytes = json.dumps(cmd).encode("utf-8")
            bytes_written = wintypes.DWORD(0)
            ok = kernel32.WriteFile(pipe, cmd_bytes, len(cmd_bytes), ctypes.byref(bytes_written), None)
            if not ok:
                return {"ok": False, "message": f"WriteFile failed"}

            buf = ctypes.create_string_buffer(65536)
            bytes_read = wintypes.DWORD(0)
            ok = kernel32.ReadFile(pipe, buf, 65536, ctypes.byref(bytes_read), None)
            if not ok:
                return {"ok": False, "message": f"ReadFile failed"}

            raw = buf.raw[:bytes_read.value].decode("utf-8")
            response = json.loads(raw)
            if on_log and "message" in response:
                on_log(response["message"])
            return response

        except Exception as e:
            log.exception("pipe_call error")
            return {"ok": False, "message": str(e)}
        finally:
            kernel32.CloseHandle(pipe)

    @staticmethod
    def _find_pythonw() -> str:
        d = os.path.dirname(sys.executable)
        pw = os.path.join(d, "pythonw.exe")
        if os.path.exists(pw):
            return pw
        import shutil
        found = shutil.which("pythonw")
        return found if found else sys.executable


# ==================== Linux 实现 ====================

class _LinuxProcessManager:
    """Linux: 直接调用 vpn_helper.py + pkexec"""

    def __init__(self, app_root: Path):
        self.app_root = app_root
        self._lock = Lock()
        self.xray_pid: int = 0
        self.openvpn_pid: int = 0
        self._vpn_helper = self.app_root / "polkit" / "vpn_helper.py"
        log.info("ProcessManager(Linux) init, app_root=%s", app_root)

    def _run_vpn_helper(self, args: list, on_log: Optional[Callable[[str], None]] = None) -> tuple:
        """使用 pkexec 运行 vpn_helper.py"""
        import subprocess

        if not self._vpn_helper.exists():
            log.error("vpn_helper.py not found: %s", self._vpn_helper)
            return False, "vpn_helper.py not found"

        cmd = ["pkexec", sys.executable, str(self._vpn_helper)] + args
        log.info("Running: %s", " ".join(cmd))

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            output = result.stdout + result.stderr

            if on_log and output:
                on_log(output)

            if result.returncode == 0:
                log.info("vpn_helper succeeded")
                return True, output
            else:
                log.error("vpn_helper failed (code %d): %s", result.returncode, output[:500])
                return False, output

        except subprocess.TimeoutExpired:
            log.error("vpn_helper timed out")
            return False, "Command timed out"
        except Exception as e:
            log.exception("vpn_helper execution failed")
            return False, str(e)

    def _parse_pid(self, output: str) -> int:
        """从输出解析 PID"""
        for line in output.split("\n"):
            if "PID:" in line:
                try:
                    return int(line.split("PID:")[-1].strip().split()[0])
                except (ValueError, IndexError):
                    continue
        return 0

    def ensure_helper_running(self) -> bool:
        """Linux 不需要常驻 helper"""
        return self._vpn_helper.exists()

    def send_command(self, cmd: dict, on_log: Optional[Callable[[str], None]] = None) -> dict:
        """命令分发"""
        with self._lock:
            action = cmd.get("action", "")

            if action == "ping":
                return {"ok": True, "message": "pong"}

            elif action == "start_xray":
                config = cmd.get("config")
                if not config:
                    return {"ok": False, "message": "config required"}
                success, output = self._run_vpn_helper(["start-v2ray-only", config], on_log)
                if success:
                    self.xray_pid = self._parse_pid(output)
                return {"ok": success, "pid": self.xray_pid, "message": "xray started" if success else output}

            elif action == "stop_xray":
                if self.xray_pid:
                    success, output = self._run_vpn_helper(["stop", "--v2ray-pid", str(self.xray_pid)], on_log)
                    if success:
                        self.xray_pid = 0
                    return {"ok": success, "message": output}
                return {"ok": True, "message": "not running"}

            elif action == "start_openvpn":
                config = cmd.get("config")
                if not config:
                    return {"ok": False, "message": "config required"}
                success, output = self._run_vpn_helper(["start-vpn-only", config], on_log)
                if success:
                    self.openvpn_pid = self._parse_pid(output)
                return {"ok": success, "pid": self.openvpn_pid, "message": "openvpn started" if success else output}

            elif action == "stop_openvpn":
                if self.openvpn_pid:
                    success, output = self._run_vpn_helper(["stop", "--openvpn-pid", str(self.openvpn_pid)], on_log)
                    if success:
                        self.openvpn_pid = 0
                    return {"ok": success, "message": output}
                return {"ok": True, "message": "not running"}

            elif action == "stop_all":
                args = ["stop"]
                if self.openvpn_pid:
                    args.extend(["--openvpn-pid", str(self.openvpn_pid)])
                if self.xray_pid:
                    args.extend(["--v2ray-pid", str(self.xray_pid)])

                if len(args) > 1:
                    success, output = self._run_vpn_helper(args, on_log)
                    if success:
                        self.openvpn_pid = 0
                        self.xray_pid = 0
                    return {"ok": success, "message": output}
                return {"ok": True, "message": "nothing to stop"}

            elif action == "status":
                return {
                    "ok": True,
                    "xray_running": self.xray_pid > 0,
                    "xray_pid": self.xray_pid,
                    "openvpn_running": self.openvpn_pid > 0,
                    "openvpn_pid": self.openvpn_pid,
                }

            elif action == "exit":
                return {"ok": True, "message": "bye", "_exit": True}

            else:
                return {"ok": False, "message": f"unknown action: {action}"}

    def stop_helper(self) -> None:
        """停止所有 VPN 进程"""
        self.send_command({"action": "stop_all"})

    def is_helper_running(self) -> bool:
        """检查 vpn_helper.py 是否存在"""
        return self._vpn_helper.exists()


# ==================== 工厂函数 ====================

def ProcessManager(app_root: Path):
    """工厂函数，根据平台返回对应实现"""
    if IS_WINDOWS:
        return _WindowsProcessManager(app_root)
    else:
        return _LinuxProcessManager(app_root)
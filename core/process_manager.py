"""
ov2n Process Manager
====================
GUI 侧的进程管理器，运行在普通权限下。跨平台支持：
  Windows: 命名管道 IPC + ShellExecuteW runas 提权
  Linux:   Unix domain socket IPC + pkexec 提权

职责：
  - 按需启动 admin_helper.py（提权）
  - 通过 IPC 向 admin_helper 发送命令
  - 将 admin_helper 的响应回调给调用方
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

BUFFER_SIZE     = 65536
CONNECT_TIMEOUT = 30      # 等待 admin_helper 启动的最长秒数
PIPE_TIMEOUT_MS = 10000   # 单次管道操作超时（毫秒）


# ---------------------------------------------------------------------------
# Windows 实现
# ---------------------------------------------------------------------------

class _WindowsProcessManager:
    """Windows 命名管道 + ShellExecuteW runas 实现。"""

    def __init__(self, app_root: Path):
        self.app_root = app_root
        self._token = secrets.token_hex(8)
        self._pipe_name = r"\\.\pipe\ov2n_" + self._token
        self._lock = Lock()
        self._helper_started = False
        self._ready_file = (
            Path(os.environ.get("TEMP", "C:/Temp"))
            / f"ov2n_ready_{self._token}.txt"
        )
        self.xray_pid: int = 0
        self.openvpn_pid: int = 0
        log.info("ProcessManager(Windows) init, pipe=%s", self._pipe_name)

    def ensure_helper_running(self) -> bool:
        if self._helper_started and self._ready_file.exists():
            return True
        return self._start_helper()

    def send_command(self, cmd: dict,
                     on_log: Optional[Callable[[str], None]] = None) -> dict:
        with self._lock:
            if not self.ensure_helper_running():
                return {"ok": False,
                        "message": "admin_helper 启动失败，请检查是否授权了 UAC"}
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

        log.info("waiting for admin_helper ready (max %ds)...", CONNECT_TIMEOUT)
        for i in range(CONNECT_TIMEOUT * 2):
            if self._ready_file.exists():
                log.info("admin_helper ready after %.1fs", i * 0.5)
                self._helper_started = True
                return True
            time.sleep(0.5)

        log.error("admin_helper did not become ready within %ds", CONNECT_TIMEOUT)
        return False

    def _pipe_call(self, cmd: dict,
                   on_log: Optional[Callable[[str], None]] = None) -> dict:
        import ctypes
        import ctypes.wintypes as wintypes
        kernel32 = ctypes.windll.kernel32

        GENERIC_READ_WRITE   = 0xC0000000
        OPEN_EXISTING        = 3
        FILE_FLAG_NONE       = 0
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
        ERROR_PIPE_BUSY      = 231

        pipe = INVALID_HANDLE_VALUE
        deadline = time.time() + PIPE_TIMEOUT_MS / 1000
        while time.time() < deadline:
            pipe = kernel32.CreateFileW(
                self._pipe_name, GENERIC_READ_WRITE,
                0, None, OPEN_EXISTING, FILE_FLAG_NONE, None,
            )
            if pipe != INVALID_HANDLE_VALUE:
                break
            err = kernel32.GetLastError()
            if err == ERROR_PIPE_BUSY:
                kernel32.WaitNamedPipeW(self._pipe_name, 1000)
            else:
                return {"ok": False,
                        "message": f"cannot connect to pipe (err={err})"}

        if pipe == INVALID_HANDLE_VALUE:
            return {"ok": False, "message": "pipe connect timeout"}

        try:
            cmd_bytes = json.dumps(cmd).encode("utf-8")
            bytes_written = wintypes.DWORD(0)
            ok = kernel32.WriteFile(
                pipe, cmd_bytes, len(cmd_bytes),
                ctypes.byref(bytes_written), None)
            if not ok:
                return {"ok": False,
                        "message": f"WriteFile failed (err={kernel32.GetLastError()})"}

            buf = ctypes.create_string_buffer(BUFFER_SIZE)
            bytes_read = wintypes.DWORD(0)
            ok = kernel32.ReadFile(
                pipe, buf, BUFFER_SIZE, ctypes.byref(bytes_read), None)
            if not ok:
                return {"ok": False,
                        "message": f"ReadFile failed (err={kernel32.GetLastError()})"}

            raw = buf.raw[:bytes_read.value].decode("utf-8")
            log.debug("pipe response: %s", raw[:300])
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


# ---------------------------------------------------------------------------
# Linux 实现
# ---------------------------------------------------------------------------

class _LinuxProcessManager:
    """
    Linux Unix domain socket + pkexec 实现。
    接口与 _WindowsProcessManager 完全一致，调用方无需关心平台差异。
    """

    def __init__(self, app_root: Path):
        self.app_root = app_root
        self._token = secrets.token_hex(8)
        self._socket_path = Path(f"/tmp/ov2n_{self._token}.sock")
        self._lock = Lock()
        self._helper_started = False
        self.xray_pid: int = 0
        self.openvpn_pid: int = 0
        log.info("ProcessManager(Linux) init, socket=%s", self._socket_path)

    def ensure_helper_running(self) -> bool:
        if self._helper_started and self._socket_path.exists():
            return True
        return self._start_helper()

    def send_command(self, cmd: dict,
                     on_log: Optional[Callable[[str], None]] = None) -> dict:
        with self._lock:
            if not self.ensure_helper_running():
                return {"ok": False, "message": "admin_helper 启动失败"}
            return self._socket_call(cmd, on_log)

    def stop_helper(self) -> None:
        try:
            with self._lock:
                self._socket_call({"action": "exit"})
        except Exception:
            pass
        self._helper_started = False
        self._socket_path.unlink(missing_ok=True)

    def is_helper_running(self) -> bool:
        return self._helper_started and self._socket_path.exists()

    def _start_helper(self) -> bool:
        import subprocess
        helper_script = self.app_root / "core" / "admin_helper.py"
        if not helper_script.exists():
            log.error("admin_helper.py not found: %s", helper_script)
            return False

        python_exe = sys.executable
        cmd = ["pkexec", python_exe, str(helper_script),
               "--socket-path", str(self._socket_path)]

        log.info("launching admin_helper via pkexec...")
        try:
            subprocess.Popen(
                cmd,
                cwd=str(self.app_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            log.warning("pkexec not found, trying sudo...")
            cmd[0] = "sudo"
            try:
                subprocess.Popen(
                    cmd,
                    cwd=str(self.app_root),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as e:
                log.error("sudo also failed: %s", e)
                return False

        log.info("waiting for admin_helper socket (max %ds)...", CONNECT_TIMEOUT)
        for i in range(CONNECT_TIMEOUT * 2):
            if self._socket_path.exists():
                log.info("admin_helper socket ready after %.1fs", i * 0.5)
                self._helper_started = True
                return True
            time.sleep(0.5)

        log.error("admin_helper socket not created within %ds", CONNECT_TIMEOUT)
        return False

    def _socket_call(self, cmd: dict,
                     on_log: Optional[Callable[[str], None]] = None) -> dict:
        import socket as _socket
        try:
            with _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM) as s:
                s.settimeout(PIPE_TIMEOUT_MS / 1000)
                s.connect(str(self._socket_path))

                cmd_bytes = json.dumps(cmd).encode("utf-8")
                length = len(cmd_bytes).to_bytes(4, "big")
                s.sendall(length + cmd_bytes)

                raw_len = self._recv_exact(s, 4)
                if raw_len is None:
                    return {"ok": False, "message": "socket read length failed"}
                resp_len = int.from_bytes(raw_len, "big")

                raw = self._recv_exact(s, resp_len)
                if raw is None:
                    return {"ok": False, "message": "socket read body failed"}

                response = json.loads(raw.decode("utf-8"))
                if on_log and "message" in response:
                    on_log(response["message"])
                return response

        except Exception as e:
            log.exception("socket_call error")
            return {"ok": False, "message": str(e)}

    @staticmethod
    def _recv_exact(s, n: int) -> Optional[bytes]:
        buf = b""
        while len(buf) < n:
            chunk = s.recv(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf


# ---------------------------------------------------------------------------
# 工厂函数：根据平台返回对应实现
# ---------------------------------------------------------------------------

def ProcessManager(app_root: Path):
    """
    工厂函数，根据当前平台返回对应的进程管理器实现。
    对外接口完全一致，调用方无需关心平台差异：
      mgr = ProcessManager(app_root)
      result = mgr.send_command({"action": "start_xray", "config": "..."})
    """
    if IS_WINDOWS:
        return _WindowsProcessManager(app_root)
    else:
        return _LinuxProcessManager(app_root)
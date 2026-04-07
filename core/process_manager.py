"""
ov2n Process Manager
====================
GUI 侧的进程管理器，运行在普通权限下。

职责：
  - 按需启动 admin_helper.py（通过 ShellExecuteW runas 提权）
  - 通过 Windows Named Pipe 向 admin_helper 发送命令
  - 将 admin_helper 的响应回调给调用方

架构：
  GUI (普通权限)
    └── ProcessManager
          ├── 启动 admin_helper.py (ShellExecuteW runas -> 管理员)
          ├── 命名管道 IPC 通信
          └── 命令：start_xray / stop_xray / start_openvpn / stop_openvpn

线程安全：
  send_command() 可以从任意线程调用，内部加锁串行化管道访问。
"""
import ctypes
import ctypes.wintypes as wintypes
import json
import logging
import os
import secrets
import sys
import time
from pathlib import Path
from threading import Lock
from typing import Callable, Dict, Optional

log = logging.getLogger("ov2n.process_manager")

PIPE_PREFIX = r"\\.\pipe\ov2n_admin_"
BUFFER_SIZE = 65536
CONNECT_TIMEOUT = 30    # 等待 admin_helper 启动的最长秒数
PIPE_TIMEOUT_MS = 10000 # 单次管道操作超时（毫秒）


class ProcessManager:
    """
    GUI 侧进程管理器。

    使用方式：
        mgr = ProcessManager(app_root)
        result = mgr.send_command({"action": "start_xray", "config": "..."})
        # result: {"ok": True, "pid": 1234, "message": "xray started"}
    """

    def __init__(self, app_root: Path):
        self.app_root = app_root
        self._token = secrets.token_hex(8)          # 随机 token，防伪造
        self._pipe_name =  r"\\.\pipe\ov2n_" + self._token
        self._lock = Lock()
        self._helper_started = False
        self._ready_file = Path(os.environ.get("TEMP", "C:/Temp")) / f"ov2n_ready_{self._token}.txt"

        # 状态缓存（由 GUI 线程维护）
        self.xray_pid: int = 0
        self.openvpn_pid: int = 0

        log.info("ProcessManager init, pipe=%s", self._pipe_name)

    # ── 公开接口 ──────────────────────────────

    def ensure_helper_running(self) -> bool:
        """
        确保 admin_helper 已启动并就绪。
        首次调用时通过 ShellExecuteW runas 启动，之后复用。
        返回 True 表示 helper 就绪。
        """
        if self._helper_started and self._ready_file.exists():
            return True

        return self._start_helper()

    def send_command(self, cmd: dict,
                     on_log: Optional[Callable[[str], None]] = None) -> dict:
        """
        向 admin_helper 发送命令，返回响应字典。

        Args:
            cmd:    命令字典，如 {"action": "start_xray", "config": "..."}
            on_log: 可选回调，接收日志字符串

        Returns:
            响应字典，如 {"ok": True, "pid": 123, "message": "..."}
            失败时返回 {"ok": False, "message": "错误原因"}
        """
        with self._lock:
            if not self.ensure_helper_running():
                return {"ok": False, "message": "admin_helper 启动失败，请检查是否授权了 UAC"}

            return self._pipe_call(cmd, on_log)

    def stop_helper(self) -> None:
        """向 admin_helper 发送 exit 命令，清理资源。"""
        try:
            with self._lock:
                self._pipe_call({"action": "exit"})
        except Exception:
            pass
        self._helper_started = False
        self._ready_file.unlink(missing_ok=True)

    def is_helper_running(self) -> bool:
        """检查 admin_helper 是否仍在运行。"""
        return self._helper_started and self._ready_file.exists()

    # ── 内部实现 ──────────────────────────────
    def _start_helper(self) -> bool:
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
        """
        通过命名管道发送命令并接收响应。
        使用 CreateFile + WriteFile + ReadFile 实现，不依赖 pywin32。
        """
        kernel32 = ctypes.windll.kernel32

        GENERIC_READ_WRITE   = 0xC0000000
        OPEN_EXISTING        = 3
        FILE_FLAG_NONE       = 0
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
        ERROR_PIPE_BUSY      = 231

        # 重试连接管道（WaitNamedPipe + CreateFile 之间存在竞争窗口，需循环重试）
        pipe = INVALID_HANDLE_VALUE
        deadline = time.time() + PIPE_TIMEOUT_MS / 1000
        while time.time() < deadline:
            pipe = kernel32.CreateFileW(
                self._pipe_name,
                GENERIC_READ_WRITE,
                0, None,
                OPEN_EXISTING,
                FILE_FLAG_NONE,
                None,
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
            # 发送命令
            cmd_bytes = json.dumps(cmd).encode("utf-8")
            bytes_written = wintypes.DWORD(0)
            ok = kernel32.WriteFile(
                pipe, cmd_bytes, len(cmd_bytes),
                ctypes.byref(bytes_written), None)
            if not ok:
                err = kernel32.GetLastError()
                return {"ok": False, "message": f"WriteFile failed (err={err})"}

            # 读取响应
            buf = ctypes.create_string_buffer(BUFFER_SIZE)
            bytes_read = wintypes.DWORD(0)
            ok = kernel32.ReadFile(
                pipe, buf, BUFFER_SIZE,
                ctypes.byref(bytes_read), None)
            if not ok:
                err = kernel32.GetLastError()
                return {"ok": False, "message": f"ReadFile failed (err={err})"}

            raw = buf.raw[:bytes_read.value].decode("utf-8")
            log.debug("pipe response: %s", raw[:300])

            response = json.loads(raw)

            # 透传日志
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
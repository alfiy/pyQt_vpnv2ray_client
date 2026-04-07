"""
ov2n Process Manager - 跨平台进程管理器（支持 TProxy）
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


# ==================== Linux 实现（支持 TProxy） ====================

class _LinuxProcessManager:
    """Linux: 直接调用 vpn_helper.py + pkexec，支持 TProxy 透明代理"""

    def __init__(self, app_root: Path):
        self.app_root = app_root
        self._lock = Lock()
        self.xray_pid: int = 0
        self.openvpn_pid: int = 0
        self._tproxy_configured = False
        self._vps_ip: Optional[str] = None

        # 尝试多个可能的路径
        possible_paths = [
            app_root / "polkit" / "vpn_helper.py",
            app_root / "core" / "vpn_helper.py",
            app_root / "vpn_helper.py",
            Path("/usr/local/lib/ov2n/polkit/vpn_helper.py"),
            Path("/usr/local/lib/ov2n/core/vpn_helper.py"),
        ]

        self._vpn_helper = None
        for path in possible_paths:
            log.info("Checking vpn_helper path: %s (exists=%s)", path, path.exists())
            if path.exists():
                self._vpn_helper = path
                log.info("Found vpn_helper at: %s", path)
                break

        if self._vpn_helper is None:
            self._vpn_helper = app_root / "polkit" / "vpn_helper.py"
            log.error("vpn_helper.py not found in any of: %s", [str(p) for p in possible_paths])

        log.info("ProcessManager(Linux) init, app_root=%s, vpn_helper=%s", app_root, self._vpn_helper)

    def _run_vpn_helper(self, args: list, on_log: Optional[Callable[[str], None]] = None) -> tuple:
        """使用 pkexec 运行 vpn_helper.py"""
        import subprocess

        if self._vpn_helper is None or not self._vpn_helper.exists():
            error_msg = f"vpn_helper.py not found at {self._vpn_helper}"
            log.error(error_msg)
            if self._vpn_helper:
                parent = self._vpn_helper.parent
                if parent.exists():
                    log.info("Contents of %s: %s", parent, list(parent.iterdir()))
            return False, error_msg

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

    def _setup_tproxy(self, vps_ip: str, v2ray_port: int = 12345, on_log: Optional[Callable[[str], None]] = None) -> bool:
        """配置 TProxy 透明代理"""
        if not vps_ip:
            log.error("VPS IP not provided, cannot setup TProxy")
            return False

        log.info("Setting up TProxy with VPS IP: %s, port: %d", vps_ip, v2ray_port)
        success, output = self._run_vpn_helper([
            "tproxy-start",
            "--vps-ip", vps_ip,
            "--port", str(v2ray_port)
        ], on_log)

        if success and "TPROXY_STATUS: OK" in output:
            log.info("TProxy setup successfully")
            self._tproxy_configured = True
            return True
        else:
            log.error("TProxy setup failed: %s", output)
            return False

    def _cleanup_tproxy(self, v2ray_port: int = 12345, on_log: Optional[Callable[[str], None]] = None) -> bool:
        """清理 TProxy 配置"""
        log.info("Cleaning up TProxy")
        success, output = self._run_vpn_helper([
            "tproxy-stop",
            "--port", str(v2ray_port)
        ], on_log)

        if success:
            self._tproxy_configured = False
            return True
        return False

    def ensure_helper_running(self) -> bool:
        """Linux 不需要常驻 helper"""
        return self._vpn_helper is not None and self._vpn_helper.exists()

    def send_command(self, cmd: dict, on_log: Optional[Callable[[str], None]] = None) -> dict:
        """命令分发"""
        with self._lock:
            action = cmd.get("action", "")

            if action == "ping":
                return {"ok": True, "message": "pong"}

            elif action == "start_xray":
                config = cmd.get("config")
                vps_ip = cmd.get("vps_ip") or self._vps_ip
                v2ray_port = cmd.get("v2ray_port", 12345)

                if not config:
                    return {"ok": False, "message": "config required"}

                # 保存 VPS IP 供后续使用
                if vps_ip:
                    self._vps_ip = vps_ip

                # 1. 启动 V2Ray
                success, output = self._run_vpn_helper(["start-v2ray-only", config], on_log)
                if not success:
                    return {"ok": False, "pid": 0, "message": output}

                self.xray_pid = self._parse_pid(output)

                # 2. 配置 TProxy（如果提供了 VPS IP）
                if vps_ip:
                    tproxy_ok = self._setup_tproxy(vps_ip, v2ray_port, on_log)
                    if not tproxy_ok:
                        # TProxy 失败，停止 V2Ray
                        self._run_vpn_helper(["stop", "--v2ray-pid", str(self.xray_pid)])
                        self.xray_pid = 0
                        return {"ok": False, "pid": 0, "message": "V2Ray started but TProxy setup failed"}

                return {
                    "ok": True, 
                    "pid": self.xray_pid,
                    "message": "xray and tproxy started" if vps_ip else "xray started (no tproxy)"
                }

            elif action == "stop_xray":
                # 先清理 TProxy，再停止 V2Ray
                if self._tproxy_configured:
                    self._cleanup_tproxy(on_log=on_log)

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
                # 先清理 TProxy
                if self._tproxy_configured:
                    self._cleanup_tproxy(on_log=on_log)

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
                    "tproxy_configured": self._tproxy_configured,
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
        return self._vpn_helper is not None and self._vpn_helper.exists()


# ==================== 工厂函数 ====================

def ProcessManager(app_root: Path):
    """工厂函数，根据平台返回对应实现"""
    if IS_WINDOWS:
        return _WindowsProcessManager(app_root)
    else:
        return _LinuxProcessManager(app_root)
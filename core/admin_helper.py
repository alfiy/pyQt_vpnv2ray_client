"""
ov2n Admin Helper
=================
以管理员/root 权限运行的后台进程，无窗口，无 GUI。跨平台支持：
  Windows: 命名管道服务端
  Linux:   Unix domain socket 服务端

使用方式（由 process_manager.py 自动调用）：
  Windows: pythonw.exe admin_helper.py --pipe-name <name>
  Linux:   pkexec python3 admin_helper.py --socket-path <path>
"""
import json
import logging
import os
import platform
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

IS_WINDOWS = platform.system() == "Windows"

BUFFER_SIZE = 65536


# ---------------------------------------------------------------------------
# 日志：写到文件（pythonw/pkexec 均无控制台）
# ---------------------------------------------------------------------------

def _setup_logging():
    log_file = Path(os.environ.get("TEMP", "/tmp")) / "ov2n_admin_helper.log"
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [admin_helper] %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    return logging.getLogger("ov2n.admin_helper")


log = logging.getLogger("ov2n.admin_helper")


# ---------------------------------------------------------------------------
# 命令处理（平台无关）
# ---------------------------------------------------------------------------

class CommandHandler:
    def __init__(self):
        from core.vpn_process import create_managers
        self.openvpn_mgr, self.xray_mgr = create_managers(_ROOT)
        log.info("managers initialized, app_root=%s", _ROOT)

    def handle(self, cmd: dict) -> dict:
        action = cmd.get("action", "")
        log.info("handle: %s", action)
        try:
            if action == "ping":
                return {"ok": True, "message": "pong"}

            elif action == "start_xray":
                config_path = cmd.get("config")
                p = Path(config_path) if config_path else None
                ok = self.xray_mgr.start(p)
                pid = self.xray_mgr.get_pid() or 0
                return {"ok": ok, "pid": pid,
                        "message": "xray started" if ok else "xray start failed"}

            elif action == "stop_xray":
                self.xray_mgr.stop()
                return {"ok": True, "message": "xray stopped"}

            elif action == "start_openvpn":
                config_path = cmd.get("config")
                if not config_path or not Path(config_path).exists():
                    return {"ok": False, "message": f"config not found: {config_path}"}
                ok = self.openvpn_mgr.start(Path(config_path))
                pid = self.openvpn_mgr.get_pid() or 0
                return {"ok": ok, "pid": pid,
                        "message": "openvpn started" if ok else "openvpn start failed"}

            elif action == "stop_openvpn":
                self.openvpn_mgr.stop()
                return {"ok": True, "message": "openvpn stopped"}

            elif action == "stop_all":
                self.xray_mgr.stop()
                self.openvpn_mgr.stop()
                return {"ok": True, "message": "all stopped"}

            elif action == "status":
                return {
                    "ok": True,
                    "xray_running": self.xray_mgr.is_running,
                    "xray_pid": self.xray_mgr.get_pid() or 0,
                    "openvpn_running": self.openvpn_mgr.is_running,
                    "openvpn_pid": self.openvpn_mgr.get_pid() or 0,
                }

            elif action == "exit":
                return {"ok": True, "message": "bye", "_exit": True}

            else:
                return {"ok": False, "message": f"unknown action: {action}"}

        except Exception as e:
            log.exception("action %s failed", e)
            return {"ok": False, "message": str(e)}


# ---------------------------------------------------------------------------
# Windows: 命名管道服务端
# ---------------------------------------------------------------------------

def run_pipe_server(pipe_name: str) -> None:
    import ctypes
    import ctypes.wintypes as wintypes

    kernel32 = ctypes.windll.kernel32
    advapi32 = ctypes.windll.advapi32

    PIPE_ACCESS_DUPLEX       = 0x00000003
    PIPE_TYPE_MESSAGE        = 0x00000004
    PIPE_READMODE_MESSAGE    = 0x00000002
    PIPE_WAIT                = 0x00000000
    PIPE_UNLIMITED_INSTANCES = 255
    INVALID_HANDLE_VALUE     = ctypes.c_void_p(-1).value

    class SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [
            ("nLength",              ctypes.c_ulong),
            ("lpSecurityDescriptor", ctypes.c_void_p),
            ("bInheritHandle",       ctypes.c_bool),
        ]

    sd = ctypes.c_void_p()
    ok = advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        "D:(A;;GRGW;;;WD)", 1, ctypes.byref(sd), None)
    if ok:
        sa = SECURITY_ATTRIBUTES()
        sa.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
        sa.lpSecurityDescriptor = sd
        sa.bInheritHandle = False
        sa_ptr = ctypes.byref(sa)
    else:
        log.warning("ConvertStringSecurityDescriptor failed, using default SA")
        sa_ptr = None

    handler = CommandHandler()

    token = pipe_name.split("ov2n_")[-1]
    ready_file = Path(os.environ.get("TEMP", "C:/Temp")) / f"ov2n_ready_{token}.txt"
    ready_file.write_text("ready", encoding="utf-8")
    log.info("pipe server ready: %s", pipe_name)

    should_exit = False
    while not should_exit:
        pipe = kernel32.CreateNamedPipeW(
            pipe_name,
            PIPE_ACCESS_DUPLEX,
            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
            PIPE_UNLIMITED_INSTANCES,
            BUFFER_SIZE, BUFFER_SIZE, 0, sa_ptr,
        )
        if pipe == INVALID_HANDLE_VALUE:
            log.error("CreateNamedPipe failed: %d", kernel32.GetLastError())
            time.sleep(1)
            continue

        connected = kernel32.ConnectNamedPipe(pipe, None)
        if not connected and kernel32.GetLastError() != 535:
            log.warning("ConnectNamedPipe failed: %d", kernel32.GetLastError())
            kernel32.CloseHandle(pipe)
            continue

        try:
            buf = ctypes.create_string_buffer(BUFFER_SIZE)
            bytes_read = wintypes.DWORD(0)
            ok = kernel32.ReadFile(pipe, buf, BUFFER_SIZE, ctypes.byref(bytes_read), None)
            if not ok:
                continue

            raw = buf.raw[:bytes_read.value].decode("utf-8")
            try:
                cmd = json.loads(raw)
            except json.JSONDecodeError:
                cmd = {}

            response = handler.handle(cmd)
            should_exit = response.pop("_exit", False)

            resp_bytes = json.dumps(response).encode("utf-8")
            bytes_written = wintypes.DWORD(0)
            kernel32.WriteFile(pipe, resp_bytes, len(resp_bytes),
                               ctypes.byref(bytes_written), None)
            kernel32.FlushFileBuffers(pipe)

        except Exception as e:
            log.exception("pipe error: %s", e)
        finally:
            kernel32.DisconnectNamedPipe(pipe)
            kernel32.CloseHandle(pipe)

    ready_file.unlink(missing_ok=True)
    log.info("admin_helper exiting")


# ---------------------------------------------------------------------------
# Linux: Unix domain socket 服务端
# ---------------------------------------------------------------------------

def run_socket_server(socket_path: str) -> None:
    import socket as _socket

    sock_path = Path(socket_path)
    sock_path.unlink(missing_ok=True)

    handler = CommandHandler()

    server = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    server.bind(str(sock_path))
    # 设置权限：允许普通用户连接（rw-rw-rw-）
    os.chmod(str(sock_path), 0o666)
    server.listen(5)
    server.settimeout(1.0)

    log.info("unix socket server ready: %s", socket_path)

    should_exit = False
    while not should_exit:
        try:
            conn, _ = server.accept()
        except _socket.timeout:
            continue
        except Exception as e:
            log.error("accept error: %s", e)
            continue

        try:
            # 读取长度前缀（4字节大端）
            raw_len = _recv_exact(conn, 4)
            if raw_len is None:
                continue
            msg_len = int.from_bytes(raw_len, "big")

            raw = _recv_exact(conn, msg_len)
            if raw is None:
                continue

            try:
                cmd = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                cmd = {}

            response = handler.handle(cmd)
            should_exit = response.pop("_exit", False)

            resp_bytes = json.dumps(response).encode("utf-8")
            length = len(resp_bytes).to_bytes(4, "big")
            conn.sendall(length + resp_bytes)

        except Exception as e:
            log.exception("socket handler error: %s", e)
        finally:
            conn.close()

    server.close()
    sock_path.unlink(missing_ok=True)
    log.info("admin_helper exiting")


def _recv_exact(s, n: int):
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main():
    import argparse

    _setup_logging()

    parser = argparse.ArgumentParser(description="ov2n admin helper")
    parser.add_argument("--pipe-name",   default="", help="Windows: named pipe name")
    parser.add_argument("--socket-path", default="", help="Linux: unix socket path")
    args = parser.parse_args()

    log.info("admin_helper started, platform=%s", platform.system())

    if IS_WINDOWS:
        if not args.pipe_name:
            log.error("--pipe-name required on Windows")
            sys.exit(1)
        log.info("pipe_name: %r", args.pipe_name)
        run_pipe_server(args.pipe_name)
    else:
        if not args.socket_path:
            log.error("--socket-path required on Linux")
            sys.exit(1)
        log.info("socket_path: %s", args.socket_path)
        run_socket_server(args.socket_path)


if __name__ == "__main__":
    main()
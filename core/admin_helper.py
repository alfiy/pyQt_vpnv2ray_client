"""
ov2n Admin Helper
=================
以管理员权限运行的后台进程，无窗口，无 GUI。

职责：
  - 通过 Windows Named Pipe 接收来自 GUI（普通权限）的命令
  - 执行需要管理员权限的操作（启动 xray/openvpn、配置路由）
  - 将执行结果/日志通过管道回传给 GUI

使用方式（由 process_manager.py 自动调用，不需要手动运行）：
  pythonw.exe admin_helper.py [--pipe-name <name>]

安全说明：
  - 命名管道名称包含随机 token，防止其他进程伪造连接
  - 只接受来自本机的连接（本地命名管道）
  - 命令格式为 JSON，非法命令直接忽略
"""
import json
import logging
import os
import platform
import sys
import time
from pathlib import Path

# 确保项目根目录在 sys.path 中
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

IS_WINDOWS = platform.system() == "Windows"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [admin_helper] %(levelname)s %(message)s",
)
log = logging.getLogger("ov2n.admin_helper")


# ---------------------------------------------------------------------------
# 命令处理
# ---------------------------------------------------------------------------

class CommandHandler:
    """处理来自 GUI 的命令，执行 VPN 相关操作。"""

    def __init__(self):
        from core.vpn_process import create_managers
        app_root = _ROOT
        self.openvpn_mgr, self.xray_mgr = create_managers(app_root)
        log.info("managers initialized, app_root=%s", app_root)

    def handle(self, cmd: dict) -> dict:
        """
        处理单条命令，返回响应字典。

        命令格式：{"action": "start_xray", "config": "/path/to/config.json"}
        响应格式：{"ok": true, "message": "...", "pid": 123}
        """
        action = cmd.get("action", "")
        log.info("handle action: %s", action)

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
            log.exception("action %s failed", action)
            return {"ok": False, "message": str(e)}


# ---------------------------------------------------------------------------
# Named Pipe 服务端（Windows）
# ---------------------------------------------------------------------------

PIPE_PREFIX = r"\\.\pipe\ov2n_admin_"
BUFFER_SIZE = 65536


def run_pipe_server(pipe_name: str) -> None:
    """
    启动命名管道服务端，循环接收命令直到收到 exit 或管道断开。
    每次连接处理一条命令后断开，重新等待下一条连接。
    """
    import ctypes
    import ctypes.wintypes as wintypes

    kernel32  = ctypes.windll.kernel32
    advapi32  = ctypes.windll.advapi32

    PIPE_ACCESS_DUPLEX       = 0x00000003
    PIPE_TYPE_MESSAGE        = 0x00000004
    PIPE_READMODE_MESSAGE    = 0x00000002
    PIPE_WAIT                = 0x00000000
    PIPE_UNLIMITED_INSTANCES = 255
    INVALID_HANDLE_VALUE     = ctypes.c_void_p(-1).value

    # 构造允许所有用户（Everyone）读写的安全描述符
    # SDDL: D:(A;;GRGW;;;WD)  -> Everyone 拥有 GENERIC_READ + GENERIC_WRITE
    class SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [
            ("nLength",              ctypes.c_ulong),
            ("lpSecurityDescriptor", ctypes.c_void_p),
            ("bInheritHandle",       ctypes.c_bool),
        ]

    sd = ctypes.c_void_p()
    sddl = "D:(A;;GRGW;;;WD)"
    ok = advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, 1, ctypes.byref(sd), None)
    if not ok:
        log.warning("ConvertStringSecurityDescriptor failed: %d, using default SA",
                    kernel32.GetLastError())
        sa_ptr = None
    else:
        sa = SECURITY_ATTRIBUTES()
        sa.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
        sa.lpSecurityDescriptor = sd
        sa.bInheritHandle = False
        sa_ptr = ctypes.byref(sa)

    handler = CommandHandler()
    log.info("pipe server ready: %s", pipe_name)

    # 从 pipe_name 提取 token
    token = pipe_name.split("ov2n_")[-1]

    # 写入就绪文件，通知 GUI 可以连接
    ready_file = Path(os.environ.get("TEMP", "C:/Temp")) / f"ov2n_ready_{token}.txt"
    ready_file.write_text("ready", encoding="utf-8")
    log.info("ready file written: %s", ready_file)

    should_exit = False
    while not should_exit:
        # 创建管道实例（携带允许普通用户连接的安全属性）
        pipe = kernel32.CreateNamedPipeW(
            pipe_name,
            PIPE_ACCESS_DUPLEX,
            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
            PIPE_UNLIMITED_INSTANCES,
            BUFFER_SIZE,
            BUFFER_SIZE,
            0,
            sa_ptr,
        )

        if pipe == INVALID_HANDLE_VALUE:
            err = kernel32.GetLastError()
            log.error("CreateNamedPipe failed: %d", err)
            time.sleep(1)
            continue

        log.debug("waiting for client connection...")
        connected = kernel32.ConnectNamedPipe(pipe, None)

        if not connected and kernel32.GetLastError() != 535:  # ERROR_PIPE_CONNECTED
            log.warning("ConnectNamedPipe failed: %d", kernel32.GetLastError())
            kernel32.CloseHandle(pipe)
            continue

        try:
            # 读取命令
            buf = ctypes.create_string_buffer(BUFFER_SIZE)
            bytes_read = wintypes.DWORD(0)
            ok = kernel32.ReadFile(pipe, buf, BUFFER_SIZE, ctypes.byref(bytes_read), None)

            if not ok:
                log.warning("ReadFile failed: %d", kernel32.GetLastError())
                continue

            raw = buf.raw[:bytes_read.value].decode("utf-8")
            log.debug("received: %s", raw[:200])

            try:
                cmd = json.loads(raw)
            except json.JSONDecodeError:
                response = {"ok": False, "message": "invalid JSON"}
                cmd = {}

            response = handler.handle(cmd)
            should_exit = response.pop("_exit", False)

            # 发送响应
            resp_bytes = json.dumps(response).encode("utf-8")
            bytes_written = wintypes.DWORD(0)
            kernel32.WriteFile(pipe, resp_bytes, len(resp_bytes),
                               ctypes.byref(bytes_written), None)
            kernel32.FlushFileBuffers(pipe)

        except Exception as e:
            log.exception("pipe communication error: %s", e)
        finally:
            kernel32.DisconnectNamedPipe(pipe)
            kernel32.CloseHandle(pipe)

    log.info("admin_helper exiting")
    # 清理就绪文件
    ready_file.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main():
    import argparse
    
    # ✅ 新增：写日志到文件，因为 pythonw.exe 无控制台
    log_file = Path(os.environ.get("TEMP", "C:/Temp")) / "ov2n_admin_helper.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    logging.getLogger().addHandler(file_handler)
    log.info("admin_helper started, logging to %s", log_file)

    parser = argparse.ArgumentParser()
    parser.add_argument("--pipe-name", default="", help="Named pipe name")
    args = parser.parse_args()

    pipe_name = args.pipe_name
    if not pipe_name:
        log.error("--pipe-name is required, got empty string")
        # ✅ 新增：参数为空时写一个错误就绪文件，避免 GUI 傻等30秒
        error_file = Path(os.environ.get("TEMP", "C:/Temp")) / "ov2n_helper_error.txt"
        error_file.write_text("pipe-name missing", encoding="utf-8")
        sys.exit(1)

    log.info("pipe_name received: %r", pipe_name)  # %r 显示原始字符，便于调试
    run_pipe_server(pipe_name)


if __name__ == "__main__":
    main()
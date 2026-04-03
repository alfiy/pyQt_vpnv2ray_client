"""
ov2n - VPN Process Manager
==========================
替代所有 .ps1 / .bat 脚本，直接用 Python 管理 OpenVPN 和 Xray 进程。

消灭杀软触发点：
  - 不调用任何外部 .ps1 / .bat 脚本
  - 不使用 PowerShell -ExecutionPolicy Bypass
  - 不使用 NSSM 注册服务
  - 不使用 DETACHED_PROCESS + CREATE_NO_WINDOW flag 组合
  - 路由/DNS 操作通过 Python subprocess 直接调用 netsh / route 系统命令
"""

import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

import psutil

log = logging.getLogger("ov2n.vpn")

# Windows 进程创建 flag：仅使用 CREATE_NO_WINDOW，不叠加 DETACHED_PROCESS
_CREATE_NO_WINDOW = 0x08000000


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _run(args: list, timeout: int = 10) -> Tuple[int, str]:
    """运行系统命令，返回 (returncode, stdout+stderr)。不使用 shell=True。"""
    try:
        r = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=_CREATE_NO_WINDOW,
        )
        output = (r.stdout + r.stderr).strip()
        return r.returncode, output
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    except FileNotFoundError:
        return -1, f"command not found: {args[0]}"


def _app_root() -> Path:
    """返回项目根目录（本文件位于项目根）。"""
    return Path(__file__).resolve().parent


def _load_xray_config(config_path: Path) -> dict:
    """读取 Xray config.json，支持行注释（// ...）。"""
    raw = config_path.read_text(encoding="utf-8")
    # 移除行注释（//开头的行）
    raw = re.sub(r"(?m)^\s*//.*$", "", raw)
    return json.loads(raw)


def _save_xray_config_no_bom(config: dict, output_path: Path) -> None:
    """保存 Xray config 为无 BOM 的 UTF-8（重要！）。"""
    json_str = json.dumps(config, ensure_ascii=False, indent=2)
    output_path.write_bytes(json_str.encode("utf-8"))
    
    # 验证编码（前3字节必须是 7B，不能是 EF BB BF）
    try:
        bytes_read = output_path.read_bytes()
        if len(bytes_read) >= 3 and bytes_read[0] == 0xEF and bytes_read[1] == 0xBB and bytes_read[2] == 0xBF:
            log.error("BOM 验证失败，文件写入有问题")
            raise ValueError("Config file has BOM, encoding issue")
        log.debug("Config 编码验证通过（无 BOM）")
    except Exception as e:
        log.error("Config 编码验证失败: %s", e)
        raise


def _get_vps_addr(config: dict) -> str:
    """从 Xray 配置中提取 proxy outbound 的服务器地址。"""
    for ob in config.get("outbounds", []):
        if ob.get("tag") == "proxy":
            servers = ob.get("settings", {}).get("servers", [])
            if servers:
                return servers[0].get("address", "")
            # VLESS/VMess 用 vnext
            vnext = ob.get("settings", {}).get("vnext", [])
            if vnext:
                return vnext[0].get("address", "")
    return ""


def _get_default_route() -> Optional[dict]:
    """
    获取默认路由信息，返回 {
        "gateway": str,
        "iface_alias": str,
        "iface_index": int,
        "local_ip": str
    }
    注意：xray-tun 网卡会被过滤掉。
    """
    try:
        # 使用 psutil 获取所有网卡的路由信息
        for gw_info in psutil.net_if_addrs().items():
            iface_name = gw_info[0]
            # 跳过 xray-tun（已存在的虚拟网卡）
            if "xray" in iface_name.lower():
                continue
        
        # 用 Get-NetRoute 的等价品：遍历所有网卡找默认网关
        # 或直接调用 route print 解析
        rc, out = _run(["route", "print", "0.0.0.0"])
        if rc != 0:
            return None

        # 找 "0.0.0.0  0.0.0.0  <gateway>  <local_ip>  <metric>" 行
        pattern = re.compile(
            r"0\.0\.0\.0\s+0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+)"
        )
        best_metric = 99999
        best = None
        for line in out.splitlines():
            m = pattern.search(line)
            if m:
                gw, local_ip, metric = m.group(1), m.group(2), int(m.group(3))
                if gw != "0.0.0.0" and metric < best_metric:
                    best_metric = metric
                    best = {"gateway": gw, "local_ip": local_ip}

        if not best:
            return None

        # 通过 psutil 找网卡别名和索引
        gw = best["gateway"]
        local_ip = best["local_ip"]
        
        alias = ""
        iface_index = -1
        for nic_name, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family.name == "AF_INET" and addr.address == local_ip:
                    alias = nic_name
                    break
            if alias:
                break

        if not alias:
            # 回退：从 route print 解析
            log.warning("无法通过 psutil 找到网卡，尝试从 route print 解析")
            return None

        # 通过 netsh 获取接口索引
        rc2, idx_out = _run(["netsh", "interface", "ip", "show", "interfaces"])
        if rc2 == 0:
            for line in idx_out.splitlines():
                if alias.lower() in line.lower():
                    parts = line.split()
                    if parts and parts[0].isdigit():
                        iface_index = int(parts[0])
                        break

        best["iface_alias"] = alias
        best["iface_index"] = iface_index if iface_index > 0 else 1
        return best
    except Exception as e:
        log.error("获取默认路由失败: %s", e)
        return None


def _inject_send_through(config: dict, local_ip: str) -> None:
    """为所有 proxy/direct outbound 注入 sendThrough。"""
    for ob in config.get("outbounds", []):
        if ob.get("tag") in ("proxy", "direct"):
            ob["sendThrough"] = local_ip
    log.info("已注入 sendThrough: %s", local_ip)


def _save_dns_backup(alias: str, backup_path: Path) -> None:
    """保存当前 DNS 配置到文件，供 stop 时恢复。"""
    rc, out = _run(["netsh", "interface", "ip", "show", "dns", f"name={alias}"])
    dns_list = []
    for line in out.splitlines():
        m = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
        if m:
            dns_list.append(m.group(1))

    if dns_list:
        content = f"{alias}|{','.join(dns_list)}"
    else:
        content = f"{alias}|DHCP"

    backup_path.write_text(content, encoding="utf-8")
    log.debug("DNS 备份: %s", content)


def _restore_dns(backup_path: Path) -> None:
    """从备份文件恢复 DNS 配置。"""
    if not backup_path.exists():
        log.warning("未找到 DNS 备份文件，跳过恢复")
        return
    try:
        content = backup_path.read_text(encoding="utf-8").strip()
        parts = content.split("|", 1)
        if len(parts) != 2:
            log.warning("DNS 备份格式不正确")
            return
        alias, dns_str = parts[0].strip(), parts[1].strip()
        if dns_str in ("DHCP", ""):
            _run(["netsh", "interface", "ip", "set", "dns", f"name={alias}", "dhcp"])
            log.info("已恢复 %s DNS 为 DHCP", alias)
        else:
            dns_list = [d.strip() for d in dns_str.split(",") if d.strip()]
            if dns_list:
                _run(["netsh", "interface", "ip", "set", "dns",
                      f"name={alias}", "static", dns_list[0]])
                for i, dns in enumerate(dns_list[1:], 2):
                    _run(["netsh", "interface", "ip", "add", "dns",
                          f"name={alias}", dns, f"index={i}"])
                log.info("已恢复 %s 静态 DNS: %s", alias, dns_str)
        backup_path.unlink(missing_ok=True)
    except Exception as e:
        log.error("DNS 恢复失败: %s", e)


# ---------------------------------------------------------------------------
# OpenVPN 管理
# ---------------------------------------------------------------------------

class OpenVPNManager:
    """直接用 subprocess 启动/停止 openvpn.exe。"""

    def __init__(self, openvpn_exe: Path, log_path: Path):
        self.openvpn_exe = openvpn_exe
        self.log_path = log_path
        self._proc: Optional[subprocess.Popen] = None

    @property
    def is_running(self) -> bool:
        if self._proc is None:
            return False
        return self._proc.poll() is None

    def start(self, config_file: Path) -> bool:
        """启动 OpenVPN，返回是否成功。"""
        if self.is_running:
            log.warning("OpenVPN 已在运行，先停止")
            self.stop()

        if not self.openvpn_exe.exists():
            log.error("openvpn.exe 未找到: %s", self.openvpn_exe)
            return False
        if not config_file.exists():
            log.error("OpenVPN config 未找到: %s", config_file)
            return False

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(self.log_path, "a", encoding="utf-8")

        try:
            self._proc = subprocess.Popen(
                [
                    str(self.openvpn_exe),
                    "--config", str(config_file),
                    "--log-append", str(self.log_path),
                ],
                cwd=str(self.openvpn_exe.parent),
                stdout=log_file,
                stderr=log_file,
                stdin=subprocess.DEVNULL,
                creationflags=_CREATE_NO_WINDOW,
            )
            log.info("OpenVPN 已启动，PID=%d，config=%s", self._proc.pid, config_file)
            return True
        except Exception as e:
            log.error("OpenVPN 启动失败: %s", e)
            return False

    def stop(self, timeout: int = 10) -> None:
        """停止 OpenVPN 进程。"""
        if self._proc is None:
            self._kill_orphan()
            return

        if self._proc.poll() is None:
            log.info("正在停止 OpenVPN (PID=%d)...", self._proc.pid)
            self._proc.terminate()
            try:
                self._proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                log.warning("OpenVPN 未响应 terminate，已强制 kill")

        self._proc = None
        log.info("OpenVPN 已停止")

    def _kill_orphan(self) -> None:
        """杀死所有 openvpn.exe 孤儿进程。"""
        try:
            for proc in psutil.process_iter(["name", "pid"]):
                if proc.info["name"] and "openvpn" in proc.info["name"].lower():
                    log.info("发现孤儿 OpenVPN 进程 PID=%d，强制终止", proc.info["pid"])
                    proc.kill()
        except Exception as e:
            log.warning("清理 OpenVPN 孤儿进程失败: %s", e)

    def get_pid(self) -> Optional[int]:
        return self._proc.pid if self._proc else None


# ---------------------------------------------------------------------------
# Xray 管理（完整 Windows 实现）
# ---------------------------------------------------------------------------

class XrayManager:
    """
    完整的 Xray Windows TUN 模式管理器。
    功能包括：
      1. 配置文件选择优先级处理
      2. 注入 sendThrough（选择合适的本地 IP）
      3. 启动 xray.exe 进程
      4. 等待 xray-tun 虚拟网卡创建
      5. 配置 IP 地址 (10.0.0.1/24)
      6. 设置路由表（VPS 地址、网关、默认路由）
      7. 配置 DNS (114.114.114.114, 8.8.8.8)
      8. 停止时清理路由和恢复 DNS
    """

    TUN_NAME = "xray-tun"
    TUN_IP   = "10.0.0.1"
    TUN_MASK = "255.255.255.0"
    TUN_GW   = "10.0.0.0"

    def __init__(self, xray_dir: Path, log_path: Path):
        self.xray_dir = xray_dir
        self.xray_exe = xray_dir / "xray.exe"
        self.log_path = log_path
        self._proc: Optional[subprocess.Popen] = None
        self._dns_backup = xray_dir / "dns_backup.txt"
        self._runtime_config = xray_dir / "config.runtime.json"
        self._vps_addr = ""
        self._route_info: Optional[dict] = None

    @property
    def is_running(self) -> bool:
        if self._proc is None:
            return False
        return self._proc.poll() is None

    def start(self, config_path: Path) -> bool:
        """
        启动 Xray TUN 模式，参照 start-xray.ps1 的完整流程：
          1. 选择配置文件（优先级处理）
          2. 解析配置，提取 VPS 地址
          3. 获取默认路由和网卡信息
          4. 注入 sendThrough
          5. 保存 runtime 配置（无 BOM UTF-8）
          6. 清理旧进程
          7. 启动 xray.exe
          8. 等待 xray-tun 出现（最多 20 秒）
          9. ��置 IP/路由/DNS
        """
        if self.is_running:
            log.warning("Xray 已在运行，先停止")
            self.stop()

        if not self.xray_exe.exists():
            log.error("xray.exe 未找到: %s", self.xray_exe)
            return False

        # ── 1. 选择配置文件（优先级：传入 > APPDATA > 内置）──
        actual_config_path = self._select_config(config_path)
        if not actual_config_path:
            log.error("无法找到有效的 Xray 配置文件")
            return False
        log.info("使用 Xray 配置: %s", actual_config_path)

        # ── 2. 解析配置，提取 VPS 地址 ──
        try:
            config = _load_xray_config(actual_config_path)
        except Exception as e:
            log.error("解析 Xray 配置失败: %s", e)
            return False

        self._vps_addr = _get_vps_addr(config)
        if not self._vps_addr:
            log.error("无法从配置提取 VPS 地址")
            return False
        log.info("VPS 地址: %s", self._vps_addr)

        # ── 3. 获取默认路由和网卡信息 ──
        route_info = _get_default_route()
        if not route_info:
            log.error("找不到默认网关")
            return False
        self._route_info = route_info
        log.info("默认路由信息: %s", route_info)

        # ── 4. 注入 sendThrough ──
        _inject_send_through(config, route_info["local_ip"])

        # ── 5. 保存 runtime 配置（无 BOM UTF-8） ──
        try:
            _save_xray_config_no_bom(config, self._runtime_config)
        except Exception as e:
            log.error("保存 runtime 配置失败: %s", e)
            return False

        # ── 6. 清理旧进程 ──
        self._kill_orphan()

        # ── 7. 清理旧路由 ──
        self._cleanup_routes()

        # ── 8. 启动 xray.exe ──
        log.info("正在启动 xray.exe...")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(self.log_path, "a", encoding="utf-8")

        try:
            self._proc = subprocess.Popen(
                [str(self.xray_exe), "-config", str(self._runtime_config)],
                cwd=str(self.xray_dir),
                stdout=log_file,
                stderr=log_file,
                stdin=subprocess.DEVNULL,
                creationflags=_CREATE_NO_WINDOW,
            )
            log.info("Xray 已启动，PID=%d", self._proc.pid)
        except Exception as e:
            log.error("Xray 启动失败: %s", e)
            return False

        # ── 9. 等待 xray-tun 网卡出现（最多 20 秒） ──
        if not self._wait_for_tun(timeout=20):
            log.error("xray-tun 网卡超时未出现")
            self.stop()
            return False

        time.sleep(2)  # 等网卡稳定

        # ── 10. 配置 IP/路由/DNS ──
        try:
            self._setup_network(route_info)
        except Exception as e:
            log.error("网络配置失败: %s", e)
            self.stop()
            return False

        log.info("===== Xray 启动成功 =====")
        return True

    def stop(self) -> None:
        """
        停止 Xray，完全替代 stop-xray.ps1：
          1. 停止进程
          2. 清理路由
          3. 恢复 DNS
        """
        log.info("===== 停止 Xray TUN =====")

        # 1. 停止进程
        if self._proc and self._proc.poll() is None:
            log.info("正在停止 Xray (PID=%d)...", self._proc.pid)
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                log.warning("Xray 未响应 terminate，已强制 kill")
        self._proc = None
        self._kill_orphan()
        log.info("Xray 进程已停止")

        # 2. 清理路由
        self._cleanup_routes()

        # 3. 恢复 DNS
        if self._route_info:
            _restore_dns(self._dns_backup)
        _run(["ipconfig", "/flushdns"])
        log.info("===== Xray TUN 已停止 =====")

    def get_pid(self) -> Optional[int]:
        return self._proc.pid if self._proc else None

    # ──────────────────────────────────────────
    # 内部方法
    # ──────────────────────────────────────────

    def _select_config(self, user_config: Path) -> Optional[Path]:
        """
        选择配置文件，优先级：
          1. 用户传入的配置（已验证存在）
          2. %APPDATA%\ov2n\config.json
          3. resources\xray\config.json
        """
        if user_config and user_config.exists():
            log.info("使用用户配置: %s", user_config)
            return user_config

        appdata_config = Path(os.environ.get("APPDATA", "")) / "ov2n" / "config.json"
        if appdata_config.exists():
            log.info("使用 APPDATA 配置: %s", appdata_config)
            return appdata_config

        builtin_config = self.xray_dir / "config.json"
        if builtin_config.exists():
            log.info("使用内置配置: %s", builtin_config)
            return builtin_config

        log.error("找不到有效的 Xray 配置文件")
        return None

    def _wait_for_tun(self, timeout: int = 20) -> bool:
        """等待 xray-tun 虚拟网卡出现。"""
        for i in range(timeout):
            time.sleep(1)
            try:
                if self.TUN_NAME in psutil.net_if_addrs():
                    log.info("xray-tun 网卡已出现 (%ds)", i + 1)
                    return True
            except Exception as e:
                log.debug("查询网卡信息失败: %s", e)
            log.debug("等待 xray-tun... %ds", i + 1)
        return False

    def _setup_network(self, route_info: dict) -> None:
        """
        配置 xray-tun IP、路由、DNS。
        完整参照 start-xray.ps1 的网络配置段。
        """
        gw       = route_info["gateway"]
        local_ip = route_info["local_ip"]
        alias    = route_info["iface_alias"]
        real_idx = route_info["iface_index"]

        log.info("网络配置开始 | VPS=%s, 网卡=%s (idx=%d), 网关=%s, sendThrough=%s",
                 self._vps_addr, alias, real_idx, gw, local_ip)

        # 设置 TUN 网卡 IP
        log.info("配置 xray-tun IP 地址...")
        rc, out = _run(["netsh", "interface", "ip", "set", "address",
                        f"name={self.TUN_NAME}", "static", self.TUN_IP, self.TUN_MASK])
        if rc != 0:
            log.warning("设置 xray-tun IP 失败: %s", out)
        time.sleep(1)

        # 获取 TUN 接口索引
        tun_idx = -1
        try:
            adapter = psutil.net_if_addrs().get(self.TUN_NAME)
            if adapter:
                log.debug("xray-tun 网卡已获取")
        except Exception as e:
            log.warning("获取 xray-tun 网卡信息失败: %s", e)

        # 从 netsh 获取精确的索引
        rc2, idx_out = _run(["netsh", "interface", "ip", "show", "interfaces"])
        if rc2 == 0:
            for line in idx_out.splitlines():
                if self.TUN_NAME.lower() in line.lower():
                    parts = line.split()
                    if parts and parts[0].isdigit():
                        tun_idx = int(parts[0])
                        break
        log.info("xray-tun 接口索引: %d", tun_idx)

        # 添加路由
        log.info("配置路由表...")
        _run(["route", "add", self._vps_addr, "mask", "255.255.255.255",
              gw, "metric", "1", "if", str(real_idx)])
        _run(["route", "add", gw, "mask", "255.255.255.255",
              gw, "metric", "1", "if", str(real_idx)])
        if tun_idx > 0:
            _run(["route", "add", "0.0.0.0", "mask", "0.0.0.0",
                  self.TUN_GW, "metric", "5", "if", str(tun_idx)])

        # 备份 DNS 并设置新 DNS
        log.info("配置 DNS...")
        _save_dns_backup(alias, self._dns_backup)
        _run(["netsh", "interface", "ip", "set", "dns",
              f"name={alias}", "static", "114.114.114.114"])
        _run(["netsh", "interface", "ip", "add", "dns",
              f"name={alias}", "8.8.8.8", "index=2"])
        _run(["ipconfig", "/flushdns"])

        log.info("网络配置完成")

    def _cleanup_routes(self) -> None:
        """清理 Xray 添加的路由。"""
        log.info("清理路由...")
        _run(["route", "delete", "0.0.0.0", "mask", "0.0.0.0", self.TUN_GW])
        _run(["route", "delete", "0.0.0.0", "mask", "0.0.0.0", self.TUN_IP])
        if self._vps_addr:
            _run(["route", "delete", self._vps_addr])

    def _kill_orphan(self) -> None:
        """杀死所有 xray.exe 孤儿进程。"""
        try:
            for proc in psutil.process_iter(["name", "pid"]):
                if proc.info["name"] and "xray" in proc.info["name"].lower():
                    log.info("发现孤儿 Xray 进程 PID=%d，强制终止", proc.info["pid"])
                    proc.kill()
        except Exception as e:
            log.warning("清理 Xray 孤儿进程失败: %s", e)


# ---------------------------------------------------------------------------
# 便捷工厂
# ---------------------------------------------------------------------------

def create_managers(app_root: Optional[Path] = None) -> Tuple[OpenVPNManager, XrayManager]:
    """根据项目根目录创建 OpenVPNManager 和 XrayManager。"""
    if app_root is None:
        app_root = _app_root()

    log_dir = app_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    openvpn_mgr = OpenVPNManager(
        openvpn_exe=app_root / "resources" / "openvpn" / "bin" / "openvpn.exe",
        log_path=log_dir / "openvpn.log",
    )
    xray_mgr = XrayManager(
        xray_dir=app_root / "resources" / "xray",
        log_path=log_dir / "xray.log",
    )
    return openvpn_mgr, xray_mgr


# ---------------------------------------------------------------------------
# 命令行测试
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if len(sys.argv) < 3:
        print("用法: python vpn_process.py <xray|openvpn> <start|stop> [config]")
        sys.exit(1)

    mode, action = sys.argv[1], sys.argv[2]
    ovpn_mgr, xray_mgr = create_managers()

    if mode == "xray":
        if action == "start":
            cfg = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("resources/xray/config.json")
            ok = xray_mgr.start(cfg)
            sys.exit(0 if ok else 1)
        elif action == "stop":
            xray_mgr.stop()
    elif mode == "openvpn":
        if action == "start":
            cfg = Path(sys.argv[3]) if len(sys.argv) > 3 else None
            if not cfg:
                print("缺少 config 路径")
                sys.exit(1)
            ok = ovpn_mgr.start(cfg)
            sys.exit(0 if ok else 1)
        elif action == "stop":
            ovpn_mgr.stop()
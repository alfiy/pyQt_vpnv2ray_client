"""
ov2n - VPN Process Manager
==========================
跨平台支持：
  - Windows: Xray TUN 模式（无 TProxy）
  - Linux: V2Ray + 可选 TProxy

变更说明（Bug 修复）：
  - 根本原因：_wait_for_tun() 和 _get_default_route_windows() 内部
    调用了 PowerShell Get-NetAdapter / Get-NetRoute，
    每次调用超时 5 秒 × 20 次 = 100 秒全部超时。
  - 修复方案：全部改用 psutil + netsh/route 实现，零 PowerShell 调用。

具体变更：
  _wait_for_tun()            → psutil.net_if_addrs() 检测网卡（毫秒级，无冷启动）
  _get_default_route_windows() → route print 0.0.0.0 + psutil 解析
  _get_iface_index_by_name() → netsh interface ip show interfaces 解析
  _save_dns_backup_windows() → netsh interface ip show dns 解析
  _restore_dns_windows()     → netsh interface ip set/add dns（原有，保持不变）
  所有函数均无 PowerShell 调用
"""

import json
import logging
import os
import platform
import re
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import psutil

log = logging.getLogger("ov2n.vpn")

IS_WINDOWS = platform.system() == "Windows"
_CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0


# ---------------------------------------------------------------------------
# 配置文件处理
# ---------------------------------------------------------------------------

def _load_xray_config(config_path: Path) -> dict:
    """读取 Xray config.json，支持多种编码和行注释。"""
    log.info("加载配置: %s", config_path)

    for encoding in ('utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'gb18030', 'latin-1'):
        try:
            raw = config_path.read_text(encoding=encoding)
            log.info("✓ 编码: %s", encoding)
            raw = re.sub(r"(?m)^\s*//.*$", "", raw)
            config = json.loads(raw)
            log.info("✓ 配置解析成功")
            return config
        except (UnicodeDecodeError, LookupError):
            continue
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 解析失败: {e}") from e

    raise UnicodeDecodeError("unknown", b"", 0, 1, "无法读取配置文件")


def _save_xray_config_no_bom(config: dict, output_path: Path) -> None:
    """保存为无 BOM UTF-8，并验证编码和 JSON 合法性。"""
    log.info("保存 runtime 配置: %s", output_path)
    json_str = json.dumps(config, ensure_ascii=False, indent=2)
    output_path.write_bytes(json_str.encode("utf-8"))

    header = output_path.read_bytes()[:3]
    log.info("文件头: %s", header.hex().upper())
    if header[:3] == b'\xef\xbb\xbf':
        raise ValueError("runtime config 含有 BOM，写入异常")

    json.loads(output_path.read_text(encoding="utf-8"))
    log.info("✓ 配置保存成功")


def _get_vps_addr(config: dict) -> str:
    """从 Xray 配置提取 VPS 地址（支持 servers/vnext 两种格式）。"""
    for ob in config.get("outbounds", []):
        if ob.get("tag") == "proxy":
            # Shadowsocks / Trojan 格式
            servers = ob.get("settings", {}).get("servers", [])
            if servers:
                addr = servers[0].get("address", "")
                if addr:
                    log.info("✓ VPS (servers): %s", addr)
                    return addr
            # VLESS / VMess 格式
            vnext = ob.get("settings", {}).get("vnext", [])
            if vnext:
                addr = vnext[0].get("address", "")
                if addr:
                    log.info("✓ VPS (vnext): %s", addr)
                    return addr

    raise ValueError("无法从配置提取 VPS 地址（找不到 tag=proxy 的 outbound）")


def _inject_send_through(config: dict, local_ip: str) -> None:
    """向 proxy/direct outbound 注入 sendThrough。"""
    log.info("注入 sendThrough: %s", local_ip)
    count = 0
    for ob in config.get("outbounds", []):
        if ob.get("tag") in ("proxy", "direct"):
            ob["sendThrough"] = local_ip
            count += 1
    log.info("✓ 注入 %d 个 outbound", count)


# ---------------------------------------------------------------------------
# 系统命令执行（无 PowerShell，无 shell=True）
# ---------------------------------------------------------------------------

def _run_cmd(cmd: list, timeout: int = 30) -> Tuple[int, str]:
    """
    执行系统命令，返回 (returncode, combined_output)。
    不使用 shell=True，不调用 PowerShell。
    """
    try:
        log.debug("执行: %s", " ".join(str(c) for c in cmd))
        r = subprocess.run(
            [str(c) for c in cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=_CREATE_NO_WINDOW if IS_WINDOWS else 0,
        )
        output = (r.stdout + r.stderr).strip()
        if r.returncode != 0:
            log.debug("  rc=%d output=%s", r.returncode, output[:200])
        return r.returncode, output
    except subprocess.TimeoutExpired:
        log.warning("命令超时 (%ds): %s", timeout, " ".join(str(c) for c in cmd))
        return -1, "timeout"
    except Exception as e:
        log.error("命令失败: %s -> %s", cmd, e)
        return -1, str(e)


# ---------------------------------------------------------------------------
# Windows 网络操作（纯 psutil + netsh/route，零 PowerShell）
# ---------------------------------------------------------------------------

def _get_default_route_windows() -> Dict[str, Any]:
    """
    获取 Windows 默认路由信息。

    对标 PS1 的 Get-NetRoute + Get-NetIPAddress，
    改用 `route print 0.0.0.0` + psutil 实现，无 PowerShell。

    返回: {"gateway", "realIdx", "realAlias", "localIP"}
    """
    log.info("获取默认路由 (route print 0.0.0.0)...")

    rc, out = _run_cmd(["route", "print", "0.0.0.0"], timeout=10)
    if rc != 0:
        raise RuntimeError(f"route print 失败: {out}")

    # 格式：0.0.0.0  0.0.0.0  <gateway>  <local_ip>  <metric>
    pattern = re.compile(
        r"0\.0\.0\.0\s+0\.0\.0\.0\s+"
        r"(\d+\.\d+\.\d+\.\d+)\s+"   # gateway
        r"(\d+\.\d+\.\d+\.\d+)\s+"   # local_ip（本机 IP）
        r"(\d+)"                       # metric
    )

    best_metric = 99999
    best_gw = ""
    best_ip = ""

    for line in out.splitlines():
        m = pattern.search(line)
        if m:
            gw, lip, metric = m.group(1), m.group(2), int(m.group(3))
            if gw != "0.0.0.0" and metric < best_metric:
                best_metric = metric
                best_gw = gw
                best_ip = lip

    if not best_gw:
        raise RuntimeError("route print 中找不到有效的默认路由")

    log.info("✓ gateway=%s, localIP=%s (metric=%d)", best_gw, best_ip, best_metric)

    # 用 psutil 通过本机 IP 找网卡名（跳过 xray-tun）
    alias = _find_alias_by_ip(best_ip, skip={"xray-tun"})
    if not alias:
        raise RuntimeError(f"找不到 IP={best_ip} 对应的网卡")

    # 用 netsh 获取接口索引
    real_idx = _get_iface_index_by_name(alias)

    log.info("✓ 网卡: %s (idx=%d)", alias, real_idx)
    return {
        "gateway": best_gw,
        "realIdx": real_idx,
        "realAlias": alias,
        "localIP": best_ip,
    }


def _find_alias_by_ip(target_ip: str, skip: set = None) -> str:
    """
    用 psutil.net_if_addrs() 根据 IPv4 地址查找网卡名。
    skip: 需要跳过的网卡名集合（不区分大小写）。
    """
    skip_lower = {s.lower() for s in (skip or set())}
    for nic_name, addrs in psutil.net_if_addrs().items():
        if nic_name.lower() in skip_lower:
            continue
        for addr in addrs:
            if addr.family == socket.AF_INET and addr.address == target_ip:
                return nic_name
    return ""


def _get_iface_index_by_name(alias: str) -> int:
    """
    通过 `netsh interface ip show interfaces` 获取网卡接口索引。
    无 PowerShell。
    """
    rc, out = _run_cmd(
        ["netsh", "interface", "ip", "show", "interfaces"], timeout=10)
    if rc != 0:
        log.warning("netsh show interfaces 失败，索引回退 -1")
        return -1

    # 典型行格式（列顺序: Idx Met MTU State Name）
    # 示例：  5          25        1500  connected     以太网
    for line in out.splitlines():
        if alias.lower() not in line.lower():
            continue
        parts = line.split()
        if parts and parts[0].isdigit():
            return int(parts[0])

    log.warning("找不到 '%s' 的接口索引，回退 -1", alias)
    return -1


def _get_tun_index() -> int:
    """
    获取 xray-tun 的接口索引。
    先尝试 psutil（快），再用 netsh（备用）。
    """
    # 先用 psutil 查 net_if_stats（有 index 信息的平台才有效）
    # 直接用 netsh 最可靠
    return _get_iface_index_by_name("xray-tun")


def _save_dns_backup_windows(alias: str, backup_path: Path) -> None:
    """
    备份当前 DNS 配置，供 stop 时恢复。
    用 `netsh interface ip show dns`，无 PowerShell。
    """
    log.info("备份 DNS（%s）...", alias)

    rc, out = _run_cmd(
        ["netsh", "interface", "ip", "show", "dns", f"name={alias}"],
        timeout=10)

    dns_list = []
    if rc == 0:
        for line in out.splitlines():
            m = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
            if m:
                ip = m.group(1)
                # 过滤明显无效的 IP（如 0.0.0.0）
                if not ip.startswith("0."):
                    dns_list.append(ip)

    dns_str = ",".join(dns_list) if dns_list else "DHCP"
    content = f"{alias}|{dns_str}"
    backup_path.write_text(content, encoding="utf-8")
    log.info("✓ DNS 备份: %s", content)


def _restore_dns_windows(backup_path: Path) -> None:
    """
    从备份文件恢复 DNS 配置，无 PowerShell。
    对标 stop-xray.ps1 的 DNS 恢复段。
    """
    log.info("恢复 DNS...")

    if not backup_path.exists():
        log.warning("⚠ DNS 备份文件不存在: %s", backup_path)
        return

    try:
        content = backup_path.read_text(encoding="utf-8").strip()
        alias, dns_str = content.split("|", 1)
        alias, dns_str = alias.strip(), dns_str.strip()

        if dns_str in ("DHCP", ""):
            _run_cmd(["netsh", "interface", "ip", "set", "dns",
                      f"name={alias}", "dhcp"])
            log.info("✓ %s DNS 恢复为 DHCP", alias)
        else:
            dns_list = [d.strip() for d in dns_str.split(",") if d.strip()]
            _run_cmd(["netsh", "interface", "ip", "set", "dns",
                      f"name={alias}", "static", dns_list[0]])
            for i, dns in enumerate(dns_list[1:], 2):
                _run_cmd(["netsh", "interface", "ip", "add", "dns",
                          f"name={alias}", dns, f"index={i}"])
            log.info("✓ %s DNS 恢复为静态: %s", alias, dns_str)

        backup_path.unlink(missing_ok=True)

    except Exception as e:
        log.error("❌ DNS 恢复失败: %s", e)


# ---------------------------------------------------------------------------
# Linux 网络操作（占位，原有逻辑）
# ---------------------------------------------------------------------------

def _save_dns_backup_linux(alias: str, backup_path: Path) -> None:
    backup_path.write_text(f"{alias}|original", encoding="utf-8")


def _restore_dns_linux(backup_path: Path) -> None:
    if backup_path.exists():
        backup_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# OpenVPN 管理器（跨平台）
# ---------------------------------------------------------------------------

class OpenVPNManager:
    """直接用 subprocess 管理 openvpn.exe 进程，不依赖 NSSM 服务。"""

    def __init__(self, openvpn_exe: Path, log_path: Path):
        self.openvpn_exe = openvpn_exe
        self.log_path = log_path
        self._proc: Optional[subprocess.Popen] = None

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, config_file: Path) -> bool:
        if self.is_running:
            log.warning("OpenVPN 已在运行，先停止")
            self.stop()

        if not self.openvpn_exe.exists():
            log.error("❌ openvpn.exe 未找到: %s", self.openvpn_exe)
            return False
        if not config_file.exists():
            log.error("❌ 配置文件未找到: %s", config_file)
            return False

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(self.log_path, "a", encoding="utf-8")

        try:
            self._proc = subprocess.Popen(
                [str(self.openvpn_exe), "--config", str(config_file),
                 "--log-append", str(self.log_path)],
                cwd=str(self.openvpn_exe.parent),
                stdout=log_file,
                stderr=log_file,
                stdin=subprocess.DEVNULL,
                creationflags=_CREATE_NO_WINDOW,
            )
            log.info("✓ OpenVPN 已启动 (PID=%d)", self._proc.pid)
            return True
        except Exception as e:
            log.error("❌ OpenVPN 启动失败: %s", e)
            return False

    def stop(self, timeout: int = 10) -> None:
        if self._proc:
            if self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
        self._proc = None
        # 清理孤儿进程
        for proc in psutil.process_iter(["name", "pid"]):
            try:
                if proc.info["name"] and "openvpn" in proc.info["name"].lower():
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        log.info("✓ OpenVPN 已停止")

    def get_pid(self) -> Optional[int]:
        if self._proc and self._proc.poll() is None:
            return self._proc.pid
        return None


# ---------------------------------------------------------------------------
# Xray 管理器（Windows TUN 模式，零 PowerShell）
# ---------------------------------------------------------------------------

class XrayManager:
    """
    Xray 管理器 - Windows TUN 模式。

    完全对标 start-xray.ps1 / stop-xray.ps1。
    全部用 Python + psutil + netsh/route 实现，零 PowerShell。

    核心修复：
      _wait_for_tun() 用 psutil.net_if_addrs() 代替
      Get-NetAdapter PowerShell 调用，避免超时。
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

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # ──────────────────────────────────────────
    # 公开接口
    # ──────────────────────────────────────────

    def start(self, user_config_path: Optional[Path]) -> bool:
        """启动 Xray TUN 模式（完全对标 start-xray.ps1，零 PowerShell）。"""
        log.info("=" * 60)
        log.info("========== 启动 Xray ==========")
        log.info("=" * 60)

        try:
            log.info("[1/8] 选择配置文件...")
            config_path = self._select_config(user_config_path)

            log.info("[2/8] 加载配置...")
            config = _load_xray_config(config_path)

            log.info("[3/8] 提取 VPS 地址...")
            self._vps_addr = _get_vps_addr(config)

            log.info("[4/8] 获取默认路由...")
            route_info = _get_default_route_windows()

            log.info("[5/8] 注入 sendThrough...")
            _inject_send_through(config, route_info["localIP"])

            log.info("[6/8] 保存 runtime 配置...")
            _save_xray_config_no_bom(config, self._runtime_config)

            log.info("[7/8] 清理旧进程和路由...")
            self._kill_xray()
            self._cleanup_routes()

            log.info("[8/8] 启动 xray.exe 并配置网络...")
            self._start_and_configure(route_info)

            log.info("=" * 60)
            log.info("✓✓✓ Xray 启动成功！")
            log.info("=" * 60)
            return True

        except Exception as e:
            log.exception("❌ Xray 启动失败: %s", e)
            return False

    def stop(self) -> None:
        """停止 Xray（完全对标 stop-xray.ps1，零 PowerShell）。"""
        log.info("=" * 60)
        log.info("========== 停止 Xray ==========")
        log.info("=" * 60)

        self._kill_xray()
        self._cleanup_routes()
        _restore_dns_windows(self._dns_backup)
        _run_cmd(["ipconfig", "/flushdns"])

        log.info("✓ Xray 已停止")

    def get_pid(self) -> Optional[int]:
        if self._proc and self._proc.poll() is None:
            return self._proc.pid
        return None

    # ──────────────────────────────────────────
    # 内部实现
    # ──────────────────────────────────────────

    def _select_config(self, user_config: Optional[Path]) -> Path:
        """配置文件三级优先级（对标 PS1）：用户传入 > APPDATA > 内置。"""
        if user_config and user_config.exists():
            log.info("✓ 用户配置: %s", user_config)
            return user_config

        appdata = os.environ.get("APPDATA", "")
        if appdata:
            p = Path(appdata) / "ov2n" / "config.json"
            if p.exists():
                log.info("✓ APPDATA 配置: %s", p)
                return p

        p = self.xray_dir / "config.json"
        if p.exists():
            log.info("✓ 内置配置: %s", p)
            return p

        raise FileNotFoundError(
            "找不到 Xray 配置文件（已检查：用户传入、APPDATA、resources/xray）")

    def _kill_xray(self) -> None:
        """
        终止所有 xray.exe 进程。
        对标 PS1：Get-Process -Name "xray" | Stop-Process -Force
        用 psutil，零 PowerShell。
        """
        log.info("清理 Xray 进程...")
        killed = 0
        for proc in psutil.process_iter(["name", "pid"]):
            try:
                if proc.info["name"] and "xray" in proc.info["name"].lower():
                    log.info("  终止 PID=%d (%s)", proc.info["pid"], proc.info["name"])
                    proc.kill()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if killed > 0:
            # 对标 PS1：while (Get-Process xray) { Start-Sleep 1 }
            for _ in range(10):
                still = [p for p in psutil.process_iter(["name"])
                         if p.info["name"] and "xray" in p.info["name"].lower()]
                if not still:
                    break
                time.sleep(1)

        log.info("✓ 已清理 %d 个 Xray 进程", killed)

    def _cleanup_routes(self) -> None:
        """清理 Xray 路由（对标 PS1：route delete）。"""
        log.info("清理旧路由...")
        _run_cmd(["route", "delete", "0.0.0.0", "mask", "0.0.0.0", self.TUN_GW])
        _run_cmd(["route", "delete", "0.0.0.0", "mask", "0.0.0.0", self.TUN_IP])
        if self._vps_addr:
            _run_cmd(["route", "delete", self._vps_addr])
        log.info("✓ 旧路由已清理")

    def _start_and_configure(self, route_info: Dict[str, Any]) -> None:
        """启动 xray.exe，等待 xray-tun，配置网络。"""
        if not self.xray_exe.exists():
            raise FileNotFoundError(f"xray.exe 未找到: {self.xray_exe}")

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(self.log_path, "a", encoding="utf-8")

        self._proc = subprocess.Popen(
            [str(self.xray_exe), "-config", str(self._runtime_config)],
            cwd=str(self.xray_dir),
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.DEVNULL,
            creationflags=_CREATE_NO_WINDOW,
        )
        log.info("✓ xray.exe 已启动 (PID=%d)", self._proc.pid)
        log.info("配置: %s", self._runtime_config)

        # 等待 xray-tun 出现（零 PowerShell）
        log.info("等待 xray-tun 出现（最多 20s）...")
        tun_idx = self._wait_for_tun(timeout=20)

        if tun_idx is None:
            log.error("❌ xray-tun 20s 内未出现")
            log.error("   日志: %s", self.log_path)
            log.error("   可能原因: xray 启动失败 / config 格式错误 / 缺少管理员权限")
            raise RuntimeError("xray-tun 未出现，xray.exe 可能启动失败")

        log.info("✓ xray-tun 已出现 (idx=%d)", tun_idx)
        time.sleep(2)  # 对标 PS1：Start-Sleep 2，等网卡稳定

        self._setup_network(tun_idx, route_info)

    def _wait_for_tun(self, timeout: int = 20) -> Optional[int]:
        """
        等待 xray-tun 网卡出现，返回接口索引。

        对标 PS1：
            do {
                Start-Sleep 1
                $adapter = Get-NetAdapter -Name "xray-tun" -ErrorAction SilentlyContinue
                Write-Host "等待 xray-tun... ${waited}s"
            } while ($null -eq $adapter -and $waited -lt 20)

        ★ 修复核心：
            旧代码：每秒调用 PowerShell Get-NetAdapter，首次冷启动 5 秒超时
                   → 20 次 × 5 秒 = 100 秒全部超时，xray-tun 永远"未出现"
            新代码：psutil.net_if_addrs() 直接读取系统网卡列表，毫秒级，无 PowerShell
        """
        for i in range(1, timeout + 1):
            # psutil.net_if_addrs() 返回 {网卡名: [地址列表]}，键即为网卡名
            if self.TUN_NAME in psutil.net_if_addrs():
                tun_idx = _get_tun_index()
                log.info("  xray-tun 出现 (%ds), idx=%d", i, tun_idx)
                return tun_idx if tun_idx > 0 else 1  # 保底返回 1

            log.debug("  等待 xray-tun... %ds", i)
            time.sleep(1)

        return None

    def _setup_network(self, tun_idx: int, route_info: Dict[str, Any]) -> None:
        """
        配置网络（对标 PS1 的网络配置段，零 PowerShell）：
          1. netsh: 设置 xray-tun IP 10.0.0.1/24
          2. route add: VPS 直连 / 网关直连 / 默认走 TUN
          3. netsh: 备份并设置 DNS
        """
        gateway  = route_info["gateway"]
        real_idx = route_info["realIdx"]
        alias    = route_info["realAlias"]
        local_ip = route_info["localIP"]

        log.info("配置网络:")
        log.info("  VPS        : %s", self._vps_addr)
        log.info("  物理网卡   : %s (idx=%d)", alias, real_idx)
        log.info("  网关       : %s", gateway)
        log.info("  sendThrough: %s", local_ip)
        log.info("  xray-tun   : idx=%d", tun_idx)

        # 设置 TUN IP（对标 PS1：netsh interface ip set address）
        log.info("设置 xray-tun IP (10.0.0.1/24)...")
        _run_cmd(["netsh", "interface", "ip", "set", "address",
                  "name=xray-tun", "static", self.TUN_IP, self.TUN_MASK])
        time.sleep(1)  # 对标 PS1：Start-Sleep 1

        # 重新获取 tunIdx（网卡重建后索引可能变化，对标 PS1 的重新 Get-NetAdapter）
        new_idx = _get_tun_index()
        if new_idx > 0:
            tun_idx = new_idx
            log.info("✓ 更新 xray-tun idx: %d", tun_idx)

        # 添加路由（对标 PS1：route add）
        log.info("添加路由...")
        _run_cmd(["route", "add", self._vps_addr, "mask", "255.255.255.255",
                  gateway, "metric", "1", "if", str(real_idx)])
        _run_cmd(["route", "add", gateway, "mask", "255.255.255.255",
                  gateway, "metric", "1", "if", str(real_idx)])
        _run_cmd(["route", "add", "0.0.0.0", "mask", "0.0.0.0",
                  self.TUN_GW, "metric", "5", "if", str(tun_idx)])
        log.info("✓ 路由已配置")

        # DNS（对标 PS1：netsh interface ip set/add dns）
        log.info("配置 DNS...")
        _save_dns_backup_windows(alias, self._dns_backup)
        _run_cmd(["netsh", "interface", "ip", "set", "dns",
                  f"name={alias}", "static", "114.114.114.114"])
        _run_cmd(["netsh", "interface", "ip", "add", "dns",
                  f"name={alias}", "8.8.8.8", "index=2"])
        _run_cmd(["ipconfig", "/flushdns"])
        log.info("✓ DNS 已配置")

        log.info("===== 启动完成 =====")
        log.info("VPS        : %s", self._vps_addr)
        log.info("网卡       : %s (idx=%d)", alias, real_idx)
        log.info("网关       : %s", gateway)
        log.info("sendThrough: %s", local_ip)
        log.info("tunIdx     : %d", tun_idx)


# ---------------------------------------------------------------------------
# Linux V2Ray 管理器（占位，由 worker.py 处理）
# ---------------------------------------------------------------------------

class V2RayManager:
    """V2Ray 管理器 - Linux 专用（由 worker.py 和 PolkitHelper 处理）。"""

    def __init__(self, v2ray_dir: Path, log_path: Path):
        self.v2ray_dir = v2ray_dir
        self.log_path = log_path

    @property
    def is_running(self) -> bool:
        return False

    def start(self, config_path: Path, **kwargs) -> bool:
        log.warning("V2Ray 启动应通过 worker.py 的 SingleV2RayThread 调用（Linux 专用）")
        return False

    def stop(self) -> None:
        pass

    def get_pid(self) -> Optional[int]:
        return None


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def create_managers(app_root: Optional[Path] = None) -> Tuple[OpenVPNManager, Any]:
    """
    创建进程管理器。

    用法：
        from core.vpn_process import create_managers
        openvpn_mgr, xray_mgr = create_managers(app_root)
    """
    if app_root is None:
        app_root = Path(__file__).resolve().parent.parent

    log.info("初始化管理器: app_root=%s", app_root)
    log_dir = app_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    openvpn_mgr = OpenVPNManager(
        openvpn_exe=app_root / "resources" / "openvpn" / "bin" / "openvpn.exe",
        log_path=log_dir / "openvpn.log",
    )

    if IS_WINDOWS:
        xray_mgr: Any = XrayManager(
            xray_dir=app_root / "resources" / "xray",
            log_path=log_dir / "xray.log",
        )
    else:
        xray_mgr = V2RayManager(
            v2ray_dir=app_root / "resources" / "xray",
            log_path=log_dir / "v2ray.log",
        )

    return openvpn_mgr, xray_mgr
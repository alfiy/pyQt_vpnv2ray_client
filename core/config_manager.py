"""
配置管理模块
负责所有配置文件的加载、保存、验证和提取逻辑，包括：
- 用户配置路径持久化 (config_paths.json)
- 导入标志持久化 (imported_flags.json)
- TProxy 配置持久化 (tproxy.conf)
- V2Ray 配置验证与默认配置创建
- 从 V2Ray 配置中提取 TProxy 参数

跨平台说明：
  Linux   → 配置存储在 ~/.config/ov2n/（原有逻辑不变）
  Windows → 配置存储在 %APPDATA%\ov2n\
            validate_v2ray_config 支持含 // 注释的 JSON（xray Windows 模板格式）
            init_config_files 对已存在且有效的文件绝不覆盖
"""
import json
import os
import platform
import re
import shutil
from typing import Dict, Optional

from core.utils import get_app_root

IS_WINDOWS = platform.system() == "Windows"


# ── 配置目录：Linux 用 ~/.config/ov2n，Windows 用 %APPDATA%\ov2n ──
def _get_config_dir() -> str:
    if IS_WINDOWS:
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(appdata, "ov2n")
    return os.path.expanduser("~/.config/ov2n")


_CONFIG_DIR = _get_config_dir()

TPROXY_CONF_PATH    = os.path.join(_CONFIG_DIR, "tproxy.conf")
CONFIG_PATHS_FILE   = os.path.join(_CONFIG_DIR, "config_paths.json")
IMPORTED_FLAGS_FILE = os.path.join(_CONFIG_DIR, "imported_flags.json")

DEFAULT_VPN_CONFIG   = os.path.join(_CONFIG_DIR, "client.ovpn")
DEFAULT_V2RAY_CONFIG = os.path.join(_CONFIG_DIR, "config.json")


# ============================================
# 导入标志 (imported_flags.json)
# ============================================

def load_imported_flags() -> Dict[str, bool]:
    """加载 VPN 和 V2Ray 配置的导入状态标志。"""
    defaults = {'vpn': False, 'v2ray': False}
    if not os.path.exists(IMPORTED_FLAGS_FILE):
        return defaults
    try:
        with open(IMPORTED_FLAGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {'vpn': data.get('vpn', False), 'v2ray': data.get('v2ray', False)}
    except Exception:
        return defaults


def save_imported_flags(vpn_imported: bool, v2ray_imported: bool) -> None:
    """保存 VPN 和 V2Ray 配置的导入状态标志。"""
    try:
        os.makedirs(os.path.dirname(IMPORTED_FLAGS_FILE), exist_ok=True)
        with open(IMPORTED_FLAGS_FILE, 'w', encoding='utf-8') as f:
            json.dump({'vpn': vpn_imported, 'v2ray': v2ray_imported}, f)
    except Exception as e:
        print(f"保存导入标志失败: {e}")


# ============================================
# 配置路径 (config_paths.json)
# ============================================

def load_config_paths() -> Dict[str, str]:
    """加载已保存的 VPN 和 V2Ray 配置文件路径。"""
    defaults = {
        'vpn_config': DEFAULT_VPN_CONFIG,
        'v2ray_config': DEFAULT_V2RAY_CONFIG,
    }
    if not os.path.exists(CONFIG_PATHS_FILE):
        return defaults
    try:
        with open(CONFIG_PATHS_FILE, 'r', encoding='utf-8') as f:
            saved = json.load(f)
        vpn   = saved.get('vpn_config',   defaults['vpn_config'])
        v2ray = saved.get('v2ray_config', defaults['v2ray_config'])
        return {
            'vpn_config':   vpn   if os.path.exists(vpn)   else defaults['vpn_config'],
            'v2ray_config': v2ray if os.path.exists(v2ray) else defaults['v2ray_config'],
        }
    except Exception as e:
        print(f"加载配置路径失败: {e}")
        return defaults


def save_config_paths(vpn_config: str, v2ray_config: str) -> None:
    """保存 VPN 和 V2Ray 配置文件路径。"""
    try:
        os.makedirs(os.path.dirname(CONFIG_PATHS_FILE), exist_ok=True)
        with open(CONFIG_PATHS_FILE, 'w', encoding='utf-8') as f:
            json.dump(
                {'vpn_config': vpn_config, 'v2ray_config': v2ray_config},
                f, indent=2, ensure_ascii=False,
            )
        print("✓ 配置路径已保存")
    except Exception as e:
        print(f"保存配置路径失败: {e}")


# ============================================
# TProxy 配置 (tproxy.conf)
# ============================================

def load_tproxy_config() -> Dict:
    """加载 TProxy 透明代理配置。"""
    defaults = {"enabled": False, "vps_ip": "", "port": 12345, "mark": 1, "table": 100}
    if not os.path.exists(TPROXY_CONF_PATH):
        return defaults
    try:
        data = {}
        with open(TPROXY_CONF_PATH) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    data[k.strip()] = v.strip()
        defaults["enabled"] = data.get("TPROXY_ENABLED", "false").lower() == "true"
        defaults["vps_ip"]  = data.get("VPS_IP", "")
        defaults["port"]    = int(data.get("V2RAY_PORT", 12345))
        defaults["mark"]    = int(data.get("MARK", 1))
        defaults["table"]   = int(data.get("TABLE", 100))
    except Exception as e:
        print(f"加载 tproxy 配置失败: {e}")
    return defaults


def save_tproxy_config(enabled: bool, vps_ip: str, port: int,
                       mark: int, table: int) -> None:
    """保存 TProxy 透明代理配置。"""
    try:
        os.makedirs(os.path.dirname(TPROXY_CONF_PATH), exist_ok=True)
        with open(TPROXY_CONF_PATH, "w") as f:
            f.write("# ov2n TProxy 配置\n")
            f.write(f"TPROXY_ENABLED={'true' if enabled else 'false'}\n")
            f.write(f"VPS_IP={vps_ip}\n")
            f.write(f"V2RAY_PORT={port}\n")
            f.write(f"MARK={mark}\n")
            f.write(f"TABLE={table}\n")
    except Exception as e:
        print(f"保存 tproxy 配置失败: {e}")


# ============================================
# V2Ray 配置提取与验证
# ============================================

def _strip_json_comments(text: str) -> str:
    """
    移除 JSON 中的单行注释（// 开头的行）。
    用于支持 xray Windows 模板中含注释的 config.json。
    Linux 上的标准 JSON 文件同样兼容（无注释则原样返回）。
    """
    return re.sub(r'(?m)^\s*//.*$', '', text)


def extract_tproxy_config_from_v2ray(config_path: str) -> Optional[Dict]:
    """
    从 V2Ray 配置文件中提取 TProxy 相关参数（VPS IP 和 TProxy 端口）。

    Returns:
        包含 'vps_ip' 和 'tproxy_port' 的字典，提取失败返回 None。
    """
    if not os.path.exists(config_path):
        return None
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            raw = f.read()

        # 支持含注释的 JSON（xray Windows 模板）
        config = json.loads(_strip_json_comments(raw))

        vps_ip = None
        tproxy_port = None

        # 从 outbounds 提取 VPS IP
        for ob in config.get('outbounds', []):
            if ob.get('protocol') in [
                    'shadowsocks', 'vmess', 'vless', 'trojan', 'socks', 'http']:
                servers = ob.get('settings', {}).get('servers', [])
                if servers:
                    addr = servers[0].get('address', '')
                    if addr and re.match(
                            r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', addr):
                        vps_ip = addr
                        break

        # 从 inbounds 提取 TProxy 端口
        for ib in config.get('inbounds', []):
            if ib.get('protocol') == 'dokodemo-door':
                if ib.get('settings', {}).get('network') in ['tcp,udp', 'tcp', 'udp']:
                    tproxy_port = ib.get('port')
                    break
            elif 'tproxy' in ib.get('tag', '').lower():
                tproxy_port = ib.get('port')
                break

        if vps_ip and tproxy_port:
            print(f"✓ 自动提取配置成功: VPS IP={vps_ip}, TProxy端口={tproxy_port}")
            return {'vps_ip': vps_ip, 'tproxy_port': tproxy_port}

        print(f"⚠ 配置提取不完整: VPS IP={vps_ip}, TProxy端口={tproxy_port}")
        return None
    except Exception as e:
        print(f"✗ 提取配置失败: {e}")
        return None


def validate_v2ray_config(path: str) -> bool:
    """
    验证 V2Ray 配置文件是否有效（非空且包含 inbounds/outbounds）。
    支持含 // 单行注释的 JSON（xray Windows 模板格式）。
    """
    try:
        if os.path.getsize(path) == 0:
            return False
        with open(path, 'r', encoding='utf-8') as f:
            raw = f.read()
        cfg = json.loads(_strip_json_comments(raw))
        return 'inbounds' in cfg and 'outbounds' in cfg
    except Exception:
        return False


def create_default_v2ray_config(config_path: str) -> None:
    """创建默认的 V2Ray 配置文件（仅在文件不存在时调用）。"""
    cfg = {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {"tag": "socks", "port": 1080, "protocol": "socks",
             "settings": {"auth": "noauth", "udp": True}},
            {"tag": "http", "port": 1081, "protocol": "http"},
            {"tag": "tproxy", "port": 12345, "protocol": "dokodemo-door",
             "settings": {"network": "tcp,udp", "followRedirect": True},
             "streamSettings": {"sockopt": {"tproxy": "tproxy"}}},
        ],
        "outbounds": [
            {"tag": "proxy", "protocol": "shadowsocks",
             "settings": {"servers": [{"address": "your.server.com", "port": 8388,
                                       "method": "chacha20-ietf-poly1305",
                                       "password": "your_password_here"}]}},
            {"tag": "direct", "protocol": "freedom", "settings": {}},
            {"tag": "block", "protocol": "blackhole",
             "settings": {"response": {"type": "http"}}},
        ],
        "routing": {
            "domainStrategy": "IPOnDemand",
            "rules": [
                {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"},
                {"type": "field", "domain": ["geosite:cn"], "outboundTag": "direct"},
                {"type": "field", "ip": ["geoip:cn"], "outboundTag": "direct"},
            ],
        },
    }
    try:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        print("✓ 默认 V2Ray 配置已创建")
    except Exception as e:
        print(f"创建默认 V2Ray 配置失败: {e}")


def init_config_files(vpn_config_path: str, v2ray_config_path: str) -> None:
    """
    初始化配置文件。

    设计原则（Linux / Windows 一致）：
      1. 文件不存在 → 从开发目录复制，复制失败才创建默认模板
      2. 文件存在且有效 → 绝不覆盖（用户自定义配置受保护）
      3. 文件存在但无效（损坏/空文件）→ 备份后重建默认模板

    Windows 额外说明：
      - 用户从 GUI 导入配置后，路径保存在 %APPDATA%\ov2n\config_paths.json
      - v2ray_config_path 指向用户导入的文件，validate 支持含注释的 JSON
      - 因此正常情况下不会触发重建
    """
    app_root = get_app_root()
    dev_vpn   = os.path.join(app_root, "core", "openvpn", "client.ovpn")
    dev_v2ray = os.path.join(app_root, "core", "xray",   "config.json")

    user_cfg_dir = os.path.dirname(v2ray_config_path)
    os.makedirs(user_cfg_dir, exist_ok=True)

    # ── V2Ray 配置初始化 ────────────────────────────
    if not os.path.exists(v2ray_config_path):
        # 文件不存在：从开发目录复制，复制失败才创建默认模板
        if os.path.exists(dev_v2ray):
            try:
                shutil.copy2(dev_v2ray, v2ray_config_path)
                print(f"✓ 已从开发目录复制 V2Ray 配置")
            except Exception as e:
                print(f"复制 V2Ray 配置失败: {e}")
                create_default_v2ray_config(v2ray_config_path)
        else:
            create_default_v2ray_config(v2ray_config_path)

    elif not validate_v2ray_config(v2ray_config_path):
        # 文件存在但无效（损坏/空）：备份后重建
        # 注意：含注释的 JSON 在 validate_v2ray_config 中已经能正确处理，
        # 因此用户的 xray Windows 格式配置不会触发此分支
        backup_path = v2ray_config_path + ".backup"
        try:
            shutil.copy2(v2ray_config_path, backup_path)
            print(f"⚠ V2Ray 配置无效，已备份至 {backup_path}")
        except Exception:
            pass
        create_default_v2ray_config(v2ray_config_path)

    # else: 文件存在且有效 → 什么都不做，完全保留用户配置

    # ── VPN 配置初始化 ──────────────────────────────
    if not os.path.exists(vpn_config_path) and os.path.exists(dev_vpn):
        try:
            shutil.copy2(dev_vpn, vpn_config_path)
        except Exception:
            pass
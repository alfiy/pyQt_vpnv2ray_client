"""
配置管理模块
负责所有配置文件的加载、保存、验证和提取逻辑，包括：
- 用户配置文件的复制与持久化存储
- 导入标志持久化 (imported_flags.json)
- TProxy 配置持久化 (tproxy.conf)
- V2Ray 配置验证与默认配置创建
- 从 V2Ray 配置中提取 TProxy 参数

核心设计原则：
  用户导入配置时，将配置文件**复制**到用户配置目录下，而非仅保存路径。
  这样即使用户删除了原始文件，程序仍能从用户配置目录读取正确的配置。

跨平台说明：
  Linux   → 配置存储在 ~/.config/ov2n/
  Windows → 配置存储在 %APPDATA%\ov2n\
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
IMPORTED_FLAGS_FILE = os.path.join(_CONFIG_DIR, "imported_flags.json")

# 旧版本遗留的配置路径文件（用于迁移）
_LEGACY_CONFIG_PATHS_FILE = os.path.join(_CONFIG_DIR, "config_paths.json")

# 用户配置文件的固定存储位置（导入时复制到此处）
USER_VPN_CONFIG   = os.path.join(_CONFIG_DIR, "client.ovpn")
USER_V2RAY_CONFIG = os.path.join(_CONFIG_DIR, "config.json")


def get_config_dir() -> str:
    """获取用户配置目录路径（供外部模块使用）。"""
    return _CONFIG_DIR


def get_user_vpn_config_path() -> str:
    """获取用户 VPN 配置文件的固定存储路径。"""
    return USER_VPN_CONFIG


def get_user_v2ray_config_path() -> str:
    """获取用户 V2Ray 配置文件的固定存储路径。"""
    return USER_V2RAY_CONFIG


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
        print(f"[ov2n] ERR save imported flags: {e}")


# ============================================
# 配置文件导入（复制到用户目录）
# ============================================

def import_vpn_config(source_path: str) -> str:
    """
    将用户选择的 VPN 配置文件复制到用户配置目录。

    Args:
        source_path: 用户选择的源文件路径

    Returns:
        复制后的目标文件路径（即 USER_VPN_CONFIG）

    Raises:
        FileNotFoundError: 源文件不存在
        OSError: 复制失败
    """
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"源文件不存在: {source_path}")

    os.makedirs(_CONFIG_DIR, exist_ok=True)

    # 如果源文件和目标文件是同一个文件，无需复制
    src_real = os.path.realpath(source_path)
    dst_real = os.path.realpath(USER_VPN_CONFIG)
    if src_real != dst_real:
        shutil.copy2(source_path, USER_VPN_CONFIG)
        print(f"[ov2n] OK VPN config copied to: {USER_VPN_CONFIG}")
    else:
        print(f"[ov2n] OK VPN config already in place: {USER_VPN_CONFIG}")

    return USER_VPN_CONFIG


def import_v2ray_config(source_path: str) -> str:
    """
    将用户选择的 V2Ray 配置文件复制到用户配置目录。

    Args:
        source_path: 用户选择的源文件路径

    Returns:
        复制后的目标文件路径（即 USER_V2RAY_CONFIG）

    Raises:
        FileNotFoundError: 源文件不存在
        OSError: 复制失败
    """
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"源文件不存在: {source_path}")

    os.makedirs(_CONFIG_DIR, exist_ok=True)

    # 如果源文件和目标文件是同一个文件，无需复制
    src_real = os.path.realpath(source_path)
    dst_real = os.path.realpath(USER_V2RAY_CONFIG)
    if src_real != dst_real:
        shutil.copy2(source_path, USER_V2RAY_CONFIG)
        print(f"[ov2n] OK V2Ray config copied to: {USER_V2RAY_CONFIG}")
    else:
        print(f"[ov2n] OK V2Ray config already in place: {USER_V2RAY_CONFIG}")

    return USER_V2RAY_CONFIG


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
        print(f"[ov2n] ERR load tproxy config: {e}")
    return defaults


def save_tproxy_config(enabled: bool, vps_ip: str, port: int,
                       mark: int, table: int) -> None:
    """保存 TProxy 透明代理配置。"""
    try:
        os.makedirs(os.path.dirname(TPROXY_CONF_PATH), exist_ok=True)
        with open(TPROXY_CONF_PATH, "w") as f:
            f.write("# ov2n TProxy config\n")
            f.write(f"TPROXY_ENABLED={'true' if enabled else 'false'}\n")
            f.write(f"VPS_IP={vps_ip}\n")
            f.write(f"V2RAY_PORT={port}\n")
            f.write(f"MARK={mark}\n")
            f.write(f"TABLE={table}\n")
    except Exception as e:
        print(f"[ov2n] ERR save tproxy config: {e}")


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
        with open(config_path, 'r', encoding='utf-8-sig') as f:
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
            print(f"[ov2n] OK extracted: VPS IP={vps_ip}, TProxy port={tproxy_port}")
            return {'vps_ip': vps_ip, 'tproxy_port': tproxy_port}

        print(f"[ov2n] WARN extract incomplete: VPS IP={vps_ip}, TProxy port={tproxy_port}")
        return None
    except Exception as e:
        print(f"[ov2n] ERR extract failed: {e}")
        return None


def validate_v2ray_config(path: str) -> bool:
    """
    验证 V2Ray 配置文件是否有效（非空且包含 inbounds/outbounds）。
    支持含 // 单行注释的 JSON（xray Windows 模板格式）。

    增强容错：
      - 支持 UTF-8 BOM 编码
      - 捕获文件锁定、权限不足等 OS 异常
      - 空文件直接返回 False
    """
    try:
        if not os.path.exists(path):
            return False
        if os.path.getsize(path) == 0:
            return False
        with open(path, 'r', encoding='utf-8-sig') as f:
            raw = f.read()
        if not raw.strip():
            return False
        cfg = json.loads(_strip_json_comments(raw))
        return 'inbounds' in cfg and 'outbounds' in cfg
    except (OSError, IOError) as e:
        # 文件被锁定、权限不足等 → 不能确定无效，返回 True 以避免误覆盖
        print(f"[ov2n] WARN V2Ray config IO error (treated as valid): {e}")
        return True
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[ov2n] WARN V2Ray config JSON parse failed: {e}")
        return False
    except Exception as e:
        print(f"[ov2n] WARN V2Ray config validation error: {e}")
        return False


def has_real_vps_config(path: str) -> bool:
    """
    检查 V2Ray 配置文件是否包含真实的 VPS 服务器信息（非占位符）。

    用于判断用户是否已经成功导入过有效的 SS/V2Ray 配置。
    占位符地址包括：your.server.com, YOUR_VPS_IP, 127.0.0.1, placeholder 等。

    Returns:
        True  - 配置中包含看起来真实的 VPS 地址
        False - 配置中只有占位符或无法解析
    """
    placeholder_addresses = {
        "your.server.com", "your_vps_ip", "127.0.0.1",
        "0.0.0.0", "localhost", "example.com",
    }
    try:
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return False
        with open(path, 'r', encoding='utf-8-sig') as f:
            raw = f.read()
        cfg = json.loads(_strip_json_comments(raw))
        for ob in cfg.get('outbounds', []):
            if ob.get('protocol') in ('shadowsocks', 'vmess', 'vless', 'trojan'):
                servers = ob.get('settings', {}).get('servers', [])
                for srv in servers:
                    addr = srv.get('address', '').strip().lower()
                    if addr and addr not in placeholder_addresses:
                        return True
        return False
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
        print("[ov2n] OK default V2Ray config created")
    except Exception as e:
        print(f"[ov2n] ERR create default V2Ray config: {e}")


def _migrate_legacy_config_paths() -> None:
    """
    从旧版本的 config_paths.json 迁移配置文件到新的固定位置。

    旧版本将用户选择的配置文件路径保存在 config_paths.json 中，
    配置文件本身可能存储在任意位置（如用户的下载目录）。
    新版本要求配置文件统一存储在用户配置目录下。

    迁移逻辑：
      1. 读取 config_paths.json 中保存的旧路径
      2. 如果旧路径指向的文件存在且目标位置没有有效文件，则复制过来
      3. 迁移完成后删除 config_paths.json，避免重复迁移
      4. 同步更新 imported_flags.json
    """
    if not os.path.exists(_LEGACY_CONFIG_PATHS_FILE):
        return

    print("[ov2n] legacy config_paths.json detected, migrating...")

    try:
        with open(_LEGACY_CONFIG_PATHS_FILE, 'r', encoding='utf-8') as f:
            saved = json.load(f)
    except Exception as e:
        print(f"[ov2n] WARN read legacy config_paths.json failed: {e}")
        # 读取失败也删除，避免每次启动都尝试
        _remove_legacy_config_paths_file()
        return

    old_vpn_path = saved.get('vpn_config', '')
    old_v2ray_path = saved.get('v2ray_config', '')

    migrated_vpn = False
    migrated_v2ray = False

    # 迁移 VPN 配置
    if (old_vpn_path
            and os.path.exists(old_vpn_path)
            and os.path.realpath(old_vpn_path) != os.path.realpath(USER_VPN_CONFIG)):
        if not os.path.exists(USER_VPN_CONFIG) or os.path.getsize(USER_VPN_CONFIG) == 0:
            try:
                shutil.copy2(old_vpn_path, USER_VPN_CONFIG)
                print(f"[ov2n] OK VPN config migrated: {old_vpn_path} -> {USER_VPN_CONFIG}")
                migrated_vpn = True
            except Exception as e:
                print(f"[ov2n] WARN VPN config migration failed: {e}")
        else:
            print(f"[ov2n] VPN config already at destination, skip migration")
            migrated_vpn = True
    elif old_vpn_path and os.path.realpath(old_vpn_path) == os.path.realpath(USER_VPN_CONFIG):
        if os.path.exists(USER_VPN_CONFIG) and os.path.getsize(USER_VPN_CONFIG) > 0:
            migrated_vpn = True

    # 迁移 V2Ray 配置
    if (old_v2ray_path
            and os.path.exists(old_v2ray_path)
            and os.path.realpath(old_v2ray_path) != os.path.realpath(USER_V2RAY_CONFIG)):
        if not os.path.exists(USER_V2RAY_CONFIG) or os.path.getsize(USER_V2RAY_CONFIG) == 0:
            try:
                shutil.copy2(old_v2ray_path, USER_V2RAY_CONFIG)
                print(f"[ov2n] OK V2Ray config migrated: {old_v2ray_path} -> {USER_V2RAY_CONFIG}")
                migrated_v2ray = True
            except Exception as e:
                print(f"[ov2n] WARN V2Ray config migration failed: {e}")
        else:
            print(f"[ov2n] V2Ray config already at destination, skip migration")
            migrated_v2ray = True
    elif old_v2ray_path and os.path.realpath(old_v2ray_path) == os.path.realpath(USER_V2RAY_CONFIG):
        if os.path.exists(USER_V2RAY_CONFIG) and os.path.getsize(USER_V2RAY_CONFIG) > 0:
            migrated_v2ray = True

    # 同步更新 imported_flags
    if migrated_vpn or migrated_v2ray:
        flags = load_imported_flags()
        if migrated_vpn and not flags['vpn']:
            flags['vpn'] = True
        if migrated_v2ray and not flags['v2ray']:
            flags['v2ray'] = True
        save_imported_flags(flags['vpn'], flags['v2ray'])
        print(f"[ov2n] imported flags updated: vpn={flags['vpn']}, v2ray={flags['v2ray']}")

    _remove_legacy_config_paths_file()
    print("[ov2n] OK legacy config_paths.json migration done")


def _remove_legacy_config_paths_file() -> None:
    """安全删除旧版 config_paths.json。"""
    try:
        if os.path.exists(_LEGACY_CONFIG_PATHS_FILE):
            os.remove(_LEGACY_CONFIG_PATHS_FILE)
            print(f"[ov2n] removed legacy config_paths.json")
    except Exception as e:
        print(f"[ov2n] WARN remove legacy config_paths.json failed: {e}")


def init_config_dir() -> None:
    """
    初始化用户配置目录并执行必要的迁移。

    设计原则：
      - 程序第一次启动时，用户配置目录下没有任何配置文件，这是正常状态
      - 不再从开发目录复制模板文件，也不再自动创建默认配置
      - 用户需要通过以下方式导入配置：
        1. 通过文件选择器选择 .ovpn 或 config.json
        2. 拖拽文件到窗口
        3. 从剪贴板导入 ss:// 链接
      - 导入后，配置文件会被复制到用户配置目录下永久保存

    迁移逻辑：
      - 如果检测到旧版 config_paths.json，自动将旧路径指向的配置文件
        复制到新的固定位置，确保升级后不丢失用户配置
    """
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    print(f"[ov2n] config dir: {_CONFIG_DIR}")

    # 执行旧版本迁移（如果需要）
    _migrate_legacy_config_paths()
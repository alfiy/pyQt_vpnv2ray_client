"""
SS URL 配置管理器 (修复版)
负责解析 SS URL 并生成/更新 V2Ray 配置

修复内容:
- 修复 Base64 格式判断逻辑,正确处理 ss://base64==@server:port 格式
- 支持混合格式: ss://base64@server:port
- 增强调试信息
- 修复 warn_legacy 误判：只有完全Base64且解码后含@的才是真正遗留格式
"""
import json
import os
import re
import base64
import urllib.parse
from typing import List, Dict, Optional, Tuple
from PyQt5.QtWidgets import QMessageBox


class ShadowsocksServer:
    """Shadowsocks 服务器配置"""
    
    def __init__(self):
        self.address: str = ""
        self.port: int = 0
        self.method: str = ""
        self.password: str = ""
        self.remark: str = ""
        self.warn_legacy: bool = False  # 是否使用遗留格式
    
    def to_v2ray_outbound(self, tag: str = "proxy") -> Dict:
        """转换为 V2Ray/Xray outbound 配置"""
        return {
            "tag": tag,
            "protocol": "shadowsocks",
            "settings": {
                "servers": [
                    {
                        "address": self.address,
                        "port": self.port,
                        "method": self.method,
                        "password": self.password
                    }
                ]
            },
            "streamSettings": {
                "sockopt": {
                    "mark": 255
                }
            }
        }
    
    def __str__(self) -> str:
        return f"{self.remark or 'Unnamed'} ({self.address}:{self.port})"


class SSUrlParser:
    """SIP002 SS URL 解析器 (增强版)"""
    
    # 支持的加密方法列表
    SUPPORTED_METHODS = [
        "aes-256-gcm", "aes-128-gcm", "chacha20-poly1305", "chacha20-ietf-poly1305",
        "aes-256-cfb", "aes-128-cfb", "chacha20", "chacha20-ietf",
        "rc4-md5", "none"
    ]
    
    @staticmethod
    def parse(ss_url: str) -> Optional[ShadowsocksServer]:
        """
        解析 SS URL，支持以下三种格式:
        1. ss://method:password@server:port#remark          (明文, 现代格式)
        2. ss://base64(method:password)@server:port#remark  (混合 Base64, 现代格式)
        3. ss://base64(method:password@server:port)#remark  (完全 Base64, 遗留格式)

        warn_legacy 判断规则:
        - 格式1、格式2: warn_legacy = False (现代合法格式)
        - 格式3: warn_legacy = True  (真正的遗留格式，解码后才能拿到服务器地址)
        """
        if not ss_url or not ss_url.startswith("ss://"):
            return None
        
        try:
            # 移除 ss:// 前缀
            content = ss_url[5:]
            
            server = ShadowsocksServer()
            
            # 提取备注 (# 后面的内容)
            if "#" in content:
                remark_encoded = content.split("#")[-1]
                content = content.rsplit("#", 1)[0]
                try:
                    server.remark = urllib.parse.unquote(remark_encoded)
                except:
                    server.remark = remark_encoded
            
            # ==================== 判断格式 ====================
            is_plaintext = False
            
            if "@" in content:
                userinfo_part = content.split("@")[0]
                if ":" in userinfo_part:
                    method_candidate = userinfo_part.split(":")[0]
                    method_lower = method_candidate.lower()
                    if method_lower in [m.lower() for m in SSUrlParser.SUPPORTED_METHODS]:
                        is_plaintext = True
                        print(f"[解析] 检测到明文格式: method={method_candidate}")
            
            # ==================== 按格式解析 ====================
            if is_plaintext:
                # 格式1: 明文 method:password@server:port，现代格式，不标记遗留
                user_info, server_part = content.rsplit("@", 1)
                server.warn_legacy = False
                print(f"[解析] 明文模式: userinfo={user_info}, server={server_part}")

            else:
                # Base64 编码格式（格式2 或 格式3）
                print(f"[解析] Base64 模式: content={content}")

                if "@" in content:
                    # 格式2: ss://base64(method:password)@server:port
                    # URL 中有 @，服务器地址直接可见，属于现代合法格式
                    base64_part, server_part = content.split("@", 1)
                    print(f"[解析] 混合 Base64 格式 (现代): base64={base64_part}, server={server_part}")

                    base64_str = base64_part.replace("-", "+").replace("_", "/")
                    padding = 4 - len(base64_str) % 4
                    if padding != 4:
                        base64_str += "=" * padding

                    try:
                        decoded = base64.b64decode(base64_str).decode("utf-8")
                        print(f"[解析] Base64 解码成功: {decoded}")
                    except Exception as e:
                        print(f"[解析] Base64 解码失败: {e}")
                        return None

                    if "@" in decoded:
                        # 解码后仍含 @，说明 base64 部分编码了完整的 user@host 信息
                        # 以解码内容的 user_info 为准，server_part 仍用 URL 中的
                        user_info, _ = decoded.rsplit("@", 1)
                    else:
                        user_info = decoded

                    # 格式2 是现代合法格式，不标记遗留
                    server.warn_legacy = False

                else:
                    # 格式3: ss://base64(method:password@server:port)，完全编码
                    # 服务器地址隐藏在 Base64 中，属于遗留格式
                    base64_part = content
                    server_part = None
                    print(f"[解析] 完全 Base64 格式 (遗留): base64={base64_part}")

                    base64_str = base64_part.replace("-", "+").replace("_", "/")
                    padding = 4 - len(base64_str) % 4
                    if padding != 4:
                        base64_str += "=" * padding

                    try:
                        decoded = base64.b64decode(base64_str).decode("utf-8")
                        print(f"[解析] Base64 解码成功: {decoded}")
                    except Exception as e:
                        print(f"[解析] Base64 解码失败: {e}")
                        return None

                    if "@" in decoded:
                        # 解码后含 @：完整的 method:password@server:port，真正的遗留格式
                        user_info, server_part = decoded.rsplit("@", 1)
                        server.warn_legacy = True  # ← 只在这里标记遗留
                        print(f"[解析] 标记为遗留格式")
                    else:
                        # 解码后不含 @：理论上不应出现，尝试当作纯 user_info 处理
                        user_info = decoded
                        server.warn_legacy = False
                        print(f"[解析] 完全 Base64 解码后无 @，当作 user_info 处理")

                if not server_part:
                    print(f"[解析] 缺少服务器信息")
                    return None

            # ==================== 解析用户信息 ====================
            if ":" not in user_info:
                print(f"[解析] 用户信息格式错误: {user_info}")
                return None
            
            server.method, server.password = user_info.split(":", 1)
            print(f"[解析] 加密方法: {server.method}, 密码: {server.password[:3]}***")
            
            # ==================== 解析服务器信息 ====================
            if not server_part or ":" not in server_part:
                print(f"[解析] 服务器信息格式错误: {server_part}")
                return None
            
            if server_part.startswith("[") and "]:" in server_part:
                # IPv6: [::1]:8080
                server.address, port_str = server_part.rsplit(":", 1)
                server.address = server.address[1:-1]
                server.port = int(port_str)
            else:
                # IPv4/域名: 1.2.3.4:8080
                server.address, port_str = server_part.rsplit(":", 1)
                server.port = int(port_str)
            
            print(f"[解析] 服务器地址: {server.address}:{server.port}")
            
            # ==================== 验证加密方法 ====================
            if server.method not in SSUrlParser.SUPPORTED_METHODS:
                method_lower = server.method.lower()
                for m in SSUrlParser.SUPPORTED_METHODS:
                    if m.lower() == method_lower:
                        server.method = m
                        break
            
            print(f"[解析] ✓ 解析成功: {server} (遗留格式={server.warn_legacy})")
            return server
            
        except Exception as e:
            print(f"[解析] ✗ 解析失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    @staticmethod
    def parse_multiple(input_text: str) -> List[ShadowsocksServer]:
        """
        解析多个 SS URL（支持换行、逗号、空格分隔）
        """
        servers = []
        if not input_text:
            return servers
        
        urls = re.findall(r'ss://[^\s,]+', input_text)
        
        for url in urls:
            server = SSUrlParser.parse(url)
            if server:
                servers.append(server)
        
        return servers


class V2RayConfigManager:
    """V2Ray 配置管理器"""
    
    DEFAULT_CONFIG = {
        "log": {
            "loglevel": "warning"
        },
        "dns": {
            "servers": [
                "8.8.8.8",
                "1.1.1.1"
            ]
        },
        "inbounds": [
            {
                "listen": "127.0.0.1",
                "port": 1080,
                "protocol": "http",
                "tag": "http-in"
            },
            {
                "listen": "127.0.0.1",
                "port": 1081,
                "protocol": "socks",
                "settings": {
                    "udp": True
                },
                "tag": "socks-in"
            },
            {
                "listen": "0.0.0.0",
                "port": 12345,
                "protocol": "dokodemo-door",
                "settings": {
                    "network": "tcp,udp",
                    "followRedirect": True
                },
                "streamSettings": {
                    "sockopt": {
                        "tproxy": "tproxy"
                    }
                },
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls"]
                },
                "tag": "tproxy-in"
            }
        ],
        "outbounds": [
            {
                "tag": "proxy",
                "protocol": "shadowsocks",
                "settings": {
                    "servers": [
                        {
                            "address": "127.0.0.1",
                            "port": 8388,
                            "method": "aes-256-gcm",
                            "password": "placeholder"
                        }
                    ]
                },
                "streamSettings": {
                    "sockopt": {
                        "mark": 255
                    }
                }
            },
            {
                "tag": "direct",
                "protocol": "freedom",
                "settings": {},
                "streamSettings": {
                    "sockopt": {
                        "mark": 255
                    }
                }
            }
        ],
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [
                {
                    "type": "field",
                    "ip": ["geoip:private"],
                    "outboundTag": "direct"
                },
                {
                    "type": "field",
                    "port": "53",
                    "network": "udp",
                    "outboundTag": "proxy"
                },
                {
                    "type": "field",
                    "domain": ["geosite:cn"],
                    "outboundTag": "direct"
                },
                {
                    "type": "field",
                    "ip": ["geoip:cn"],
                    "outboundTag": "direct"
                },
                {
                    "type": "field",
                    "network": "tcp,udp",
                    "outboundTag": "proxy"
                }
            ]
        }
    }
    
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self) -> Dict:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载配置失败，使用默认配置: {e}")
                return self.DEFAULT_CONFIG.copy()
        return self.DEFAULT_CONFIG.copy()
    
    def save_config(self) -> bool:
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"保存配置失败: {e}")
            return False
    
    def update_shadowsocks_server(self, server: ShadowsocksServer) -> bool:
        try:
            if "outbounds" not in self.config:
                self.config["outbounds"] = []
            
            outbounds = self.config["outbounds"]
            proxy_index = -1
            for i, outbound in enumerate(outbounds):
                if outbound.get("tag") == "proxy":
                    proxy_index = i
                    break
            
            new_outbound = server.to_v2ray_outbound("proxy")
            
            if proxy_index >= 0:
                outbounds[proxy_index] = new_outbound
            else:
                outbounds.insert(0, new_outbound)
            
            return self.save_config()
            
        except Exception as e:
            print(f"更新服务器配置失败: {e}")
            return False
    
    def add_shadowsocks_server(self, server: ShadowsocksServer) -> bool:
        try:
            if "outbounds" not in self.config:
                self.config["outbounds"] = []
            
            base_tag = "ss-" + server.address.replace(".", "-")
            tag = base_tag
            counter = 1
            
            existing_tags = {o.get("tag") for o in self.config["outbounds"]}
            while tag in existing_tags:
                tag = f"{base_tag}-{counter}"
                counter += 1
            
            new_outbound = server.to_v2ray_outbound(tag)
            self.config["outbounds"].append(new_outbound)
            
            return self.save_config()
            
        except Exception as e:
            print(f"添加服务器配置失败: {e}")
            return False
    
    def get_current_servers(self) -> List[Tuple[str, str, int]]:
        servers = []
        for outbound in self.config.get("outbounds", []):
            if outbound.get("protocol") == "shadowsocks":
                settings = outbound.get("settings", {})
                server_list = settings.get("servers", [])
                for s in server_list:
                    servers.append((
                        outbound.get("tag", "unknown"),
                        s.get("address", ""),
                        s.get("port", 0)
                    ))
        return servers


class SSConfigDialog:
    """SS 配置导入对话框（简化版，使用标准 QMessageBox）"""
    
    @staticmethod
    def ask_import_ss_url(parent, url: str, server: ShadowsocksServer) -> bool:
        preview = f"{server.remark or 'New Server'} ({server.address}:{server.port})"
        
        reply = QMessageBox.question(
            parent,
            "确认导入",
            f"从以下 URL 导入服务器配置?\n\n{preview}\n\n{url[:80]}...",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        return reply == QMessageBox.Yes
    
    @staticmethod
    def show_success(parent, server: ShadowsocksServer):
        QMessageBox.information(
            parent,
            "导入成功",
            f"已成功导入服务器:\n{server.remark or 'Unnamed'}\n"
            f"地址: {server.address}:{server.port}\n"
            f"加密: {server.method}"
        )
    
    @staticmethod
    def show_error(parent, message: str):
        QMessageBox.critical(parent, "导入失败", message)
    
    @staticmethod
    def show_legacy_warning(parent, server: ShadowsocksServer):
        QMessageBox.warning(
            parent,
            "警告",
            f"服务器 \"{server}\" 使用了遗留的 ss:// 链接格式。\n\n"
            f"建议更新为新的 SIP002 标准格式以获得更好的兼容性。"
        )


def import_ss_url_from_clipboard(parent, config_path: str, 
                                  replace_existing: bool = True) -> bool:
    from PyQt5.QtWidgets import QApplication
    
    clipboard = QApplication.clipboard()
    text = clipboard.text()
    
    if not text:
        SSConfigDialog.show_error(parent, "剪贴板为空")
        return False
    
    servers = SSUrlParser.parse_multiple(text)
    
    if not servers:
        server = SSUrlParser.parse(text.strip())
        if server:
            servers = [server]
    
    if not servers:
        SSConfigDialog.show_error(parent, 
            "剪贴板中没有找到有效的 SS URL\n\n"
            "支持的格式:\n"
            "• ss://method:password@server:port#remark\n"
            "• ss://base64(method:password@server:port)#remark\n"
            "• ss://base64(method:password)@server:port#remark")
        return False
    
    server = servers[0]
    
    if not SSConfigDialog.ask_import_ss_url(parent, text.strip(), server):
        return False
    
    manager = V2RayConfigManager(config_path)
    
    if replace_existing:
        success = manager.update_shadowsocks_server(server)
    else:
        success = manager.add_shadowsocks_server(server)
    
    if success:
        SSConfigDialog.show_success(parent, server)
        
        # 只有真正的遗留格式才显示警告
        if server.warn_legacy:
            SSConfigDialog.show_legacy_warning(parent, server)
        
        return True
    else:
        SSConfigDialog.show_error(parent, "保存配置失败，请检查文件权限")
        return False
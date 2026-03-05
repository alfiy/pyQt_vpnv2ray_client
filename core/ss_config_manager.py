"""
SS URL 配置管理器
负责解析 SS URL 并生成/更新 V2Ray 配置
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
    """SIP002 SS URL 解析器"""
    
    # 支持的加密方法列表
    SUPPORTED_METHODS = [
        "aes-256-gcm", "aes-128-gcm", "chacha20-poly1305", "chacha20-ietf-poly1305",
        "aes-256-cfb", "aes-128-cfb", "chacha20", "chacha20-ietf",
        "rc4-md5", "none"
    ]
    
    @staticmethod
    def parse(ss_url: str) -> Optional[ShadowsocksServer]:
        """
        解析 SS URL (SIP002 标准)
        支持格式:
        - ss://method:password@server:port#remark (明文)
        - ss://base64(method:password@server:port)#remark (Base64)
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
            
            # 判断是否为 Base64 编码
            if "@" in content and ":" in content.split("@")[0]:
                # 明文格式: method:password@server:port
                user_info, server_part = content.rsplit("@", 1)
            else:
                # Base64 编码格式
                # 处理可能的 URL 安全 Base64 (替换 -_ 为 +/)
                base64_str = content.replace("-", "+").replace("_", "/")
                # 补齐 padding
                padding = 4 - len(base64_str) % 4
                if padding != 4:
                    base64_str += "=" * padding
                
                try:
                    decoded = base64.b64decode(base64_str).decode("utf-8")
                except Exception:
                    return None
                
                if "@" not in decoded:
                    return None
                
                user_info, server_part = decoded.rsplit("@", 1)
                server.warn_legacy = True  # 标记为遗留格式
            
            # 解析用户信息 (method:password)
            if ":" not in user_info:
                return None
            
            server.method, server.password = user_info.split(":", 1)
            
            # 解析服务器部分 (server:port)
            if ":" not in server_part:
                return None
            
            # 处理 IPv6 地址 [addr]:port 和普通地址 addr:port
            if server_part.startswith("[") and "]:" in server_part:
                # IPv6 格式: [::1]:8080
                server.address, port_str = server_part.rsplit(":", 1)
                server.address = server.address[1:-1]  # 去掉 []
                server.port = int(port_str)
            else:
                # IPv4/域名格式: 1.2.3.4:8080 或 domain.com:8080
                server.address, port_str = server_part.rsplit(":", 1)
                server.port = int(port_str)
            
            # 验证加密方法
            if server.method not in SSUrlParser.SUPPORTED_METHODS:
                # 尝试匹配，可能是大小写问题
                method_lower = server.method.lower()
                if method_lower in [m.lower() for m in SSUrlParser.SUPPORTED_METHODS]:
                    # 标准化方法名
                    for m in SSUrlParser.SUPPORTED_METHODS:
                        if m.lower() == method_lower:
                            server.method = m
                            break
            
            return server
            
        except Exception as e:
            print(f"解析 SS URL 失败: {e}")
            return None
    
    @staticmethod
    def parse_multiple(input_text: str) -> List[ShadowsocksServer]:
        """
        解析多个 SS URL（支持换行、逗号、空格分隔）
        """
        servers = []
        if not input_text:
            return servers
        
        # 清理并分割输入
        # 支持 ss:// 开头的任何内容
        urls = re.findall(r'ss://[^\s,]+', input_text)
        
        for url in urls:
            server = SSUrlParser.parse(url)
            if server:
                servers.append(server)
        
        return servers


class V2RayConfigManager:
    """V2Ray 配置管理器"""
    
    # 默认 V2Ray 配置模板
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
        """加载现有配置或创建默认配置"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载配置失败，使用默认配置: {e}")
                return self.DEFAULT_CONFIG.copy()
        return self.DEFAULT_CONFIG.copy()
    
    def save_config(self) -> bool:
        """保存配置到文件"""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"保存配置失败: {e}")
            return False
    
    def update_shadowsocks_server(self, server: ShadowsocksServer) -> bool:
        """
        更新 Shadowsocks 服务器配置（替换现有的 proxy outbound）
        """
        try:
            # 确保 outbounds 存在
            if "outbounds" not in self.config:
                self.config["outbounds"] = []
            
            outbounds = self.config["outbounds"]
            
            # 查找并替换现有的 shadowsocks outbound
            proxy_index = -1
            for i, outbound in enumerate(outbounds):
                if outbound.get("tag") == "proxy":
                    proxy_index = i
                    break
            
            new_outbound = server.to_v2ray_outbound("proxy")
            
            if proxy_index >= 0:
                outbounds[proxy_index] = new_outbound
            else:
                # 如果没有找到 proxy tag，插入到第一个位置
                outbounds.insert(0, new_outbound)
            
            return self.save_config()
            
        except Exception as e:
            print(f"更新服务器配置失败: {e}")
            return False
    
    def add_shadowsocks_server(self, server: ShadowsocksServer) -> bool:
        """
        添加新的 Shadowsocks 服务器（作为新的 outbound）
        """
        try:
            if "outbounds" not in self.config:
                self.config["outbounds"] = []
            
            # 生成唯一的 tag
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
        """获取当前配置中的所有 SS 服务器列表 (tag, address, port)"""
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
        """
        询问用户是否确认导入（模仿 Shadowsocks-Windows 的 AskAddServerBySSURL）
        """
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
        """显示导入成功消息"""
        QMessageBox.information(
            parent,
            "导入成功",
            f"已成功导入服务器:\n{server.remark or 'Unnamed'}\n"
            f"地址: {server.address}:{server.port}\n"
            f"加密: {server.method}"
        )
    
    @staticmethod
    def show_error(parent, message: str):
        """显示错误消息"""
        QMessageBox.critical(parent, "导入失败", message)
    
    @staticmethod
    def show_legacy_warning(parent, server: ShadowsocksServer):
        """显示遗留格式警告"""
        QMessageBox.warning(
            parent,
            "警告",
            f"服务器 \"{server}\" 使用了遗留的 ss:// 链接格式。\n\n"
            f"建议更新为新的 SIP002 标准格式以获得更好的兼容性。"
        )


def import_ss_url_from_clipboard(parent, config_path: str, 
                                  replace_existing: bool = True) -> bool:
    """
    从剪贴板导入 SS URL（主入口函数）
    
    Args:
        parent: 父窗口（用于显示对话框）
        config_path: V2Ray 配置文件路径
        replace_existing: 是否替换现有配置（True=替换 proxy outbound，False=添加新 outbound）
    
    Returns:
        bool: 是否成功导入
    """
    from PyQt5.QtWidgets import QApplication
    
    # 获取剪贴板内容
    clipboard = QApplication.clipboard()
    text = clipboard.text()
    
    if not text:
        SSConfigDialog.show_error(parent, "剪贴板为空")
        return False
    
    # 解析 URL
    servers = SSUrlParser.parse_multiple(text)
    
    if not servers:
        # 尝试单条解析
        server = SSUrlParser.parse(text.strip())
        if server:
            servers = [server]
    
    if not servers:
        SSConfigDialog.show_error(parent, 
            "剪贴板中没有找到有效的 SS URL\n\n"
            "支持的格式:\n"
            "• ss://method:password@server:port#remark\n"
            "• ss://base64(method:password@server:port)#remark")
        return False
    
    # 处理第一个服务器（目前只处理单个，可扩展为批量）
    server = servers[0]
    
    # 确认导入
    if not SSConfigDialog.ask_import_ss_url(parent, text.strip(), server):
        return False
    
    # 更新配置
    manager = V2RayConfigManager(config_path)
    
    if replace_existing:
        success = manager.update_shadowsocks_server(server)
    else:
        success = manager.add_shadowsocks_server(server)
    
    if success:
        SSConfigDialog.show_success(parent, server)
        
        # 显示遗留格式警告
        if server.warn_legacy:
            SSConfigDialog.show_legacy_warning(parent, server)
        
        return True
    else:
        SSConfigDialog.show_error(parent, "保存配置失败，请检查文件权限")
        return False
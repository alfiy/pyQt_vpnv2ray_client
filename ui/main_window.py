"""
主窗口界面 - 重新设计版本
核心设计:
1. 统一 PID 管理: self.vpn_pid 和 self.v2ray_pid
2. 智能联合启动: 自动检测并只启动未运行的服务
3. 智能联合停止: 自动检测并只停止已运行的服务
4. 独立启动 V2Ray 时也配置 TProxy
"""
import os
import sys
import time
import subprocess
from PyQt5.QtGui import QIcon, QDragEnterEvent, QDropEvent
from PyQt5.QtCore import Qt, QThread, pyqtSignal
import re
import json
from PyQt5.QtWidgets import (
    QMainWindow, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QWidget,
    QFileDialog, QMessageBox, QCheckBox, QLineEdit,
    QGroupBox, QFormLayout, QSpinBox
)
from core.ss_config_manager import (
    import_ss_url_from_clipboard, 
    V2RayConfigManager,
    SSUrlParser
)
from core.polkit_helper import PolkitHelper

# ============================================
# 辅助函数 (保持不变)
# ============================================
def get_app_root():
    """获取程序根目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 配置文件路径
TPROXY_CONF_PATH = os.path.expanduser("~/.config/ov2n/tproxy.conf")
CONFIG_PATHS_FILE = os.path.expanduser("~/.config/ov2n/config_paths.json")

def load_config_paths():
    """加载上次使用的配置文件路径"""
    defaults = {
        'vpn_config': os.path.expanduser("~/.config/ov2n/client.ovpn"),
        'v2ray_config': os.path.expanduser("~/.config/ov2n/config.json")
    }
    
    if not os.path.exists(CONFIG_PATHS_FILE):
        return defaults
    
    try:
        with open(CONFIG_PATHS_FILE, 'r', encoding='utf-8') as f:
            saved_paths = json.load(f)
        
        vpn_path = saved_paths.get('vpn_config', defaults['vpn_config'])
        v2ray_path = saved_paths.get('v2ray_config', defaults['v2ray_config'])
        
        if not os.path.exists(vpn_path):
            vpn_path = defaults['vpn_config']
        
        if not os.path.exists(v2ray_path):
            v2ray_path = defaults['v2ray_config']
        
        return {
            'vpn_config': vpn_path,
            'v2ray_config': v2ray_path
        }
    except Exception as e:
        print(f"加载配置路径失败: {e}")
        return defaults

def save_config_paths(vpn_config, v2ray_config):
    """保存当前使用的配置文件路径"""
    try:
        config_dir = os.path.dirname(CONFIG_PATHS_FILE)
        os.makedirs(config_dir, exist_ok=True)
        
        paths = {
            'vpn_config': vpn_config,
            'v2ray_config': v2ray_config
        }
        
        with open(CONFIG_PATHS_FILE, 'w', encoding='utf-8') as f:
            json.dump(paths, f, indent=2, ensure_ascii=False)
        
        print(f"✓ 配置路径已保存")
    except Exception as e:
        print(f"保存配置路径失败: {e}")

def load_tproxy_config():
    """从配置文件加载 tproxy 参数"""
    defaults = {
        "enabled": False,
        "vps_ip": "",
        "port": 12345,
        "mark": 1,
        "table": 100,
    }
    if not os.path.exists(TPROXY_CONF_PATH):
        return defaults

    try:
        data = {}
        with open(TPROXY_CONF_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    data[key.strip()] = val.strip()

        defaults["enabled"] = data.get("TPROXY_ENABLED", "false").lower() == "true"
        defaults["vps_ip"] = data.get("VPS_IP", "")
        defaults["port"] = int(data.get("V2RAY_PORT", 12345))
        defaults["mark"] = int(data.get("MARK", 1))
        defaults["table"] = int(data.get("TABLE", 100))
    except Exception as e:
        print(f"加载 tproxy 配置失败: {e}")

    return defaults

def save_tproxy_config(enabled, vps_ip, port, mark, table):
    """保存 tproxy 参数到配置文件"""
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

def extract_tproxy_config_from_v2ray(config_path):
    """从 V2Ray 配置文件中自动提取 TProxy 相关参数"""
    if not os.path.exists(config_path):
        return None
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        vps_ip = None
        tproxy_port = None
        
        # 提取服务器 IP
        outbounds = config.get('outbounds', [])
        for outbound in outbounds:
            if outbound.get('protocol') in ['shadowsocks', 'vmess', 'vless', 'trojan', 'socks', 'http']:
                settings = outbound.get('settings', {})
                servers = settings.get('servers', [])
                if servers and len(servers) > 0:
                    server = servers[0]
                    address = server.get('address', '')
                    if address and re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', address):
                        vps_ip = address
                        break
        
        # 提取 TProxy 端口
        inbounds = config.get('inbounds', [])
        for inbound in inbounds:
            protocol = inbound.get('protocol', '')
            if protocol == 'dokodemo-door':
                port = inbound.get('port')
                settings = inbound.get('settings', {})
                if settings.get('network') in ['tcp,udp', 'tcp', 'udp']:
                    tproxy_port = port
                    break
            elif 'tproxy' in inbound.get('tag', '').lower():
                tproxy_port = inbound.get('port')
                break
        
        if vps_ip and tproxy_port:
            print(f"✓ 自动提取配置成功: VPS IP={vps_ip}, TProxy端口={tproxy_port}")
            return {
                'vps_ip': vps_ip,
                'tproxy_port': tproxy_port
            }
        else:
            print(f"⚠ 配置提取不完整: VPS IP={vps_ip}, TProxy端口={tproxy_port}")
            return None
    except Exception as e:
        print(f"✗ 提取配置失败: {e}")
        return None


# ============================================
# 独立启动线程
# ============================================
class SingleVPNThread(QThread):
    """独立的 OpenVPN 启动线程"""
    update_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    success_signal = pyqtSignal(int)  # 发送 PID
    
    def __init__(self, vpn_config_path):
        super().__init__()
        self.vpn_config_path = vpn_config_path
    
    def run(self):
        try:
            self.update_signal.emit("正在启动 OpenVPN...")
            
            cmd = [
                "pkexec",
                PolkitHelper.HELPER_SCRIPT,
                "start-vpn-only",
                self.vpn_config_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'OpenVPN PID:' in line:
                        pid = int(line.split(':')[1].strip())
                        self.success_signal.emit(pid)
                        return
                self.error_signal.emit("无法获取 OpenVPN PID")
            else:
                error = result.stderr.strip() if result.stderr else "启动失败"
                if "dismissed" in error.lower() or "cancelled" in error.lower():
                    self.error_signal.emit("用户取消了权限授权")
                else:
                    self.error_signal.emit(f"OpenVPN 启动失败:\n{error}")
        except Exception as e:
            self.error_signal.emit(f"OpenVPN 启动异常: {str(e)}")


class SingleV2RayThread(QThread):
    """独立的 V2Ray 启动线程 (带 TProxy 配置)"""
    update_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    success_signal = pyqtSignal(dict)  # 发送 {pid, tproxy_ok}
    
    def __init__(self, v2ray_config_path, tproxy_enabled=False, 
                 tproxy_port=12345, tproxy_vps_ip="", tproxy_mark=1, tproxy_table=100):
        super().__init__()
        self.v2ray_config_path = v2ray_config_path
        self.tproxy_enabled = tproxy_enabled
        self.tproxy_port = tproxy_port
        self.tproxy_vps_ip = tproxy_vps_ip
        self.tproxy_mark = tproxy_mark
        self.tproxy_table = tproxy_table
    
    def run(self):
        try:
            # 步骤 1: 启动 V2Ray
            self.update_signal.emit("正在启动 V2Ray...")
            
            cmd = [
                "pkexec",
                PolkitHelper.HELPER_SCRIPT,
                "start-v2ray-only",
                self.v2ray_config_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                error = result.stderr.strip() if result.stderr else "启动失败"
                if "dismissed" in error.lower() or "cancelled" in error.lower():
                    self.error_signal.emit("用户取消了权限授权")
                else:
                    self.error_signal.emit(f"V2Ray 启动失败:\n{error}")
                return
            
            # 解析 PID
            v2ray_pid = None
            for line in result.stdout.split('\n'):
                if 'V2Ray PID:' in line:
                    v2ray_pid = int(line.split(':')[1].strip())
                    break
            
            if not v2ray_pid:
                self.error_signal.emit("无法获取 V2Ray PID")
                return
            
            # 步骤 2: 配置 TProxy (如果启用)
            tproxy_ok = False
            if self.tproxy_enabled:
                self.update_signal.emit("正在配置透明代理...")
                time.sleep(1)  # 等待 V2Ray 完全启动
                
                tproxy_success, tproxy_msg = PolkitHelper.start_tproxy(
                    self.tproxy_port,
                    self.tproxy_vps_ip,
                    self.tproxy_mark,
                    self.tproxy_table
                )
                
                if tproxy_success:
                    tproxy_ok = True
                    self.update_signal.emit("✓ 透明代理已配置")
                else:
                    self.update_signal.emit(f"⚠ 透明代理配置失败: {tproxy_msg}")
            
            # 发送成功信号
            self.success_signal.emit({
                'pid': v2ray_pid,
                'tproxy_ok': tproxy_ok
            })
            
        except Exception as e:
            self.error_signal.emit(f"V2Ray 启动异常: {str(e)}")


class CombinedStartThread(QThread):
    """智能联合启动线程"""
    update_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    success_signal = pyqtSignal(dict)  # {vpn_pid, v2ray_pid, tproxy_ok}
    
    def __init__(self, vpn_config_path, v2ray_config_path,
                 current_vpn_pid, current_v2ray_pid,
                 tproxy_enabled=False, tproxy_port=12345,
                 tproxy_vps_ip="", tproxy_mark=1, tproxy_table=100):
        super().__init__()
        self.vpn_config_path = vpn_config_path
        self.v2ray_config_path = v2ray_config_path
        self.current_vpn_pid = current_vpn_pid
        self.current_v2ray_pid = current_v2ray_pid
        self.tproxy_enabled = tproxy_enabled
        self.tproxy_port = tproxy_port
        self.tproxy_vps_ip = tproxy_vps_ip
        self.tproxy_mark = tproxy_mark
        self.tproxy_table = tproxy_table
    
    def run(self):
        try:
            result_vpn_pid = self.current_vpn_pid
            result_v2ray_pid = self.current_v2ray_pid
            tproxy_ok = False
            
            # 步骤 1: 启动 VPN (如果未运行)
            if not self.current_vpn_pid:
                self.update_signal.emit("正在启动 OpenVPN...")
                
                cmd = [
                    "pkexec",
                    PolkitHelper.HELPER_SCRIPT,
                    "start-vpn-only",
                    self.vpn_config_path
                ]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode != 0:
                    error = result.stderr.strip() if result.stderr else "启动失败"
                    self.error_signal.emit(f"OpenVPN 启动失败:\n{error}")
                    return
                
                for line in result.stdout.split('\n'):
                    if 'OpenVPN PID:' in line:
                        result_vpn_pid = int(line.split(':')[1].strip())
                        break
                
                if not result_vpn_pid:
                    self.error_signal.emit("无法获取 OpenVPN PID")
                    return
            else:
                self.update_signal.emit("OpenVPN 已在运行,跳过启动")
            
            # 步骤 2: 启动 V2Ray (如果未运行)
            if not self.current_v2ray_pid:
                self.update_signal.emit("正在启动 V2Ray...")
                
                cmd = [
                    "pkexec",
                    PolkitHelper.HELPER_SCRIPT,
                    "start-v2ray-only",
                    self.v2ray_config_path
                ]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode != 0:
                    error = result.stderr.strip() if result.stderr else "启动失败"
                    self.error_signal.emit(f"V2Ray 启动失败:\n{error}")
                    # 如果刚启动了 VPN,需要回滚
                    if result_vpn_pid and not self.current_vpn_pid:
                        self._stop_process(result_vpn_pid, "openvpn")
                    return
                
                for line in result.stdout.split('\n'):
                    if 'V2Ray PID:' in line:
                        result_v2ray_pid = int(line.split(':')[1].strip())
                        break
                
                if not result_v2ray_pid:
                    self.error_signal.emit("无法获取 V2Ray PID")
                    # 回滚 VPN
                    if result_vpn_pid and not self.current_vpn_pid:
                        self._stop_process(result_vpn_pid, "openvpn")
                    return
            else:
                self.update_signal.emit("V2Ray 已在运行,跳过启动")
            
            # 步骤 3: 配置 TProxy (如果启用且 V2Ray 新启动或需要配置)
            if self.tproxy_enabled:
                self.update_signal.emit("正在配置透明代理...")
                time.sleep(1)
                
                tproxy_success, tproxy_msg = PolkitHelper.start_tproxy(
                    self.tproxy_port,
                    self.tproxy_vps_ip,
                    self.tproxy_mark,
                    self.tproxy_table
                )
                
                if tproxy_success:
                    tproxy_ok = True
                else:
                    self.update_signal.emit(f"⚠ 透明代理配置失败: {tproxy_msg}")
            
            # 发送成功信号
            self.success_signal.emit({
                'vpn_pid': result_vpn_pid,
                'v2ray_pid': result_v2ray_pid,
                'tproxy_ok': tproxy_ok
            })
            
        except Exception as e:
            self.error_signal.emit(f"启动异常: {str(e)}")
    
    def _stop_process(self, pid, name):
        """回滚时停止进程"""
        try:
            cmd = [
                "pkexec",
                PolkitHelper.HELPER_SCRIPT,
                "stop",
                f"--{name}-pid", str(pid)
            ]
            subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except:
            pass


# ============================================
# 主窗口类 (核心修改)
# ============================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ov2n Client")
        self.setGeometry(200, 200, 400, 750)
        self.setAcceptDrops(True)  # 启用拖拽
        
        # 设置窗口图标
        app_root = get_app_root()
        icon_path = os.path.join(app_root, "resources", "images", "ov2n256.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # ==================== 连接状态区域 ====================
        self.status_group = QGroupBox("连接状态")
        self.status_group.setStyleSheet("""
            QGroupBox {
                font-size: 13px;
                font-weight: bold;
                border: 1px solid #ccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        status_layout = QVBoxLayout()
        
        # VPN 状态
        self.vpn_status_label = QLabel("OpenVPN: 未连接")
        self.vpn_status_label.setStyleSheet("color: #999; padding: 5px; font-size: 12px;")
        status_layout.addWidget(self.vpn_status_label)
        
        # V2Ray 状态
        self.v2ray_status_label = QLabel("V2Ray: 未连接")
        self.v2ray_status_label.setStyleSheet("color: #999; padding: 5px; font-size: 12px;")
        status_layout.addWidget(self.v2ray_status_label)
        
        self.status_group.setLayout(status_layout)
        
        # ==================== VPN 配置区域 ====================
        self.vpn_group = QGroupBox("VPN 配置")
        self.vpn_group.setStyleSheet("""
            QGroupBox {
                font-size: 13px;
                font-weight: bold;
                border: 1px solid #ccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        vpn_layout = QVBoxLayout()
        
        # 拖拽区域
        self.vpn_drop_area = QLabel("📁 点击选择或拖拽 .ovpn 配置文件到此处")
        self.vpn_drop_area.setAlignment(Qt.AlignCenter)
        self.vpn_drop_area.setStyleSheet("""
            QLabel {
                border: 2px dashed #ccc;
                border-radius: 5px;
                padding: 20px;
                background-color: #f9f9f9;
                color: #666;
            }
            QLabel:hover {
                border-color: #2196F3;
                background-color: #f0f8ff;
            }
        """)
        self.vpn_drop_area.setMinimumHeight(80)
        self.vpn_drop_area.mousePressEvent = lambda e: self.select_vpn_config()
        vpn_layout.addWidget(self.vpn_drop_area)
        
        # VPN 按钮行
        vpn_button_layout = QHBoxLayout()
        
        self.start_vpn_button = QPushButton("🚀 启动 VPN")
        self.start_vpn_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 10px;
                font-size: 12px;
                border-radius: 4px;
                border: none;
                outline: none;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            QPushButton:focus {
                outline: none;
            }
        """)
        self.start_vpn_button.clicked.connect(self.start_vpn_only)
        
        self.stop_vpn_button = QPushButton("⏹ 停止 VPN")
        self.stop_vpn_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 10px;
                font-size: 12px;
                border-radius: 4px;
                border: none;
                outline: none;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            QPushButton:focus {
                outline: none;
            }
        """)
        self.stop_vpn_button.setEnabled(False)
        self.stop_vpn_button.clicked.connect(self.stop_vpn_only)
        
        vpn_button_layout.addWidget(self.start_vpn_button)
        vpn_button_layout.addWidget(self.stop_vpn_button)
        vpn_layout.addLayout(vpn_button_layout)
        
        self.vpn_group.setLayout(vpn_layout)
        
        # ==================== Shadowsocks 配置区域 ====================
        self.ss_group = QGroupBox("Shadowsocks 配置")
        self.ss_group.setStyleSheet("""
            QGroupBox {
                font-size: 13px;
                font-weight: bold;
                border: 1px solid #ccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        ss_layout = QVBoxLayout()
        
        # 拖拽区域
        self.v2ray_drop_area = QLabel("📁 点击选择或拖拽 config.json 到此处")
        self.v2ray_drop_area.setAlignment(Qt.AlignCenter)
        self.v2ray_drop_area.setStyleSheet("""
            QLabel {
                border: 2px dashed #ccc;
                border-radius: 5px;
                padding: 15px;
                background-color: #f9f9f9;
                color: #666;
            }
            QLabel:hover {
                border-color: #2196F3;
                background-color: #f0f8ff;
            }
        """)
        self.v2ray_drop_area.setMinimumHeight(60)
        self.v2ray_drop_area.mousePressEvent = lambda e: self.select_v2ray_config()
        ss_layout.addWidget(self.v2ray_drop_area)
        
        # 按钮网格 (2x2)
        ss_buttons_grid = QVBoxLayout()
        
        # 第一行
        ss_row1 = QHBoxLayout()
        
        self.import_ss_button = QPushButton("📋 从剪贴板导入")
        self.import_ss_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 8px;
                font-size: 11px;
                border-radius: 4px;
                border: none;
                outline: none;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:focus {
                outline: none;
            }
        """)
        self.import_ss_button.clicked.connect(self.import_ss_from_clipboard)
        
        self.edit_ss_button = QPushButton("✏️ 手动编辑")
        self.edit_ss_button.setStyleSheet("""
            QPushButton {
                padding: 8px;
                font-size: 11px;
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: white;
                outline: none;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
            }
            QPushButton:focus {
                outline: none;
                border: 1px solid #2196F3;
            }
        """)
        self.edit_ss_button.clicked.connect(self.edit_v2ray_config)
        
        ss_row1.addWidget(self.import_ss_button)
        ss_row1.addWidget(self.edit_ss_button)
        
        # 第二行
        ss_row2 = QHBoxLayout()
        
        self.start_v2ray_button = QPushButton("🚀 启动 V2Ray")
        self.start_v2ray_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px;
                font-size: 11px;
                border-radius: 4px;
                border: none;
                outline: none;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            QPushButton:focus {
                outline: none;
            }
        """)
        self.start_v2ray_button.clicked.connect(self.start_v2ray_only)
        
        self.stop_v2ray_button = QPushButton("⏹ 停止 V2Ray")
        self.stop_v2ray_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 8px;
                font-size: 11px;
                border-radius: 4px;
                border: none;
                outline: none;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            QPushButton:focus {
                outline: none;
            }
        """)
        self.stop_v2ray_button.setEnabled(False)
        self.stop_v2ray_button.clicked.connect(self.stop_v2ray_only)
        
        ss_row2.addWidget(self.start_v2ray_button)
        ss_row2.addWidget(self.stop_v2ray_button)
        
        ss_buttons_grid.addLayout(ss_row1)
        ss_buttons_grid.addLayout(ss_row2)
        ss_layout.addLayout(ss_buttons_grid)
        
        self.ss_group.setLayout(ss_layout)
        
        # ==================== TProxy 配置区域 ====================
        tproxy_conf = load_tproxy_config()
        
        self.tproxy_group = QGroupBox("透明代理 (TProxy)")
        self.tproxy_group.setStyleSheet("""
            QGroupBox {
                font-size: 13px;
                font-weight: bold;
                border: 1px solid #ccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        tproxy_layout = QFormLayout()
        
        # 启用复选框
        self.tproxy_checkbox = QCheckBox("启用透明代理(从配置自动获取参数)")
        self.tproxy_checkbox.setChecked(tproxy_conf["enabled"])
        tproxy_layout.addRow(self.tproxy_checkbox)
        
        # VPS IP (只读)
        self.vps_ip_input = QLineEdit(tproxy_conf["vps_ip"])
        self.vps_ip_input.setPlaceholderText("将从 V2Ray 配置自动提取")
        self.vps_ip_input.setReadOnly(True)
        self.vps_ip_input.setStyleSheet("QLineEdit { background-color: #f5f5f5; color: #666; }")
        tproxy_layout.addRow("VPS IP:", self.vps_ip_input)
        
        # TProxy 端口 (只读)
        self.tproxy_port_input = QSpinBox()
        self.tproxy_port_input.setRange(1, 65535)
        self.tproxy_port_input.setValue(tproxy_conf["port"])
        self.tproxy_port_input.setReadOnly(True)
        self.tproxy_port_input.setButtonSymbols(QSpinBox.NoButtons)
        self.tproxy_port_input.setStyleSheet("""
            QSpinBox {
                background-color: #f5f5f5;
                color: #666;
                border: 1px solid #ddd;
                border-radius: 3px;
                padding: 4px;
            }
        """)
        tproxy_layout.addRow("TProxy 端口:", self.tproxy_port_input)
        
        # fwmark
        self.mark_input = QSpinBox()
        self.mark_input.setRange(1, 255)
        self.mark_input.setValue(tproxy_conf["mark"])
        self.mark_input.setButtonSymbols(QSpinBox.NoButtons)
        self.mark_input.setStyleSheet("""
            QSpinBox {
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 4px;
            }
        """)
        tproxy_layout.addRow("fwmark:", self.mark_input)
        
        # 路由表
        self.table_input = QSpinBox()
        self.table_input.setRange(1, 252)
        self.table_input.setValue(tproxy_conf["table"])
        self.table_input.setButtonSymbols(QSpinBox.NoButtons)
        self.table_input.setStyleSheet("""
            QSpinBox {
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 4px;
            }
        """)
        tproxy_layout.addRow("路由表:", self.table_input)
        
        self.tproxy_group.setLayout(tproxy_layout)
        
        self._toggle_tproxy_inputs(self.tproxy_checkbox.isChecked())
        self.tproxy_checkbox.toggled.connect(self._toggle_tproxy_inputs)
        
        # ==================== 底部联合启动停止 ====================
        self.start_all_button = QPushButton("🚀 启动 VPN + V2Ray")
        self.start_all_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 15px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
                border: none;
                outline: none;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            QPushButton:focus {
                outline: none;
            }
        """)
        self.start_all_button.clicked.connect(self.start_combined)
        
        self.stop_all_button = QPushButton("⏹ 停止 VPN + V2Ray")
        self.stop_all_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 15px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
                border: none;
                outline: none;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            QPushButton:focus {
                outline: none;
            }
        """)
        self.stop_all_button.setEnabled(False)
        self.stop_all_button.clicked.connect(self.stop_combined)
        
        # ==================== 主布局 ====================
        layout = QVBoxLayout()
        layout.addWidget(self.status_group)
        layout.addWidget(self.vpn_group)
        layout.addWidget(self.ss_group)
        layout.addWidget(self.tproxy_group)
        layout.addSpacing(10)
        layout.addWidget(self.start_all_button)
        layout.addWidget(self.stop_all_button)
        layout.addStretch()
        
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        
        # ==================== 初始化状态 ====================
        # 核心 PID 跟踪
        self.vpn_pid = None
        self.v2ray_pid = None
        self.tproxy_active = False
        
        # 加载配置路径
        saved_paths = load_config_paths()
        self.vpn_config_path = saved_paths['vpn_config']
        self.v2ray_config_path = saved_paths['v2ray_config']
        
        # 配置文件初始化 (保持原有逻辑)
        self._init_config_files()
        
        # 更新显示
        self._update_config_display()
        
        # 自动提取 TProxy 配置
        self._auto_extract_tproxy_config()
    
    # ==================== 初始化方法 ====================
    def _init_config_files(self):
        """初始化配置文件 (保持原有逻辑)"""
        app_root = get_app_root()
        dev_vpn_path = os.path.join(app_root, "core", "openvpn", "client.ovpn")
        dev_v2ray_path = os.path.join(app_root, "core", "xray", "config.json")
        
        user_config_dir = os.path.dirname(self.v2ray_config_path)
        os.makedirs(user_config_dir, exist_ok=True)
        
        # V2Ray 配置处理
        if not os.path.exists(self.v2ray_config_path):
            if os.path.exists(dev_v2ray_path):
                import shutil
                try:
                    shutil.copy2(dev_v2ray_path, self.v2ray_config_path)
                except Exception as e:
                    print(f"复制失败: {e}")
                    self._create_default_v2ray_config()
            else:
                self._create_default_v2ray_config()
        else:
            if not self._validate_v2ray_config(self.v2ray_config_path):
                import shutil
                try:
                    backup_path = self.v2ray_config_path + ".backup"
                    shutil.copy2(self.v2ray_config_path, backup_path)
                except:
                    pass
                self._create_default_v2ray_config()
        
        # OpenVPN 配置处理
        if not os.path.exists(self.vpn_config_path) and os.path.exists(dev_vpn_path):
            import shutil
            try:
                shutil.copy2(dev_vpn_path, self.vpn_config_path)
            except:
                pass
    
    def _validate_v2ray_config(self, config_path):
        """验证 V2Ray 配置文件"""
        try:
            size = os.path.getsize(config_path)
            if size == 0:
                return False
            
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content.strip():
                    return False
                config = json.loads(content)
                if 'inbounds' not in config or 'outbounds' not in config:
                    return False
                return True
        except:
            return False
    
    def _create_default_v2ray_config(self):
        """创建默认 V2Ray 配置 (保持原有逻辑)"""
        default_config = {
            "log": {"loglevel": "warning"},
            "inbounds": [
                {"tag": "socks", "port": 1080, "protocol": "socks", "settings": {"auth": "noauth", "udp": True}},
                {"tag": "http", "port": 1081, "protocol": "http"},
                {"tag": "tproxy", "port": 12345, "protocol": "dokodemo-door", 
                 "settings": {"network": "tcp,udp", "followRedirect": True},
                 "streamSettings": {"sockopt": {"tproxy": "tproxy"}}}
            ],
            "outbounds": [
                {"tag": "proxy", "protocol": "shadowsocks", 
                 "settings": {"servers": [{"address": "your.server.com", "port": 8388, 
                                          "method": "chacha20-ietf-poly1305", "password": "your_password_here"}]}},
                {"tag": "direct", "protocol": "freedom", "settings": {}},
                {"tag": "block", "protocol": "blackhole", "settings": {"response": {"type": "http"}}}
            ],
            "routing": {
                "domainStrategy": "IPOnDemand",
                "rules": [
                    {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"},
                    {"type": "field", "domain": ["geosite:cn"], "outboundTag": "direct"},
                    {"type": "field", "ip": ["geoip:cn"], "outboundTag": "direct"}
                ]
            }
        }
        
        try:
            with open(self.v2ray_config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            print(f"✓ 默认 V2Ray 配置已创建")
        except Exception as e:
            print(f"创建默认 V2Ray 配置失败: {e}")
    
    def _update_config_display(self):
        """更新配置文件显示"""
        if os.path.exists(self.vpn_config_path):
            self.vpn_drop_area.setText(f"✓ {os.path.basename(self.vpn_config_path)}")
            self.vpn_drop_area.setStyleSheet("""
                QLabel {
                    border: 2px solid #4CAF50;
                    border-radius: 5px;
                    padding: 20px;
                    background-color: #f1f8f4;
                    color: #4CAF50;
                }
            """)
        
        if os.path.exists(self.v2ray_config_path):
            self.v2ray_drop_area.setText(f"✓ {os.path.basename(self.v2ray_config_path)}")
            self.v2ray_drop_area.setStyleSheet("""
                QLabel {
                    border: 2px solid #4CAF50;
                    border-radius: 5px;
                    padding: 15px;
                    background-color: #f1f8f4;
                    color: #4CAF50;
                }
            """)
    
    def _auto_extract_tproxy_config(self):
        """自动从 V2Ray 配置中提取 TProxy 参数"""
        if not os.path.exists(self.v2ray_config_path):
            return
        
        extracted = extract_tproxy_config_from_v2ray(self.v2ray_config_path)
        
        if extracted:
            self.tproxy_checkbox.setChecked(True)
            self.vps_ip_input.setText(extracted['vps_ip'])
            self.tproxy_port_input.setValue(extracted['tproxy_port'])
            
            save_tproxy_config(
                True,
                extracted['vps_ip'],
                extracted['tproxy_port'],
                self.mark_input.value(),
                self.table_input.value()
            )
    
    def _toggle_tproxy_inputs(self, enabled):
        """根据复选框状态启用/禁用 tproxy 输入控件"""
        self.mark_input.setEnabled(enabled)
        self.table_input.setEnabled(enabled)
    
    def _validate_ip(self, ip_str):
        """验证 IPv4 地址格式"""
        pattern = r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$'
        match = re.match(pattern, ip_str)
        if not match:
            return False
        for group in match.groups():
            if int(group) > 255:
                return False
        return True
    
    # ==================== 拖拽事件处理 ====================
    def dragEnterEvent(self, event: QDragEnterEvent):
        """拖拽进入事件"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        
    def dropEvent(self, event: QDropEvent):
        """拖拽放下事件"""
        urls = event.mimeData().urls()  # ← 修复：hasUrls() → urls()
        if urls:
            file_path = urls[0].toLocalFile()
            
            if file_path.endswith('.ovpn'):
                self.vpn_config_path = file_path
                self.vpn_drop_area.setText(f"✓ {os.path.basename(file_path)}")
                self.vpn_drop_area.setStyleSheet("""
                    QLabel {
                        border: 2px solid #4CAF50;
                        border-radius: 5px;
                        padding: 20px;
                        background-color: #f1f8f4;
                        color: #4CAF50;
                    }
                """)
                save_config_paths(self.vpn_config_path, self.v2ray_config_path)
                QMessageBox.information(self, "成功", f"已加载 OpenVPN 配置:\n{os.path.basename(file_path)}")
                
            elif file_path.endswith('.json'):
                self.v2ray_config_path = file_path
                self.v2ray_drop_area.setText(f"✓ {os.path.basename(file_path)}")
                self.v2ray_drop_area.setStyleSheet("""
                    QLabel {
                        border: 2px solid #4CAF50;
                        border-radius: 5px;
                        padding: 15px;
                        background-color: #f1f8f4;
                        color: #4CAF50;
                    }
                """)
                self._auto_extract_tproxy_config()
                save_config_paths(self.vpn_config_path, self.v2ray_config_path)
                QMessageBox.information(self, "成功", f"已加载 V2Ray 配置:\n{os.path.basename(file_path)}")
            else:
                QMessageBox.warning(self, "错误", "不支持的文件类型!\n请拖拽 .ovpn 或 .json 文件")
    
    # ==================== 配置文件选择 ====================
    def select_vpn_config(self):
        """选择 OpenVPN 配置文件"""
        start_dir = os.path.dirname(self.vpn_config_path) if os.path.exists(self.vpn_config_path) else os.path.expanduser("~")
        
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 OpenVPN 配置文件",
            start_dir,
            "OVPN 文件 (*.ovpn);;所有文件 (*)"
        )
        if path:
            self.vpn_config_path = path
            self.vpn_drop_area.setText(f"✓ {os.path.basename(path)}")
            self.vpn_drop_area.setStyleSheet("""
                QLabel {
                    border: 2px solid #4CAF50;
                    border-radius: 5px;
                    padding: 20px;
                    background-color: #f1f8f4;
                    color: #4CAF50;
                }
            """)
            save_config_paths(self.vpn_config_path, self.v2ray_config_path)
    
    def select_v2ray_config(self):
        """选择 V2Ray 配置文件"""
        start_dir = os.path.dirname(self.v2ray_config_path) if os.path.exists(self.v2ray_config_path) else os.path.expanduser("~")
        
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 V2Ray 配置文件",
            start_dir,
            "JSON 文件 (*.json);;所有文件 (*)"
        )
        if path:
            self.v2ray_config_path = path
            self.v2ray_drop_area.setText(f"✓ {os.path.basename(path)}")
            self.v2ray_drop_area.setStyleSheet("""
                QLabel {
                    border: 2px solid #4CAF50;
                    border-radius: 5px;
                    padding: 15px;
                    background-color: #f1f8f4;
                    color: #4CAF50;
                }
            """)
            self._auto_extract_tproxy_config()
            save_config_paths(self.vpn_config_path, self.v2ray_config_path)
    
    # ==================== 独立启动/停止方法 ====================
    def start_vpn_only(self):
        """独立启动 OpenVPN"""
        if not os.path.exists(self.vpn_config_path):
            QMessageBox.critical(self, "错误", "请先选择 OpenVPN 配置文件")
            return
        
        if self.vpn_pid:
            QMessageBox.warning(self, "警告", "OpenVPN 已在运行")
            return
        
        self.start_vpn_button.setEnabled(False)
        self.vpn_status_label.setText("OpenVPN: 正在启动...")
        self.vpn_status_label.setStyleSheet("color: #FF9800; padding: 5px; font-size: 12px;")
        
        self.vpn_thread = SingleVPNThread(self.vpn_config_path)
        self.vpn_thread.update_signal.connect(lambda msg: self.vpn_status_label.setText(f"OpenVPN: {msg}"))
        self.vpn_thread.error_signal.connect(self.handle_vpn_error)
        self.vpn_thread.success_signal.connect(self.handle_vpn_started)
        self.vpn_thread.start()
    
    def handle_vpn_started(self, pid):
        """OpenVPN 启动成功"""
        self.vpn_pid = pid
        self.vpn_status_label.setText(f"OpenVPN: ✓ 已连接 (PID: {pid})")
        self.vpn_status_label.setStyleSheet("color: #4CAF50; padding: 5px; font-size: 12px;")
        self.stop_vpn_button.setEnabled(True)
        self.start_vpn_button.setEnabled(True)
        self._update_combined_buttons()
    
    def handle_vpn_error(self, error):
        """OpenVPN 启动失败"""
        self.vpn_status_label.setText("OpenVPN: 未连接")
        self.vpn_status_label.setStyleSheet("color: #999; padding: 5px; font-size: 12px;")
        self.start_vpn_button.setEnabled(True)
        QMessageBox.critical(self, "错误", error)
    
    def stop_vpn_only(self):
        """独立停止 OpenVPN"""
        if not self.vpn_pid:
            return
        
        self.vpn_status_label.setText("OpenVPN: 正在停止...")
        self.vpn_status_label.setStyleSheet("color: #FF9800; padding: 5px; font-size: 12px;")
        
        try:
            cmd = [
                "pkexec",
                PolkitHelper.HELPER_SCRIPT,
                "stop",
                "--openvpn-pid", str(self.vpn_pid)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                self.vpn_pid = None
                self.vpn_status_label.setText("OpenVPN: 未连接")
                self.vpn_status_label.setStyleSheet("color: #999; padding: 5px; font-size: 12px;")
                self.stop_vpn_button.setEnabled(False)
                self._update_combined_buttons()
                QMessageBox.information(self, "成功", "OpenVPN 已停止")
            else:
                QMessageBox.critical(self, "错误", f"停止失败:\n{result.stderr}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"停止失败: {str(e)}")
    
    def start_v2ray_only(self):
        """独立启动 V2Ray (带 TProxy)"""
        if not os.path.exists(self.v2ray_config_path):
            QMessageBox.critical(self, "错误", "请先选择 V2Ray 配置文件")
            return
        
        if self.v2ray_pid:
            QMessageBox.warning(self, "警告", "V2Ray 已在运行")
            return
        
        # 验证 TProxy 配置
        tproxy_enabled = self.tproxy_checkbox.isChecked()
        if tproxy_enabled:
            vps_ip = self.vps_ip_input.text().strip()
            if not vps_ip or not self._validate_ip(vps_ip):
                QMessageBox.critical(self, "错误", "启用透明代理时必须配置有效的 VPS IP 地址")
                return
        
        self.start_v2ray_button.setEnabled(False)
        self.v2ray_status_label.setText("V2Ray: 正在启动...")
        self.v2ray_status_label.setStyleSheet("color: #FF9800; padding: 5px; font-size: 12px;")
        
        self.v2ray_thread = SingleV2RayThread(
            self.v2ray_config_path,
            tproxy_enabled=tproxy_enabled,
            tproxy_port=self.tproxy_port_input.value(),
            tproxy_vps_ip=self.vps_ip_input.text().strip(),
            tproxy_mark=self.mark_input.value(),
            tproxy_table=self.table_input.value()
        )
        self.v2ray_thread.update_signal.connect(lambda msg: self.v2ray_status_label.setText(f"V2Ray: {msg}"))
        self.v2ray_thread.error_signal.connect(self.handle_v2ray_error)
        self.v2ray_thread.success_signal.connect(self.handle_v2ray_started)
        self.v2ray_thread.start()
    
    def handle_v2ray_started(self, result):
        """V2Ray 启动成功"""
        self.v2ray_pid = result['pid']
        self.tproxy_active = result['tproxy_ok']
        
        if result['tproxy_ok']:
            self.v2ray_status_label.setText(f"V2Ray: ✓ 已连接 + TProxy (PID: {result['pid']})")
        else:
            self.v2ray_status_label.setText(f"V2Ray: ✓ 已连接 (PID: {result['pid']})")
        
        self.v2ray_status_label.setStyleSheet("color: #4CAF50; padding: 5px; font-size: 12px;")
        self.stop_v2ray_button.setEnabled(True)
        self.start_v2ray_button.setEnabled(True)
        self._update_combined_buttons()
    
    def handle_v2ray_error(self, error):
        """V2Ray 启动失败"""
        self.v2ray_status_label.setText("V2Ray: 未连接")
        self.v2ray_status_label.setStyleSheet("color: #999; padding: 5px; font-size: 12px;")
        self.start_v2ray_button.setEnabled(True)
        QMessageBox.critical(self, "错误", error)
    
    def stop_v2ray_only(self):
        """独立停止 V2Ray (包括 TProxy)"""
        if not self.v2ray_pid:
            return
        
        self.v2ray_status_label.setText("V2Ray: 正在停止...")
        self.v2ray_status_label.setStyleSheet("color: #FF9800; padding: 5px; font-size: 12px;")
        
        try:
            # 先清理 TProxy
            if self.tproxy_active:
                PolkitHelper.stop_tproxy(
                    self.tproxy_port_input.value(),
                    self.vps_ip_input.text().strip(),
                    self.mark_input.value(),
                    self.table_input.value()
                )
                self.tproxy_active = False
            
            # 停止 V2Ray
            cmd = [
                "pkexec",
                PolkitHelper.HELPER_SCRIPT,
                "stop",
                "--v2ray-pid", str(self.v2ray_pid)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                self.v2ray_pid = None
                self.v2ray_status_label.setText("V2Ray: 未连接")
                self.v2ray_status_label.setStyleSheet("color: #999; padding: 5px; font-size: 12px;")
                self.stop_v2ray_button.setEnabled(False)
                self._update_combined_buttons()
                QMessageBox.information(self, "成功", "V2Ray 已停止")
            else:
                QMessageBox.critical(self, "错误", f"停止失败:\n{result.stderr}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"停止失败: {str(e)}")
    
    # ==================== 智能联合启动/停止 ====================
    def start_combined(self):
        """智能联合启动 (只启动未运行的服务)"""
        # 检查配置文件
        if not os.path.exists(self.vpn_config_path):
            QMessageBox.critical(self, "错误", "请先选择 OpenVPN 配置文件")
            return
        
        if not os.path.exists(self.v2ray_config_path):
            QMessageBox.critical(self, "错误", "请先选择 V2Ray 配置文件")
            return
        
        # 验证 TProxy 配置
        tproxy_enabled = self.tproxy_checkbox.isChecked()
        if tproxy_enabled:
            vps_ip = self.vps_ip_input.text().strip()
            if not vps_ip or not self._validate_ip(vps_ip):
                QMessageBox.critical(self, "错误", "启用透明代理时必须配置有效的 VPS IP 地址")
                return
        
        # 保存配置
        save_tproxy_config(
            tproxy_enabled,
            self.vps_ip_input.text().strip(),
            self.tproxy_port_input.value(),
            self.mark_input.value(),
            self.table_input.value()
        )
        
        # 禁用按钮
        self.start_all_button.setEnabled(False)
        self.start_vpn_button.setEnabled(False)
        self.start_v2ray_button.setEnabled(False)
        
        # 启动线程
        self.combined_thread = CombinedStartThread(
            self.vpn_config_path,
            self.v2ray_config_path,
            self.vpn_pid,
            self.v2ray_pid,
            tproxy_enabled=tproxy_enabled,
            tproxy_port=self.tproxy_port_input.value(),
            tproxy_vps_ip=self.vps_ip_input.text().strip(),
            tproxy_mark=self.mark_input.value(),
            tproxy_table=self.table_input.value()
        )
        self.combined_thread.update_signal.connect(self._update_combined_status)
        self.combined_thread.error_signal.connect(self.handle_combined_error)
        self.combined_thread.success_signal.connect(self.handle_combined_started)
        self.combined_thread.start()
    
    def _update_combined_status(self, msg):
        """更新联合启动状态"""
        # 根据消息更新对应的状态标签
        if "OpenVPN" in msg:
            self.vpn_status_label.setText(msg)
            self.vpn_status_label.setStyleSheet("color: #FF9800; padding: 5px; font-size: 12px;")
        elif "V2Ray" in msg:
            self.v2ray_status_label.setText(msg)
            self.v2ray_status_label.setStyleSheet("color: #FF9800; padding: 5px; font-size: 12px;")
    
    def handle_combined_started(self, result):
        """联合启动成功"""
        self.vpn_pid = result['vpn_pid']
        self.v2ray_pid = result['v2ray_pid']
        self.tproxy_active = result['tproxy_ok']
        
        # 更新 VPN 状态
        if self.vpn_pid:
            self.vpn_status_label.setText(f"OpenVPN: ✓ 已连接 (PID: {self.vpn_pid})")
            self.vpn_status_label.setStyleSheet("color: #4CAF50; padding: 5px; font-size: 12px;")
            self.stop_vpn_button.setEnabled(True)
        
        # 更新 V2Ray 状态
        if self.v2ray_pid:
            if self.tproxy_active:
                self.v2ray_status_label.setText(f"V2Ray: ✓ 已连接 + TProxy (PID: {self.v2ray_pid})")
            else:
                self.v2ray_status_label.setText(f"V2Ray: ✓ 已连接 (PID: {self.v2ray_pid})")
            self.v2ray_status_label.setStyleSheet("color: #4CAF50; padding: 5px; font-size: 12px;")
            self.stop_v2ray_button.setEnabled(True)
        
        # 更新按钮
        self.start_all_button.setEnabled(True)
        self.start_vpn_button.setEnabled(True)
        self.start_v2ray_button.setEnabled(True)
        self._update_combined_buttons()
        
        QMessageBox.information(self, "成功", "VPN + V2Ray 已启动")
    
    def handle_combined_error(self, error):
        """联合启动失败"""
        self.start_all_button.setEnabled(True)
        self.start_vpn_button.setEnabled(True)
        self.start_v2ray_button.setEnabled(True)
        QMessageBox.critical(self, "错误", error)
    
    def stop_combined(self):
        """智能联合停止 (只停止已运行的服务)"""
        if not self.vpn_pid and not self.v2ray_pid:
            QMessageBox.warning(self, "警告", "没有运行中的服务")
            return
        
        try:
            # 先清理 TProxy
            if self.tproxy_active:
                PolkitHelper.stop_tproxy(
                    self.tproxy_port_input.value(),
                    self.vps_ip_input.text().strip(),
                    self.mark_input.value(),
                    self.table_input.value()
                )
                self.tproxy_active = False
            
            # 停止 V2Ray
            if self.v2ray_pid:
                self.v2ray_status_label.setText("V2Ray: 正在停止...")
                cmd = [
                    "pkexec",
                    PolkitHelper.HELPER_SCRIPT,
                    "stop",
                    "--v2ray-pid", str(self.v2ray_pid)
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    self.v2ray_pid = None
                    self.v2ray_status_label.setText("V2Ray: 未连接")
                    self.v2ray_status_label.setStyleSheet("color: #999; padding: 5px; font-size: 12px;")
                    self.stop_v2ray_button.setEnabled(False)
            
            # 停止 VPN
            if self.vpn_pid:
                self.vpn_status_label.setText("OpenVPN: 正在停止...")
                cmd = [
                    "pkexec",
                    PolkitHelper.HELPER_SCRIPT,
                    "stop",
                    "--openvpn-pid", str(self.vpn_pid)
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    self.vpn_pid = None
                    self.vpn_status_label.setText("OpenVPN: 未连接")
                    self.vpn_status_label.setStyleSheet("color: #999; padding: 5px; font-size: 12px;")
                    self.stop_vpn_button.setEnabled(False)
            
            self._update_combined_buttons()
            QMessageBox.information(self, "成功", "所有服务已停止")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"停止失败: {str(e)}")
    
    def _update_combined_buttons(self):
        """更新联合按钮状态"""
        # 如果两者都在运行,启用停止按钮
        if self.vpn_pid or self.v2ray_pid:
            self.stop_all_button.setEnabled(True)
        else:
            self.stop_all_button.setEnabled(False)
    
    # ==================== SS 配置相关 (保持不变) ====================
    def import_ss_from_clipboard(self):
        """从剪贴板导入 SS URL"""
        config_dir = os.path.dirname(self.v2ray_config_path)
        try:
            os.makedirs(config_dir, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法创建配置目录: {e}")
            return
        
        success = import_ss_url_from_clipboard(
            self, 
            self.v2ray_config_path, 
            replace_existing=True
        )
        
        if success:
            self.v2ray_drop_area.setText(f"✓ {os.path.basename(self.v2ray_config_path)} (已更新)")
            self._auto_extract_tproxy_config()
            save_config_paths(self.vpn_config_path, self.v2ray_config_path)
            QMessageBox.information(
                self,
                "成功",
                "配置已更新,透明代理参数已自动提取。\n如需应用,请重启 V2Ray。"
            )
    
    def edit_v2ray_config(self):
        """使用系统默认编辑器编辑 V2Ray 配置文件"""
        if not os.path.exists(self.v2ray_config_path):
            config_dir = os.path.dirname(self.v2ray_config_path)
            try:
                os.makedirs(config_dir, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法创建配置目录: {e}")
                return
            
            manager = V2RayConfigManager(self.v2ray_config_path)
            manager.save_config()
        
        try:
            subprocess.Popen(["xdg-open", self.v2ray_config_path])
            QMessageBox.information(
                self,
                "提示",
                "配置文件已在外部编辑器中打开。\n编辑完成后请重启 V2Ray 以应用更改。"
            )
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法打开编辑器: {e}")
    
    # ==================== 关闭窗口处理 ====================
    def closeEvent(self, event):
        """关闭窗口时清理资源"""
        if self.vpn_pid or self.v2ray_pid:
            reply = QMessageBox.question(
                self,
                "确认退出",
                "服务正在运行中,确定要退出吗?\n退出将自动停止所有服务。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.stop_combined()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
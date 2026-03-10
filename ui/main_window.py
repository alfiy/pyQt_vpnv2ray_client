"""
主窗口界面
集成 Polkit 权限提升功能 + TProxy 透明代理配置 + SS URL 导入
增强功能:自动从配置中提取 VPS IP 和 TProxy 端口,并自动启用透明代理
"""
import os
import sys
import time
import subprocess
from PyQt5.QtGui import QIcon
import re
import json
from PyQt5.QtWidgets import (
    QMainWindow, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QWidget,
    QProgressBar, QFileDialog, QMessageBox, QCheckBox, QLineEdit,
    QGroupBox, QFormLayout, QSpinBox
)
from PyQt5.QtCore import Qt
from core.worker import WorkerThread
from core.ss_config_manager import (
    import_ss_url_from_clipboard, 
    V2RayConfigManager,
    SSUrlParser
)
from core.polkit_helper import PolkitHelper

# 获取程序根目录(兼容开发和安装环境)
def get_app_root():
    """获取程序根目录"""
    # 如果是打包后的程序,使用可执行文件所在目录
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    # 开发环境:使用 main.py 所在目录的父目录(因为 main_window.py 在 ui/ 下)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# TProxy 配置持久化文件路径
TPROXY_CONF_PATH = os.path.expanduser("~/.config/ov2n/tproxy.conf")


def load_tproxy_config():
    """从配置文件加载 tproxy 参数"""
    defaults = {
        "enabled": False,
        "vps_ip": "",
        "port": 12345,
        "mark": 1,
        "table": 100,
    }
    conf_path = TPROXY_CONF_PATH
    if not os.path.exists(conf_path):
        return defaults

    try:
        data = {}
        with open(conf_path, "r") as f:
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
    conf_path = TPROXY_CONF_PATH
    try:
        os.makedirs(os.path.dirname(conf_path), exist_ok=True)
        with open(conf_path, "w") as f:
            f.write("# ov2n TProxy 配置\n")
            f.write(f"TPROXY_ENABLED={'true' if enabled else 'false'}\n")
            f.write(f"VPS_IP={vps_ip}\n")
            f.write(f"V2RAY_PORT={port}\n")
            f.write(f"MARK={mark}\n")
            f.write(f"TABLE={table}\n")
    except Exception as e:
        print(f"保存 tproxy 配置失败: {e}")


def extract_tproxy_config_from_v2ray(config_path):
    """
    从 V2Ray 配置文件中自动提取 TProxy 相关参数
    
    Returns:
        dict: {
            'vps_ip': str,      # 服务器 IP 地址
            'tproxy_port': int  # TProxy 入站端口
        }
        如果提取失败,返回 None
    """
    if not os.path.exists(config_path):
        return None
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        vps_ip = None
        tproxy_port = None
        
        # 1. 提取服务器 IP 地址
        # 从 outbounds 中查找服务器地址
        outbounds = config.get('outbounds', [])
        for outbound in outbounds:
            # 查找 Shadowsocks 或其他代理协议的服务器
            if outbound.get('protocol') in ['shadowsocks', 'vmess', 'vless', 'trojan', 'socks', 'http']:
                settings = outbound.get('settings', {})
                servers = settings.get('servers', [])
                if servers and len(servers) > 0:
                    server = servers[0]
                    address = server.get('address', '')
                    # 验证是否为有效 IP 地址(排除域名)
                    if address and re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', address):
                        vps_ip = address
                        break
        
        # 2. 提取 TProxy 入站端口
        # 从 inbounds 中查找 dokodemo-door 或 tproxy 类型的入站
        inbounds = config.get('inbounds', [])
        for inbound in inbounds:
            protocol = inbound.get('protocol', '')
            # 查找 dokodemo-door 协议(常用于透明代理)
            if protocol == 'dokodemo-door':
                port = inbound.get('port')
                settings = inbound.get('settings', {})
                # 确认配置了透明代理相关设置
                if settings.get('network') in ['tcp,udp', 'tcp', 'udp']:
                    tproxy_port = port
                    break
            # 也支持直接标记为 tproxy 的入站
            elif 'tproxy' in inbound.get('tag', '').lower():
                tproxy_port = inbound.get('port')
                break
        
        # 如果都提取成功,返回配置
        if vps_ip and tproxy_port:
            print(f"✓ 自动提取配置成功: VPS IP={vps_ip}, TProxy端口={tproxy_port}")
            return {
                'vps_ip': vps_ip,
                'tproxy_port': tproxy_port
            }
        else:
            print(f"⚠ 配置提取不完整: VPS IP={vps_ip}, TProxy端口={tproxy_port}")
            return None
            
    except json.JSONDecodeError as e:
        print(f"✗ JSON 解析失败: {e}")
        return None
    except Exception as e:
        print(f"✗ 提取配置失败: {e}")
        return None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ov2n Client")
        self.setGeometry(200, 200, 360, 650)

        # 设置窗口图标
        app_root = get_app_root()
        icon_path = os.path.join(app_root, "resources", "images", "ov2n256.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # 状态标签
        self.label = QLabel("状态: 就绪")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("font-size: 14px; padding: 10px;")

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("QProgressBar { height: 25px; }")

        # 配置文件路径显示
        self.vpn_path_label = QLabel("OpenVPN 配置: 未选择")
        self.vpn_path_label.setStyleSheet("color: #666; font-size: 12px;")
        
        self.v2ray_path_label = QLabel("V2Ray 配置: 未选择")
        self.v2ray_path_label.setStyleSheet("color: #666; font-size: 12px;")

        # 按钮
        self.select_vpn_button = QPushButton("📁 选择 OpenVPN 配置")
        self.select_vpn_button.setStyleSheet("padding: 10px; font-size: 13px;")
        
        self.select_v2ray_button = QPushButton("📁 选择 V2Ray 配置")
        self.select_v2ray_button.setStyleSheet("padding: 10px; font-size: 13px;")
        
        self.start_button = QPushButton("🚀 启动 VPN + V2Ray")
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 15px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        
        self.stop_button = QPushButton("⏹ 停止连接")
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 15px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.stop_button.setEnabled(False)

        # ==================== SS 配置导入区域 ====================
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

        # 当前服务器显示
        self.ss_server_label = QLabel("当前服务器: 未配置")
        self.ss_server_label.setStyleSheet("color: #666; padding: 5px;")
        ss_layout.addWidget(self.ss_server_label)

        # 按钮行
        ss_button_layout = QHBoxLayout()
        
        self.import_ss_button = QPushButton("📋 从剪贴板导入 SS 链接")
        self.import_ss_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 8px;
                font-size: 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        self.import_ss_button.setToolTip("从剪贴板导入 ss:// 链接并更新 V2Ray 配置")
        self.import_ss_button.clicked.connect(self.import_ss_from_clipboard)
        
        self.edit_ss_button = QPushButton("✏️ 手动编辑配置")
        self.edit_ss_button.setStyleSheet("padding: 8px; font-size: 12px;")
        self.edit_ss_button.setToolTip("手动编辑 V2Ray 配置文件")
        self.edit_ss_button.clicked.connect(self.edit_v2ray_config)
        
        ss_button_layout.addWidget(self.import_ss_button)
        ss_button_layout.addWidget(self.edit_ss_button)
        ss_layout.addLayout(ss_button_layout)

        # 重启 V2Ray 按钮
        self.restart_v2ray_button = QPushButton("🔄 重启 V2Ray 应用配置")
        self.restart_v2ray_button.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                padding: 8px;
                font-size: 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.restart_v2ray_button.setToolTip("重启 V2Ray 进程以应用新配置(保持 VPN 连接)")
        self.restart_v2ray_button.setEnabled(False)
        self.restart_v2ray_button.clicked.connect(self.restart_v2ray_only)
        ss_layout.addWidget(self.restart_v2ray_button)

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
        self.tproxy_checkbox.setToolTip("启用后,启动 VPN + V2Ray 时将自动配置 iptables tproxy 规则")
        tproxy_layout.addRow(self.tproxy_checkbox)

        # VPS IP (只读)
        self.vps_ip_input = QLineEdit(tproxy_conf["vps_ip"])
        self.vps_ip_input.setPlaceholderText("将从 V2Ray 配置自动提取")
        self.vps_ip_input.setReadOnly(True)  # 设置为只读
        self.vps_ip_input.setStyleSheet("QLineEdit { background-color: #f5f5f5; color: #666; }")
        self.vps_ip_input.setToolTip("VPS 服务器 IP (从配置自动提取,不可编辑)")
        tproxy_layout.addRow("VPS IP:", self.vps_ip_input)

        # TProxy 端口 (只读)
        self.tproxy_port_input = QSpinBox()
        self.tproxy_port_input.setRange(1, 65535)
        self.tproxy_port_input.setValue(tproxy_conf["port"])
        self.tproxy_port_input.setReadOnly(True)  # 设置为只读
        self.tproxy_port_input.setStyleSheet("QSpinBox { background-color: #f5f5f5; color: #666; }")
        self.tproxy_port_input.setToolTip("V2Ray/Xray 的 tproxy 入站监听端口 (从配置自动提取,不可编辑)")
        tproxy_layout.addRow("TProxy 端口:", self.tproxy_port_input)

        # fwmark
        self.mark_input = QSpinBox()
        self.mark_input.setRange(1, 255)
        self.mark_input.setValue(tproxy_conf["mark"])
        self.mark_input.setToolTip("iptables fwmark 标记值 (默认 1)")
        tproxy_layout.addRow("fwmark:", self.mark_input)

        # 路由表
        self.table_input = QSpinBox()
        self.table_input.setRange(1, 252)
        self.table_input.setValue(tproxy_conf["table"])
        self.table_input.setToolTip("策略路由表编号 (默认 100)")
        tproxy_layout.addRow("路由表:", self.table_input)

        self.tproxy_group.setLayout(tproxy_layout)

        # 根据复选框状态启用/禁用输入
        self._toggle_tproxy_inputs(self.tproxy_checkbox.isChecked())
        self.tproxy_checkbox.toggled.connect(self._toggle_tproxy_inputs)

        # ==================== 布局 ====================
        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.progress_bar)
        layout.addSpacing(10)
        layout.addWidget(self.vpn_path_label)
        layout.addWidget(self.select_vpn_button)
        layout.addSpacing(5)
        layout.addWidget(self.v2ray_path_label)
        layout.addWidget(self.select_v2ray_button)
        layout.addSpacing(10)
        layout.addWidget(self.ss_group)
        layout.addWidget(self.tproxy_group)
        layout.addSpacing(10)
        layout.addWidget(self.start_button)
        layout.addWidget(self.stop_button)
        layout.addStretch()

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # 使用用户主目录作为默认配置路径,避免权限问题
        user_home = os.path.expanduser("~")
        self.vpn_config_path = os.path.join(user_home, ".config", "ov2n", "client.ovpn")
        self.v2ray_config_path = os.path.join(user_home, ".config", "ov2n", "config.json")

        # 如果用户目录下没有,尝试使用程序目录(开发环境)
        app_root = get_app_root()
        dev_vpn_path = os.path.join(app_root, "core", "openvpn", "client.ovpn")
        dev_v2ray_path = os.path.join(app_root, "core", "xray", "config.json")

        # 检查并创建用户配置目录
        user_config_dir = os.path.dirname(self.v2ray_config_path)
        os.makedirs(user_config_dir, exist_ok=True)

        # 如果用户目录没有配置,但开发目录有,则复制一份
        if not os.path.exists(self.v2ray_config_path) and os.path.exists(dev_v2ray_path):
            import shutil
            try:
                shutil.copy2(dev_v2ray_path, self.v2ray_config_path)
                print(f"已复制默认配置: {dev_v2ray_path} -> {self.v2ray_config_path}")
            except Exception as e:
                print(f"复制默认配置失败: {e}")

        # 更新显示
        self._update_config_display()
        
        # 初始加载时尝试自动提取配置
        self._auto_extract_tproxy_config()

        # 绑定按钮事件
        self.start_button.clicked.connect(self.start_worker)
        self.stop_button.clicked.connect(self.stop_worker)
        self.select_vpn_button.clicked.connect(self.select_vpn_config)
        self.select_v2ray_button.clicked.connect(self.select_v2ray_config)

        self.worker = None

    def _update_config_display(self):
        """更新配置文件路径显示"""
        if os.path.exists(self.vpn_config_path):
            self.vpn_path_label.setText(f"OpenVPN 配置: {os.path.basename(self.vpn_config_path)}")
        else:
            self.vpn_path_label.setText("OpenVPN 配置: 未选择")

        if os.path.exists(self.v2ray_config_path):
            self.v2ray_path_label.setText(f"V2Ray 配置: {os.path.basename(self.v2ray_config_path)}")
            self.update_ss_server_display()
        else:
            self.v2ray_path_label.setText("V2Ray 配置: 未选择")

    def _auto_extract_tproxy_config(self):
        """
        自动从 V2Ray 配置中提取 TProxy 参数
        如果提取成功,自动启用透明代理并填充参数
        """
        if not os.path.exists(self.v2ray_config_path):
            return
        
        extracted = extract_tproxy_config_from_v2ray(self.v2ray_config_path)
        
        if extracted:
            # 自动启用透明代理
            self.tproxy_checkbox.setChecked(True)
            
            # 填充提取的参数
            self.vps_ip_input.setText(extracted['vps_ip'])
            self.tproxy_port_input.setValue(extracted['tproxy_port'])
            
            # 更新状态提示
            self.label.setText(f"✓ 已自动配置透明代理: {extracted['vps_ip']}:{extracted['tproxy_port']}")
            
            # 保存配置
            save_tproxy_config(
                True,
                extracted['vps_ip'],
                extracted['tproxy_port'],
                self.mark_input.value(),
                self.table_input.value()
            )
            
            print(f"✓ 透明代理已自动配置: VPS={extracted['vps_ip']}, 端口={extracted['tproxy_port']}")
        else:
            print("⚠ 无法从配置中提取完整的 TProxy 参数")

    # ------------------- SS 配置相关方法 -------------------
    
    def update_ss_server_display(self):
        """更新当前 SS 服务器显示"""
        try:
            if not os.path.exists(self.v2ray_config_path):
                self.ss_server_label.setText("当前服务器: 配置文件不存在")
                self.ss_server_label.setStyleSheet("color: #f44336; padding: 5px;")
                return
                
            manager = V2RayConfigManager(self.v2ray_config_path)
            servers = manager.get_current_servers()
            
            if servers:
                # 优先显示 proxy tag 的服务器
                proxy_server = None
                for tag, addr, port in servers:
                    if tag == "proxy":
                        proxy_server = (tag, addr, port)
                        break
                
                display_server = proxy_server or servers[0]
                tag, addr, port = display_server
                
                self.ss_server_label.setText(f"当前服务器: {addr}:{port} (tag: {tag})")
                self.ss_server_label.setStyleSheet("color: #4CAF50; padding: 5px;")
            else:
                self.ss_server_label.setText("当前服务器: 未配置 SS 服务器")
                self.ss_server_label.setStyleSheet("color: #666; padding: 5px;")
                
        except Exception as e:
            print(f"更新服务器显示失败: {e}")
            self.ss_server_label.setText("当前服务器: 读取失败")
            self.ss_server_label.setStyleSheet("color: #f44336; padding: 5px;")

    def import_ss_from_clipboard(self):
        """从剪贴板导入 SS URL"""
        # 确保配置目录存在
        config_dir = os.path.dirname(self.v2ray_config_path)
        try:
            os.makedirs(config_dir, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法创建配置目录: {e}")
            return
        
        # 使用 ss_config_manager 中的函数
        success = import_ss_url_from_clipboard(
            self, 
            self.v2ray_config_path, 
            replace_existing=True
        )
        
        if success:
            self.update_ss_server_display()
            self.v2ray_path_label.setText(f"V2Ray 配置: {os.path.basename(self.v2ray_config_path)} (已修改)")
            
            # 【新增】导入成功后自动提取 TProxy 配置
            self._auto_extract_tproxy_config()
            
            # 如果 V2Ray 正在运行,提示用户重启
            if self.worker and self.worker.isRunning():
                reply = QMessageBox.question(
                    self,
                    "重启 V2Ray",
                    "配置已更新,透明代理参数已自动提取。\n是否立即重启 V2Ray 以应用新配置?\n\n"
                    "VPN 连接将保持不断开。",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if reply == QMessageBox.Yes:
                    self.restart_v2ray_only()
            else:
                QMessageBox.information(
                    self,
                    "提示",
                    "配置已保存,透明代理参数已自动提取。\n下次启动 VPN 时将使用新配置。"
                )

    def edit_v2ray_config(self):
        """使用系统默认编辑器编辑 V2Ray 配置文件"""
        # 确保文件存在
        if not os.path.exists(self.v2ray_config_path):
            # 创建默认配置
            config_dir = os.path.dirname(self.v2ray_config_path)
            try:
                os.makedirs(config_dir, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法创建配置目录: {e}")
                return
            
            manager = V2RayConfigManager(self.v2ray_config_path)
            manager.save_config()
        
        # 使用 xdg-open 打开默认编辑器
        try:
            subprocess.Popen(["xdg-open", self.v2ray_config_path])
            
            # 提示用户编辑后重新加载
            QMessageBox.information(
                self,
                "提示",
                "配置文件已在外部编辑器中打开。\n\n"
                "编辑完成并保存后,请点击「选择 V2Ray 配置」按钮\n"
                "重新加载配置,以更新透明代理参数。"
            )
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法打开编辑器: {e}")

    def restart_v2ray_only(self):
        """仅重启 V2Ray 进程(保持 OpenVPN 连接)"""
        if not self.worker or not self.worker.isRunning():
            QMessageBox.warning(self, "警告", "VPN 连接未运行")
            return
        
        self.update_label("正在重启 V2Ray 以应用新配置...")
        self.restart_v2ray_button.setEnabled(False)
        
        # 获取当前 PID
        old_v2ray_pid = self.worker.pids.get('v2ray')
        
        if not old_v2ray_pid:
            QMessageBox.warning(self, "警告", "未找到 V2Ray 进程")
            self.restart_v2ray_button.setEnabled(True)
            return
        
        try:
            # 停止旧 V2Ray(只停止 V2Ray,保留 OpenVPN)            
            
            # 使用 pkexec 停止 V2Ray
            cmd = [
                "pkexec",
                PolkitHelper.HELPER_SCRIPT,
                "stop",
                "--v2ray-pid", str(old_v2ray_pid)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                # 停止失败,但可能进程已经不存在了
                print(f"停止 V2Ray 警告: {result.stderr}")
            
            # 等待进程完全停止
            time.sleep(2)
            
            # 启动新 V2Ray
            self.update_label("正在启动新的 V2Ray 进程...")
            
            # 查找 xray/v2ray 二进制
            binary = None
            for b in ['xray', 'v2ray']:
                result = subprocess.run(['which', b], capture_output=True, text=True)
                if result.returncode == 0:
                    binary = result.stdout.strip()
                    break
            
            if not binary:
                raise Exception("未找到 xray 或 v2ray 可执行文件")
            
            # 检测版本确定启动参数
            version_result = subprocess.run([binary, 'version'], capture_output=True, text=True)
            if 'V2Ray 4' in version_result.stdout or 'V2Ray 3' in version_result.stdout:
                cmd = [binary, '-config', self.v2ray_config_path]
            else:
                cmd = [binary, 'run', '-c', self.v2ray_config_path]
            
            # 启动进程
            log_file = open("/tmp/v2ray-restart.log", "w")
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=log_file,
                start_new_session=True  # 脱离当前会话
            )
            log_file.close()
            
            # 等待确认启动成功
            time.sleep(2)
            
            # 检查进程是否还在运行
            try:
                os.kill(process.pid, 0)  # 发送信号 0 检查进程是否存在
                # 更新 PID
                self.worker.pids['v2ray'] = process.pid
                self.update_label(f"✅ V2Ray 已重启 (新 PID: {process.pid})")
                self.update_ss_server_display()
                
                QMessageBox.information(
                    self,
                    "重启成功",
                    f"V2Ray 已成功重启!\n新进程 PID: {process.pid}"
                )
            except ProcessLookupError:
                # 进程已退出,检查日志
                try:
                    with open("/tmp/v2ray-restart.log", "r") as f:
                        log_content = f.read(500)
                except:
                    log_content = "无法读取日志"
                
                QMessageBox.critical(
                    self,
                    "重启失败",
                    f"V2Ray 启动失败,进程已退出。\n\n日志内容:\n{log_content}"
                )
                self.update_label("❌ V2Ray 重启失败")
                
        except Exception as e:
            QMessageBox.critical(self, "错误", f"重启 V2Ray 失败: {str(e)}")
            self.update_label(f"重启失败: {str(e)}")
        finally:
            self.restart_v2ray_button.setEnabled(True)

    # ------------------- TProxy 辅助 -------------------
    def _toggle_tproxy_inputs(self, enabled):
        """根据复选框状态启用/禁用 tproxy 输入控件"""
        # VPS IP 和 TProxy 端口始终只读,不受启用状态影响
        # 只有 mark 和 table 可编辑
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

    # ------------------- 文件选择 -------------------
    def select_vpn_config(self):
        """选择 OpenVPN 配置文件"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 OpenVPN 配置文件",
            os.path.expanduser("~"),
            "OVPN 文件 (*.ovpn);;所有文件 (*)"
        )
        if path:
            self.vpn_config_path = path
            self.vpn_path_label.setText(f"OpenVPN 配置: {os.path.basename(path)}")
            self.label.setText(f"已选择 OpenVPN 配置: {os.path.basename(path)}")

    def select_v2ray_config(self):
        """选择 V2Ray 配置文件"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 V2Ray 配置文件",
            os.path.expanduser("~"),
            "JSON 文件 (*.json);;所有文件 (*)"
        )
        if path:
            self.v2ray_config_path = path
            self.v2ray_path_label.setText(f"V2Ray 配置: {os.path.basename(path)}")
            self.label.setText(f"已选择 V2Ray 配置: {os.path.basename(path)}")
            self.update_ss_server_display()
            
            # 【新增】选择配置后自动提取 TProxy 参数
            self._auto_extract_tproxy_config()

    # ------------------- 启动/停止 Worker -------------------
    def start_worker(self):
        """启动 VPN 连接(使用 Polkit 权限提升)"""
        # 验证配置文件
        if not os.path.exists(self.vpn_config_path):
            QMessageBox.critical(
                self,
                "错误",
                f"OpenVPN 配置文件不存在:\n{self.vpn_config_path}\n\n请先选择有效的配置文件。"
            )
            return
            
        if not os.path.exists(self.v2ray_config_path):
            QMessageBox.critical(
                self,
                "错误",
                f"V2Ray 配置文件不存在:\n{self.v2ray_config_path}\n\n请先选择有效的配置文件。"
            )
            return

        # 验证 tproxy 配置
        tproxy_enabled = self.tproxy_checkbox.isChecked()
        tproxy_port = self.tproxy_port_input.value()
        tproxy_vps_ip = self.vps_ip_input.text().strip()
        tproxy_mark = self.mark_input.value()
        tproxy_table = self.table_input.value()

        if tproxy_enabled:
            if not tproxy_vps_ip:
                QMessageBox.critical(
                    self,
                    "错误",
                    "启用透明代理时必须配置 VPS IP 地址。\n\n"
                    "请确保 V2Ray 配置文件包含有效的服务器 IP 地址。"
                )
                return
            if not self._validate_ip(tproxy_vps_ip):
                QMessageBox.critical(
                    self,
                    "错误",
                    f"VPS IP 地址格式不正确: {tproxy_vps_ip}\n\n"
                    "请检查 V2Ray 配置文件中的服务器地址。"
                )
                return

        # 保存 tproxy 配置
        save_tproxy_config(tproxy_enabled, tproxy_vps_ip, tproxy_port, tproxy_mark, tproxy_table)

        # 防止重复启动
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "警告", "连接已在运行中,请勿重复启动。")
            return

        # 显示提示信息
        self.label.setText("正在启动... 请在弹出的窗口中输入密码")
        self.progress_bar.setValue(10)

        # 创建并启动 WorkerThread
        self.worker = WorkerThread(
            self.vpn_config_path,
            self.v2ray_config_path,
            tproxy_enabled=tproxy_enabled,
            tproxy_port=tproxy_port,
            tproxy_vps_ip=tproxy_vps_ip,
            tproxy_mark=tproxy_mark,
            tproxy_table=tproxy_table,
        )
        self.worker.update_signal.connect(self.update_label)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.error_signal.connect(self.handle_error)
        self.worker.finished.connect(self.worker_finished)
        
        self.worker.start()
        
        # 更新按钮状态
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.select_vpn_button.setEnabled(False)
        self.select_v2ray_button.setEnabled(False)
        self.tproxy_group.setEnabled(False)
        self.restart_v2ray_button.setEnabled(True)
        self.import_ss_button.setEnabled(False)
        self.edit_ss_button.setEnabled(False)

    def stop_worker(self):
        """停止 VPN 连接"""
        if self.worker and self.worker.isRunning():
            self.label.setText("正在停止连接...")
            self.worker.stop()
            self.worker.wait()
            self.label.setText("连接已停止")
            self.progress_bar.setValue(0)
        
        # 恢复按钮状态
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.select_vpn_button.setEnabled(True)
        self.select_v2ray_button.setEnabled(True)
        self.tproxy_group.setEnabled(True)
        self.restart_v2ray_button.setEnabled(False)
        self.import_ss_button.setEnabled(True)
        self.edit_ss_button.setEnabled(True)
        self.ss_server_label.setText("当前服务器: 未连接")
        self.ss_server_label.setStyleSheet("color: #666; padding: 5px;")

    def update_label(self, text):
        """更新状态标签"""
        self.label.setText(text)

    def update_progress(self, value):
        """更新进度条"""
        self.progress_bar.setValue(value)

    def handle_error(self, error_msg):
        """处理错误"""
        QMessageBox.critical(self, "错误", error_msg)
        self.stop_worker()

    def worker_finished(self):
        """Worker 线程完成"""
        # 恢复按钮状态
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.select_vpn_button.setEnabled(True)
        self.select_v2ray_button.setEnabled(True)
        self.tproxy_group.setEnabled(True)
        self.restart_v2ray_button.setEnabled(False)
        self.import_ss_button.setEnabled(True)
        self.edit_ss_button.setEnabled(True)

    # ------------------- 关闭窗口处理 -------------------
    def closeEvent(self, event):
        """
        关闭窗口时清理资源
        """
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self,
                "确认退出",
                "VPN 连接正在运行中,确定要退出吗?\n\n退出将自动断开连接并清理透明代理规则。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.label.setText("正在退出...")
                self.worker.stop()
                self.worker.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
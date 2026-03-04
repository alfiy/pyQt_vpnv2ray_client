"""
主窗口界面
集成 Polkit 权限提升功能 + TProxy 透明代理配置

增强: VPS IP 和 TProxy 端口自动从 V2Ray config.json 中获取,
      fwmark 和路由表在检测系统已有值的基础上自动分配
"""
import json
import os
import subprocess
from PyQt5.QtGui import QIcon
import re
from PyQt5.QtWidgets import (
    QMainWindow, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QWidget,
    QProgressBar, QFileDialog, QMessageBox, QCheckBox, QLineEdit,
    QGroupBox, QFormLayout, QSpinBox
)
from PyQt5.QtCore import Qt
from core.worker import WorkerThread
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OPENVPN_DIR = os.path.join(BASE_DIR, "core", "openvpn")
XRAY_DIR = os.path.join(BASE_DIR, "core", "xray")

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


# ==================== 自动检测辅助函数 ====================

def parse_v2ray_config(config_path):
    """
    解析 V2Ray config.json,提取 VPS IP 和 TProxy 端口

    Returns:
        dict: {"vps_ip": str or None, "tproxy_port": int or None}
    """
    result = {"vps_ip": None, "tproxy_port": None}

    if not config_path or not os.path.exists(config_path):
        return result

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            # 文件为空,静默跳过
            return result
        config = json.loads(content)
    except (json.JSONDecodeError, IOError, OSError) as e:
        print(f"解析 V2Ray 配置文件失败: {e}")
        return result

    # 1. 提取 VPS IP: 从第一个非 direct/freedom outbound 的 servers[0].address 或 vnext[0].address 获取
    outbounds = config.get("outbounds", [])
    for ob in outbounds:
        tag = ob.get("tag", "")
        protocol = ob.get("protocol", "")
        # 跳过 direct 和 freedom 类型的 outbound
        if tag == "direct" or protocol == "freedom":
            continue
        settings = ob.get("settings", {})
        # shadowsocks / trojan 等使用 servers
        servers = settings.get("servers", [])
        if servers and isinstance(servers, list):
            addr = servers[0].get("address", "")
            if addr:
                result["vps_ip"] = addr
                break
        # vmess / vless 等使用 vnext
        vnext = settings.get("vnext", [])
        if vnext and isinstance(vnext, list):
            addr = vnext[0].get("address", "")
            if addr:
                result["vps_ip"] = addr
                break

    # 2. 提取 TProxy 端口: 从 dokodemo-door inbound (tag 含 tproxy 或 sockopt.tproxy 存在) 获取
    inbounds = config.get("inbounds", [])
    for ib in inbounds:
        tag = ib.get("tag", "")
        protocol = ib.get("protocol", "")
        stream = ib.get("streamSettings", {})
        sockopt = stream.get("sockopt", {})
        tproxy_mode = sockopt.get("tproxy", "")

        # 匹配条件: dokodemo-door 协议 + (tag 含 tproxy 或 sockopt.tproxy 存在)
        if protocol == "dokodemo-door" and (
            "tproxy" in tag.lower() or tproxy_mode
        ):
            port = ib.get("port")
            if port and isinstance(port, int):
                result["tproxy_port"] = port
                break

    return result


def detect_system_fwmarks():
    """
    检测系统中已使用的 fwmark 值

    通过 `ip rule list` 和 `iptables -t mangle -L` 检测

    Returns:
        set: 已使用的 fwmark 值集合
    """
    used_marks = set()

    # 方法 1: 从 ip rule 中检测
    try:
        result = subprocess.run(
            ["ip", "rule", "list"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                # 格式: "32765: from all fwmark 0x1 lookup 100"
                match = re.search(r'fwmark\s+(0x[0-9a-fA-F]+|\d+)', line)
                if match:
                    val = match.group(1)
                    if val.startswith("0x"):
                        used_marks.add(int(val, 16))
                    else:
                        used_marks.add(int(val))
    except Exception as e:
        print(f"检测 ip rule fwmark 失败: {e}")

    # 方法 2: 从 iptables mangle 表中检测
    try:
        result = subprocess.run(
            ["iptables", "-t", "mangle", "-L", "-n", "--line-numbers"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                match = re.search(r'(?:MARK set|mark match)\s+(0x[0-9a-fA-F]+|\d+)', line)
                if match:
                    val = match.group(1)
                    if val.startswith("0x"):
                        used_marks.add(int(val, 16))
                    else:
                        used_marks.add(int(val))
    except Exception as e:
        print(f"检测 iptables fwmark 失败: {e}")

    return used_marks


def detect_system_route_tables():
    """
    检测系统中已使用的策略路由表编号

    通过 `ip rule list` 和 /etc/iproute2/rt_tables 检测

    Returns:
        set: 已使用的路由表编号集合
    """
    used_tables = set()

    # 从 ip rule 中检测
    try:
        result = subprocess.run(
            ["ip", "rule", "list"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                match = re.search(r'lookup\s+(\d+)', line)
                if match:
                    table_num = int(match.group(1))
                    # 排除系统默认表 (main=254, default=253, local=255)
                    if table_num < 253:
                        used_tables.add(table_num)
    except Exception as e:
        print(f"检测路由表失败: {e}")

    # 也检查 /etc/iproute2/rt_tables 中的自定义表
    try:
        rt_tables_path = "/etc/iproute2/rt_tables"
        if os.path.exists(rt_tables_path):
            with open(rt_tables_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            table_num = int(parts[0])
                            if 1 <= table_num < 253:
                                used_tables.add(table_num)
                        except ValueError:
                            pass
    except Exception as e:
        print(f"读取 rt_tables 失败: {e}")

    return used_tables


def find_available_mark(start=1, max_val=255):
    """
    找到一个未被系统使用的 fwmark 值

    Args:
        start: 起始值 (默认 1)
        max_val: 最大值 (默认 255)

    Returns:
        int: 可用的 fwmark 值
    """
    used = detect_system_fwmarks()
    candidate = start
    while candidate <= max_val:
        if candidate not in used:
            return candidate
        candidate += 1
    return start


def find_available_table(start=100, max_val=252):
    """
    找到一个未被系统使用的路由表编号

    Args:
        start: 起始值 (默认 100)
        max_val: 最大值 (默认 252)

    Returns:
        int: 可用的路由表编号
    """
    used = detect_system_route_tables()
    candidate = start
    while candidate <= max_val:
        if candidate not in used:
            return candidate
        candidate += 1
    return start


def copy_config_file(src, dst):
    """
    复制配置文件到用户目录
    
    Args:
        src: 源文件路径
        dst: 目标文件路径
        
    Returns:
        tuple: (success: bool, error_msg: str or None)
    """
    try:
        # 验证源文件存在且可读
        if not os.path.exists(src):
            return False, f"源文件不存在: {src}"
        
        if not os.path.isfile(src):
            return False, f"源路径不是文件: {src}"
        
        # 读取源文件内容
        with open(src, 'rb') as f:
            content = f.read()
        
        if len(content) == 0:
            return False, f"源文件为空: {src}"
        
        # 确保目标目录存在
        dst_dir = os.path.dirname(dst)
        os.makedirs(dst_dir, exist_ok=True)
        
        # 直接复制文件
        shutil.copyfile(src, dst)
        
        # 验证复制是否成功
        if not os.path.exists(dst):
            return False, f"文件复制后验证失败: {dst}"
        
        # 验证文件大小
        dst_size = os.path.getsize(dst)
        if dst_size != len(content):
            return False, f"文件大小不匹配: 原始 {len(content)} 字节, 目标 {dst_size} 字节"
        
        return True, None
        
    except PermissionError as e:
        return False, f"权限不足: {str(e)}"
    except Exception as e:
        return False, f"复制失败: {str(e)}"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ov2N Client")
        self.setGeometry(200, 200, 360, 650)

        # 设置窗口图标
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "resources",
            "images",
            "ov2n256.png"
        )
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
        
        self.start_button = QPushButton("🚀 启动 Ov2N")
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
        self.tproxy_checkbox = QCheckBox("启用透明代理")
        self.tproxy_checkbox.setChecked(tproxy_conf["enabled"])
        self.tproxy_checkbox.setToolTip("启用后,启动 Ov2N 时将自动配置 iptables tproxy 规则")
        tproxy_layout.addRow(self.tproxy_checkbox)

        # VPS IP (带自动检测提示)
        vps_ip_layout = QHBoxLayout()
        self.vps_ip_input = QLineEdit(tproxy_conf["vps_ip"])
        self.vps_ip_input.setPlaceholderText("自动从 V2Ray 配置获取")
        self.vps_ip_input.setToolTip(
            "VPS 服务器 IP,此 IP 的流量将被排除,防止代理循环\n"
            "选择 V2Ray 配置文件后将自动填充"
        )
        self.vps_ip_auto_label = QLabel("")
        self.vps_ip_auto_label.setStyleSheet("color: #4CAF50; font-size: 11px;")
        vps_ip_layout.addWidget(self.vps_ip_input)
        vps_ip_layout.addWidget(self.vps_ip_auto_label)
        tproxy_layout.addRow("VPS IP:", vps_ip_layout)

        # TProxy 端口 (带自动检测提示)
        tproxy_port_layout = QHBoxLayout()
        self.tproxy_port_input = QSpinBox()
        self.tproxy_port_input.setRange(1, 65535)
        self.tproxy_port_input.setValue(tproxy_conf["port"])
        self.tproxy_port_input.setToolTip(
            "V2Ray/Xray 的 tproxy 入站监听端口\n"
            "选择 V2Ray 配置文件后将自动填充"
        )
        self.tproxy_port_auto_label = QLabel("")
        self.tproxy_port_auto_label.setStyleSheet("color: #4CAF50; font-size: 11px;")
        tproxy_port_layout.addWidget(self.tproxy_port_input)
        tproxy_port_layout.addWidget(self.tproxy_port_auto_label)
        tproxy_layout.addRow("TProxy 端口:", tproxy_port_layout)

        # fwmark (带自动检测提示)
        mark_layout = QHBoxLayout()
        self.mark_input = QSpinBox()
        self.mark_input.setRange(1, 255)
        self.mark_input.setValue(tproxy_conf["mark"])
        self.mark_input.setToolTip(
            "iptables fwmark 标记值\n"
            "点击「自动检测」按钮可自动分配不冲突的值"
        )
        self.mark_auto_label = QLabel("")
        self.mark_auto_label.setStyleSheet("color: #2196F3; font-size: 11px;")
        mark_layout.addWidget(self.mark_input)
        mark_layout.addWidget(self.mark_auto_label)
        tproxy_layout.addRow("fwmark:", mark_layout)

        # 路由表 (带自动检测提示)
        table_layout = QHBoxLayout()
        self.table_input = QSpinBox()
        self.table_input.setRange(1, 252)
        self.table_input.setValue(tproxy_conf["table"])
        self.table_input.setToolTip(
            "策略路由表编号\n"
            "点击「自动检测」按钮可自动分配不冲突的值"
        )
        self.table_auto_label = QLabel("")
        self.table_auto_label.setStyleSheet("color: #2196F3; font-size: 11px;")
        table_layout.addWidget(self.table_input)
        table_layout.addWidget(self.table_auto_label)
        tproxy_layout.addRow("路由表:", table_layout)

        # 自动检测按钮
        self.auto_detect_button = QPushButton("🔍 自动检测 fwmark 和路由表")
        self.auto_detect_button.setStyleSheet(
            "padding: 5px; font-size: 12px; color: #2196F3;"
        )
        self.auto_detect_button.setToolTip(
            "检测系统中已使用的 fwmark 和路由表值,\n"
            "自动分配不冲突的值"
        )
        self.auto_detect_button.clicked.connect(self._auto_detect_mark_and_table)
        tproxy_layout.addRow(self.auto_detect_button)

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
        layout.addWidget(self.tproxy_group)
        layout.addSpacing(10)
        layout.addWidget(self.start_button)
        layout.addWidget(self.stop_button)
        layout.addStretch()

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # 默认配置文件路径 - 使用用户目录,避免需要 root 权限
        config_dir = os.path.expanduser("~/.config/ov2n")
        os.makedirs(config_dir, exist_ok=True)
        
        self.vpn_config_path = os.path.join(config_dir, "client.ovpn")
        self.v2ray_config_path = os.path.join(config_dir, "config.json")

        # 检查默认配置文件是否存在且不为空
        self._check_default_configs()

        # 绑定按钮事件
        self.start_button.clicked.connect(self.start_worker)
        self.stop_button.clicked.connect(self.stop_worker)
        self.select_vpn_button.clicked.connect(self.select_vpn_config)
        self.select_v2ray_button.clicked.connect(self.select_v2ray_config)

        self.worker = None

    def _check_default_configs(self):
        """检查默认配置文件是否存在且有效"""
        # 检查 OpenVPN 配置
        if os.path.exists(self.vpn_config_path):
            try:
                size = os.path.getsize(self.vpn_config_path)
                if size > 0:
                    self.vpn_path_label.setText(
                        f"OpenVPN 配置: {os.path.basename(self.vpn_config_path)} ({size} 字节)"
                    )
                    self.vpn_path_label.setStyleSheet("color: #4CAF50; font-size: 12px;")
                else:
                    self.vpn_path_label.setText("OpenVPN 配置: 文件为空,请导入")
                    self.vpn_path_label.setStyleSheet("color: #ff9800; font-size: 12px;")
            except:
                self.vpn_path_label.setText("OpenVPN 配置: 读取失败")
                self.vpn_path_label.setStyleSheet("color: #f44336; font-size: 12px;")
        else:
            self.vpn_path_label.setText("OpenVPN 配置: 未导入")
            self.vpn_path_label.setStyleSheet("color: #666; font-size: 12px;")

        # 检查 V2Ray 配置
        if os.path.exists(self.v2ray_config_path):
            try:
                size = os.path.getsize(self.v2ray_config_path)
                if size > 0:
                    self.v2ray_path_label.setText(
                        f"V2Ray 配置: {os.path.basename(self.v2ray_config_path)} ({size} 字节)"
                    )
                    self.v2ray_path_label.setStyleSheet("color: #4CAF50; font-size: 12px;")
                    # 自动填充 tproxy 配置
                    self._auto_fill_from_v2ray_config(self.v2ray_config_path)
                else:
                    self.v2ray_path_label.setText("V2Ray 配置: 文件为空,请导入")
                    self.v2ray_path_label.setStyleSheet("color: #ff9800; font-size: 12px;")
            except:
                self.v2ray_path_label.setText("V2Ray 配置: 读取失败")
                self.v2ray_path_label.setStyleSheet("color: #f44336; font-size: 12px;")
        else:
            self.v2ray_path_label.setText("V2Ray 配置: 未导入")
            self.v2ray_path_label.setStyleSheet("color: #666; font-size: 12px;")

    # ------------------- 自动检测辅助 -------------------
    def _auto_fill_from_v2ray_config(self, config_path):
        """
        从 V2Ray config.json 自动填充 VPS IP 和 TProxy 端口
        """
        parsed = parse_v2ray_config(config_path)

        if parsed["vps_ip"]:
            self.vps_ip_input.setText(parsed["vps_ip"])
            self.vps_ip_auto_label.setText("✓ 自动获取")
        else:
            self.vps_ip_auto_label.setText("")

        if parsed["tproxy_port"]:
            self.tproxy_port_input.setValue(parsed["tproxy_port"])
            self.tproxy_port_auto_label.setText("✓ 自动获取")
        else:
            self.tproxy_port_auto_label.setText("")

    def _auto_detect_mark_and_table(self):
        """自动检测并分配不冲突的 fwmark 和路由表值"""
        # 检测 fwmark
        used_marks = detect_system_fwmarks()
        available_mark = find_available_mark(start=1)
        self.mark_input.setValue(available_mark)

        if used_marks:
            marks_str = ", ".join(str(m) for m in sorted(used_marks))
            self.mark_auto_label.setText(f"✓ 已用: {marks_str} → 分配: {available_mark}")
        else:
            self.mark_auto_label.setText(f"✓ 系统无占用 → 使用: {available_mark}")

        # 检测路由表
        used_tables = detect_system_route_tables()
        available_table = find_available_table(start=100)
        self.table_input.setValue(available_table)

        if used_tables:
            tables_str = ", ".join(str(t) for t in sorted(used_tables))
            self.table_auto_label.setText(f"✓ 已用: {tables_str} → 分配: {available_table}")
        else:
            self.table_auto_label.setText(f"✓ 系统无占用 → 使用: {available_table}")

        self.label.setText(
            f"自动检测完成: fwmark={available_mark}, 路由表={available_table}"
        )

    # ------------------- TProxy 辅助 -------------------
    def _toggle_tproxy_inputs(self, enabled):
        """根据复选框状态启用/禁用 tproxy 输入控件"""
        self.vps_ip_input.setEnabled(enabled)
        self.tproxy_port_input.setEnabled(enabled)
        self.mark_input.setEnabled(enabled)
        self.table_input.setEnabled(enabled)
        self.auto_detect_button.setEnabled(enabled)

        # 启用时自动检测 fwmark 和路由表
        if enabled:
            self._auto_detect_mark_and_table()

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

        if not path:
            return

        self.label.setText("正在导入 OpenVPN 配置...")
        self.progress_bar.setValue(20)

        # 直接复制文件到用户目录
        success, error_msg = copy_config_file(path, self.vpn_config_path)

        if success:
            try:
                size = os.path.getsize(self.vpn_config_path)
                self.vpn_path_label.setText(
                    f"OpenVPN 配置: {os.path.basename(self.vpn_config_path)} ({size} 字节)"
                )
                self.vpn_path_label.setStyleSheet("color: #4CAF50; font-size: 12px;")
                self.label.setText("✓ OpenVPN 配置已成功导入")
                self.progress_bar.setValue(100)
            except Exception as e:
                self.label.setText(f"导入后验证失败: {e}")
                self.progress_bar.setValue(0)
        else:
            QMessageBox.critical(
                self,
                "导入失败",
                f"无法导入 OpenVPN 配置文件:\n\n{error_msg}\n\n"
                "请确保:\n"
                "1. 源文件存在且可读\n"
                "2. 源文件不为空"
            )
            self.label.setText("✗ OpenVPN 配置导入失败")
            self.progress_bar.setValue(0)

    def select_v2ray_config(self):
        """选择 V2Ray 配置文件"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 V2Ray 配置文件",
            os.path.expanduser("~"),
            "JSON 文件 (*.json);;所有文件 (*)"
        )

        if not path:
            return

        self.label.setText("正在导入 V2Ray 配置...")
        self.progress_bar.setValue(20)

        # 直接复制文件到用户目录
        success, error_msg = copy_config_file(path, self.v2ray_config_path)

        if success:
            try:
                size = os.path.getsize(self.v2ray_config_path)
                self.v2ray_path_label.setText(
                    f"V2Ray 配置: {os.path.basename(self.v2ray_config_path)} ({size} 字节)"
                )
                self.v2ray_path_label.setStyleSheet("color: #4CAF50; font-size: 12px;")
                self.label.setText("✓ V2Ray 配置已成功导入")
                self.progress_bar.setValue(100)
                
                # 自动填充 tproxy 配置
                self._auto_fill_from_v2ray_config(self.v2ray_config_path)
            except Exception as e:
                self.label.setText(f"导入后验证失败: {e}")
                self.progress_bar.setValue(0)
        else:
            QMessageBox.critical(
                self,
                "导入失败",
                f"无法导入 V2Ray 配置文件:\n\n{error_msg}\n\n"
                "请确保:\n"
                "1. 源文件存在且可读\n"
                "2. 配置文件格式正确 (有效的 JSON)"
            )
            self.label.setText("✗ V2Ray 配置导入失败")
            self.progress_bar.setValue(0)

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

        # 检查文件是否为空
        try:
            vpn_size = os.path.getsize(self.vpn_config_path)
            if vpn_size == 0:
                QMessageBox.critical(
                    self,
                    "错误",
                    "OpenVPN 配置文件为空,请重新导入配置文件。"
                )
                return
        except:
            QMessageBox.critical(
                self,
                "错误",
                "无法读取 OpenVPN 配置文件,请检查文件权限。"
            )
            return
            
        if not os.path.exists(self.v2ray_config_path):
            QMessageBox.critical(
                self,
                "错误",
                f"V2Ray 配置文件不存在:\n{self.v2ray_config_path}\n\n请先选择有效的配置文件。"
            )
            return

        # 检查文件是否为空
        try:
            v2ray_size = os.path.getsize(self.v2ray_config_path)
            if v2ray_size == 0:
                QMessageBox.critical(
                    self,
                    "错误",
                    "V2Ray 配置文件为空,请重新导入配置文件。"
                )
                return
        except:
            QMessageBox.critical(
                self,
                "错误",
                "无法读取 V2Ray 配置文件,请检查文件权限。"
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
                    "启用透明代理时必须填写 VPS IP 地址。\n\n"
                    "提示: 选择 V2Ray 配置文件后会自动填充。"
                )
                return
            if not self._validate_ip(tproxy_vps_ip):
                QMessageBox.critical(
                    self,
                    "错误",
                    f"VPS IP 地址格式不正确: {tproxy_vps_ip}\n\n请输入有效的 IPv4 地址,例如: 1.2.3.4"
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
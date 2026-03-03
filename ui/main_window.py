"""
主窗口界面
集成 Polkit 权限提升功能 + TProxy 透明代理配置
"""
import os
from PyQt5.QtGui import QIcon
import re
from PyQt5.QtWidgets import (
    QMainWindow, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QWidget,
    QProgressBar, QFileDialog, QMessageBox, QCheckBox, QLineEdit,
    QGroupBox, QFormLayout, QSpinBox
)
from PyQt5.QtCore import Qt
from core.worker import WorkerThread

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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ov2n Client")
        self.setGeometry(200, 200, 720, 600)

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
        self.tproxy_checkbox.setToolTip("启用后,启动 VPN + V2Ray 时将自动配置 iptables tproxy 规则")
        tproxy_layout.addRow(self.tproxy_checkbox)

        # VPS IP
        self.vps_ip_input = QLineEdit(tproxy_conf["vps_ip"])
        self.vps_ip_input.setPlaceholderText("例如: 1.2.3.4")
        self.vps_ip_input.setToolTip("VPS 服务器 IP,此 IP 的流量将被排除,防止代理循环")
        tproxy_layout.addRow("VPS IP:", self.vps_ip_input)

        # TProxy 端口
        self.tproxy_port_input = QSpinBox()
        self.tproxy_port_input.setRange(1, 65535)
        self.tproxy_port_input.setValue(tproxy_conf["port"])
        self.tproxy_port_input.setToolTip("V2Ray/Xray 的 tproxy 入站监听端口 (需与 V2Ray 配置一致)")
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
        layout.addWidget(self.tproxy_group)
        layout.addSpacing(10)
        layout.addWidget(self.start_button)
        layout.addWidget(self.stop_button)
        layout.addStretch()

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # 默认配置文件路径
        self.vpn_config_path = os.path.join(os.getcwd(), "core/openvpn/client.ovpn")
        self.v2ray_config_path = os.path.join(os.getcwd(), "core/xray/config.json")

        # 检查默认配置文件是否存在
        if os.path.exists(self.vpn_config_path):
            self.vpn_path_label.setText(f"OpenVPN 配置: {os.path.basename(self.vpn_config_path)}")
        if os.path.exists(self.v2ray_config_path):
            self.v2ray_path_label.setText(f"V2Ray 配置: {os.path.basename(self.v2ray_config_path)}")

        # 绑定按钮事件
        self.start_button.clicked.connect(self.start_worker)
        self.stop_button.clicked.connect(self.stop_worker)
        self.select_vpn_button.clicked.connect(self.select_vpn_config)
        self.select_v2ray_button.clicked.connect(self.select_v2ray_config)

        self.worker = None

    # ------------------- TProxy 辅助 -------------------
    def _toggle_tproxy_inputs(self, enabled):
        """根据复选框状态启用/禁用 tproxy 输入控件"""
        self.vps_ip_input.setEnabled(enabled)
        self.tproxy_port_input.setEnabled(enabled)
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
            os.path.join(os.getcwd(), "core/openvpn"),
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
            os.path.join(os.getcwd(), "core/xray"),
            "JSON 文件 (*.json);;所有文件 (*)"
        )
        if path:
            self.v2ray_config_path = path
            self.v2ray_path_label.setText(f"V2Ray 配置: {os.path.basename(path)}")
            self.label.setText(f"已选择 V2Ray 配置: {os.path.basename(path)}")

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
                    "启用透明代理时必须填写 VPS IP 地址。"
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
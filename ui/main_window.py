# ui/main_window.py
import os
from PyQt5.QtWidgets import (
    QMainWindow, QLabel, QPushButton, QVBoxLayout, QWidget,
    QProgressBar, QFileDialog
)
from core.worker import WorkerThread

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenVPN + V2Ray Client MVP")
        self.setGeometry(200, 200, 600, 400)

        # 日志显示
        self.label = QLabel("Status: Ready")
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)

        # 按钮
        self.start_button = QPushButton("Start VPN + V2Ray")
        self.select_vpn_button = QPushButton("Select OpenVPN Config")
        self.select_v2ray_button = QPushButton("Select V2Ray Config")

        # 布局
        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.select_vpn_button)
        layout.addWidget(self.select_v2ray_button)
        layout.addWidget(self.start_button)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # 默认配置文件路径（绝对路径）
        self.vpn_config_path = os.path.join(os.getcwd(), "core/openvpn/client.ovpn")
        self.v2ray_config_path = os.path.join(os.getcwd(), "core/xray/config.json")

        # 绑定按钮事件
        self.start_button.clicked.connect(self.start_worker)
        self.select_vpn_button.clicked.connect(self.select_vpn_config)
        self.select_v2ray_button.clicked.connect(self.select_v2ray_config)

        self.worker = None

    def select_vpn_config(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select OpenVPN Config",
            os.path.join(os.getcwd(), "core/openvpn"),
            "OVPN Files (*.ovpn)"
        )
        if path:
            self.vpn_config_path = path
            self.label.setText(f"Selected OpenVPN: {os.path.basename(path)}")

    def select_v2ray_config(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select V2Ray Config",
            os.path.join(os.getcwd(), "core/xray"),
            "JSON Files (*.json)"
        )
        if path:
            self.v2ray_config_path = path
            self.label.setText(f"Selected V2Ray: {os.path.basename(path)}")

    def start_worker(self):
        if not os.path.exists(self.vpn_config_path):
            self.label.setText("Error: OpenVPN config not found")
            return
        if not os.path.exists(self.v2ray_config_path):
            self.label.setText("Error: V2Ray config not found")
            return

        # 禁止重复启动
        if self.worker and self.worker.isRunning():
            self.label.setText("Worker already running...")
            return

        # 创建 WorkerThread
        self.worker = WorkerThread(self.vpn_config_path, self.v2ray_config_path)
        self.worker.update_signal.connect(self.update_label)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.start()
        self.label.setText("Worker started...")

    def update_label(self, text):
        self.label.setText(text)

    def update_progress(self, value):
        self.progress_bar.setValue(value)

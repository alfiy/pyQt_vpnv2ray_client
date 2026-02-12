"""
主窗口界面
集成 Polkit 权限提升功能
"""
import os
from PyQt5.QtWidgets import (
    QMainWindow, QLabel, QPushButton, QVBoxLayout, QWidget,
    QProgressBar, QFileDialog, QMessageBox
)
from PyQt5.QtCore import Qt
from core.worker import WorkerThread

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenVPN + V2Ray Client (Polkit)")
        self.setGeometry(200, 200, 700, 450)

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

        # 布局
        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.progress_bar)
        layout.addSpacing(20)
        layout.addWidget(self.vpn_path_label)
        layout.addWidget(self.select_vpn_button)
        layout.addSpacing(10)
        layout.addWidget(self.v2ray_path_label)
        layout.addWidget(self.select_v2ray_button)
        layout.addSpacing(20)
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

        # 防止重复启动
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "警告", "连接已在运行中,请勿重复启动。")
            return

        # 显示提示信息
        self.label.setText("正在启动... 请在弹出的窗口中输入密码")
        self.progress_bar.setValue(10)

        # 创建并启动 WorkerThread
        self.worker = WorkerThread(self.vpn_config_path, self.v2ray_config_path)
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

    # ------------------- 关闭窗口处理 -------------------
    def closeEvent(self, event):
        """
        关闭窗口时清理资源
        """
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self,
                "确认退出",
                "VPN 连接正在运行中,确定要退出吗?\n\n退出将自动断开连接。",
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
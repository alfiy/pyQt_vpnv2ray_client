"""
后台工作线程
负责启动和管理 VPN 连接
"""
import time
from PyQt5.QtCore import QThread, pyqtSignal
from core.polkit_helper import PolkitHelper

class WorkerThread(QThread):
    """后台工作线程"""
    
    # 信号定义
    update_signal = pyqtSignal(str)      # 状态更新信号
    progress_signal = pyqtSignal(int)    # 进度更新信号
    error_signal = pyqtSignal(str)       # 错误信号
    
    def __init__(self, vpn_config_path, v2ray_config_path):
        super().__init__()
        self.vpn_config_path = vpn_config_path
        self.v2ray_config_path = v2ray_config_path
        self.pids = {}
        self.should_stop = False
    
    def run(self):
        """线程主函数"""
        try:
            # 步骤 1: 检查环境
            self.update_signal.emit("正在检查系统环境...")
            self.progress_signal.emit(20)
            
            if not PolkitHelper.check_polkit_available():
                self.error_signal.emit("系统未安装 polkit,无法继续")
                return
            
            if not PolkitHelper.check_helper_installed():
                self.error_signal.emit(
                    "Helper 脚本未正确安装\n\n"
                    "请运行以下命令安装:\n"
                    "sudo cp polkit/vpn-helper.py /usr/local/bin/\n"
                    "sudo chmod +x /usr/local/bin/vpn-helper.py"
                )
                return
            
            time.sleep(0.5)
            
            # 步骤 2: 启动 VPN
            self.update_signal.emit("正在启动 VPN... (请输入密码)")
            self.progress_signal.emit(40)
            
            success, message, self.pids = PolkitHelper.start_vpn(
                self.vpn_config_path,
                self.v2ray_config_path
            )
            
            if not success:
                self.error_signal.emit(message)
                return
            
            # 步骤 3: 连接成功
            self.progress_signal.emit(80)
            self.update_signal.emit("VPN 连接成功!")
            time.sleep(0.5)
            
            self.progress_signal.emit(100)
            self.update_signal.emit(
                f"✅ 连接已建立\n"
                f"OpenVPN PID: {self.pids.get('openvpn', 'N/A')}\n"
                f"V2Ray PID: {self.pids.get('v2ray', 'N/A')}"
            )
            
            # 保持连接状态
            while not self.should_stop:
                time.sleep(1)
            
        except Exception as e:
            self.error_signal.emit(f"发生异常: {str(e)}")
    
    def stop(self):
        """停止线程"""
        self.should_stop = True
        
        # 停止 VPN 进程
        if self.pids:
            self.update_signal.emit("正在停止 VPN...")
            success, message = PolkitHelper.stop_vpn(self.pids)
            
            if success:
                self.update_signal.emit(message)
            else:
                self.error_signal.emit(message)
            
            self.pids = {}
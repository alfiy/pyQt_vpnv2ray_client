"""
后台工作线程
负责启动和管理 VPN 连接,以及配置透明代理
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
    
    def __init__(self, vpn_config_path, v2ray_config_path,
                 tproxy_enabled=False, tproxy_port=12345,
                 tproxy_vps_ip="", tproxy_mark=1, tproxy_table=100):
        super().__init__()
        self.vpn_config_path = vpn_config_path
        self.v2ray_config_path = v2ray_config_path
        self.pids = {}
        self.should_stop = False
        
        # TProxy 配置
        self.tproxy_enabled = tproxy_enabled
        self.tproxy_port = tproxy_port
        self.tproxy_vps_ip = tproxy_vps_ip
        self.tproxy_mark = tproxy_mark
        self.tproxy_table = tproxy_table
        self.tproxy_active = False  # 标记 tproxy 是否已成功启用
    
    def run(self):
        """线程主函数"""
        try:
            # 步骤 1: 检查环境
            self.update_signal.emit("正在检查系统环境...")
            self.progress_signal.emit(10)
            
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
            
            # 步骤 2: 启动 VPN + V2Ray
            self.update_signal.emit("正在启动 VPN + V2Ray... (请输入密码)")
            self.progress_signal.emit(30)
            
            success, message, self.pids = PolkitHelper.start_vpn(
                self.vpn_config_path,
                self.v2ray_config_path
            )
            
            if not success:
                self.error_signal.emit(message)
                return
            
            self.progress_signal.emit(60)
            self.update_signal.emit("VPN + V2Ray 启动成功!")
            time.sleep(0.5)
            
            # 步骤 3: 如果启用了 tproxy,配置透明代理
            if self.tproxy_enabled:
                self.update_signal.emit("正在配置透明代理 (TProxy)...")
                self.progress_signal.emit(75)
                
                tproxy_success, tproxy_msg = PolkitHelper.start_tproxy(
                    self.tproxy_port,
                    self.tproxy_vps_ip,
                    self.tproxy_mark,
                    self.tproxy_table
                )
                
                if tproxy_success:
                    self.tproxy_active = True
                    self.progress_signal.emit(100)
                    self.update_signal.emit(
                        f"✅ 连接已建立 (含透明代理)\n"
                        f"OpenVPN PID: {self.pids.get('openvpn', 'N/A')}\n"
                        f"V2Ray PID: {self.pids.get('v2ray', 'N/A')}\n"
                        f"TProxy: 端口 {self.tproxy_port} → VPS {self.tproxy_vps_ip}"
                    )
                else:
                    # tproxy 配置失败,但 VPN 和 V2Ray 已启动
                    # 不中断连接,只是提示用户
                    self.progress_signal.emit(90)
                    self.update_signal.emit(
                        f"⚠️ VPN + V2Ray 已启动,但透明代理配置失败\n"
                        f"OpenVPN PID: {self.pids.get('openvpn', 'N/A')}\n"
                        f"V2Ray PID: {self.pids.get('v2ray', 'N/A')}\n"
                        f"TProxy 错误: {tproxy_msg}"
                    )
            else:
                # 不启用 tproxy
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
        
        # 步骤 1: 先清理 tproxy 规则 (必须在停止 V2Ray 之前)
        if self.tproxy_active:
            self.update_signal.emit("正在清理透明代理规则...")
            tproxy_success, tproxy_msg = PolkitHelper.stop_tproxy(
                self.tproxy_port,
                self.tproxy_vps_ip,
                self.tproxy_mark,
                self.tproxy_table
            )
            if tproxy_success:
                self.update_signal.emit("透明代理规则已清理")
            else:
                print(f"清理 tproxy 失败: {tproxy_msg}")
            self.tproxy_active = False
        
        # 步骤 2: 停止 VPN 进程
        if self.pids:
            self.update_signal.emit("正在停止 VPN...")
            success, message = PolkitHelper.stop_vpn(self.pids)
            
            if success:
                self.update_signal.emit(message)
            else:
                self.error_signal.emit(message)
            
            self.pids = {}
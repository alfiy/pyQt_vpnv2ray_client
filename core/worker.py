import subprocess
from PyQt5.QtCore import QThread, pyqtSignal

class WorkerThread(QThread):
    update_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)

    def __init__(self, config_vpn, config_v2ray):
        super().__init__()
        self.vpn_config = config_vpn
        self.v2ray_config = config_v2ray

    def run(self):
        self.update_signal.emit("Starting OpenVPN...")
        self.progress_signal.emit(20)
        subprocess.Popen(["openvpn", "--config", self.vpn_config])

        self.update_signal.emit("Starting V2Ray...")
        self.progress_signal.emit(50)
        subprocess.Popen(["/usr/local/bin/v2ray", "-config", self.v2ray_config])

        self.update_signal.emit("Client started successfully!")
        self.progress_signal.emit(100)

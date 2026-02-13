#!/usr/bin/env python3
"""
OpenVPN + V2Ray Client with Polkit
主程序入口
"""
import sys
from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("VPN Client")
    app.setOrganizationName("Example")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
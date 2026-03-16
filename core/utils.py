"""
通用工具函数模块
提供跨模块共享的辅助函数
"""
import os
import re
import sys


def get_app_root() -> str:
    """获取应用根目录路径，兼容打包和开发环境。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def validate_ip(ip: str) -> bool:
    """验证 IPv4 地址格式是否合法。"""
    m = re.match(r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$', ip)
    return bool(m) and all(int(g) <= 255 for g in m.groups())
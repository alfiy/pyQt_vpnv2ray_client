"""
Linux 图标处理实现。
封装现有的 X11/Xlib 图标兼容逻辑。
"""
from PyQt5.QtGui import QIcon

from core.platform.base import IconHandler


class LinuxIconHandler(IconHandler):
    """Linux 图标处理器，委托给现有的 icon_helper 模块。"""

    def load_window_icon(self, app_root: str) -> QIcon:
        """加载窗口图标（使用现有的多路径探测逻辑）。"""
        from core.icon_helper import load_window_icon
        return load_window_icon(app_root)

    def apply_window_icon(self, window) -> None:
        """应用窗口图标（包括 X11 _NET_WM_ICON 写入）。"""
        from core.icon_helper import apply_window_icon
        apply_window_icon(window)

    def cleanup_icons(self) -> None:
        """清理历史遗留的错误用户图标。"""
        from core.icon_helper import _cleanup_bad_user_icons
        _cleanup_bad_user_icons()
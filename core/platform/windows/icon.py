"""
Windows 图标处理实现（骨架）。

Windows 下 Qt 原生支持窗口图标，无需 X11 hack。
只需从 resources/images/ 加载图标文件即可。

TODO: 后续逐步填充具体实现。
"""
import os

from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QPainterPath
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from core.platform.base import IconHandler


class WindowsIconHandler(IconHandler):
    """
    Windows 图标处理器。

    Windows 下 Qt 的 setWindowIcon() 即可正确显示标题栏和任务栏图标，
    无需 X11 的 _NET_WM_ICON 等额外处理。
    """

    def load_window_icon(self, app_root: str) -> QIcon:
        """
        加载窗口图标。

        搜索顺序：
        1. resources/images/ov2n.ico (Windows 原生 ICO 格式)
        2. resources/images/ov2n256.png
        3. resources/images/ 下其他尺寸 PNG
        4. 程序化生成盾牌图标（兜底）

        TODO: 完善 ICO 文件支持。
        """
        candidates = [
            os.path.join(app_root, "resources", "images", "ov2n.ico"),
            os.path.join(app_root, "resources", "images", "ov2n256.png"),
            os.path.join(app_root, "resources", "images", "ov2n128.png"),
            os.path.join(app_root, "resources", "images", "ov2n64.png"),
            os.path.join(app_root, "resources", "images", "ov2n48.png"),
            os.path.join(app_root, "resources", "images", "ov2n22.png"),
        ]

        icon = QIcon()
        for path in candidates:
            if os.path.exists(path):
                icon.addFile(path)

        if icon.isNull():
            # 兜底：程序化生成盾牌图标
            icon = self._generate_fallback_icon()

        # 设置 QApplication 级别图标
        app = QApplication.instance()
        if app is not None:
            app.setApplicationName("ov2n")
            app.setWindowIcon(icon)

        return icon

    def apply_window_icon(self, window) -> None:
        """
        应用窗口图标。
        Windows 下 Qt 原生支持，直接设置即可。
        """
        icon = window.windowIcon()
        if not icon.isNull():
            window.setWindowIcon(icon)
            app = QApplication.instance()
            if app is not None:
                app.setWindowIcon(icon)

    def cleanup_icons(self) -> None:
        """Windows 不需要清理图标。"""
        pass

    @staticmethod
    def _generate_fallback_icon() -> QIcon:
        """生成兜底的盾牌图标。"""
        icon = QIcon()
        for size in (16, 22, 24, 32, 48, 64, 128, 256):
            pm = QPixmap(size, size)
            pm.fill(Qt.transparent)
            painter = QPainter(pm)
            painter.setRenderHint(QPainter.Antialiasing)
            s = size
            shield = QPainterPath()
            shield.moveTo(s * 0.5, s * 0.05)
            shield.lineTo(s * 0.95, s * 0.25)
            shield.lineTo(s * 0.95, s * 0.55)
            shield.quadTo(s * 0.95, s * 0.85, s * 0.5, s * 0.95)
            shield.quadTo(s * 0.05, s * 0.85, s * 0.05, s * 0.55)
            shield.lineTo(s * 0.05, s * 0.25)
            shield.closeSubpath()
            painter.fillPath(shield, QColor("#1565C0"))
            font = QFont("Sans Serif", int(size * 0.32), QFont.Bold)
            painter.setFont(font)
            painter.setPen(QColor("white"))
            painter.drawText(pm.rect(), Qt.AlignCenter, "V")
            painter.end()
            icon.addPixmap(pm)
        return icon
"""
icon_helper.py
跨 Linux 发行版图标兼容层

解决两个问题:
1. Kylin / 部分国产 Linux: emoji 字符在按钮上显示为方块
   → 改用 Qt 内置 QStyle 标准图标 + Unicode 纯文本符号兜底
2. Ubuntu 等: 窗口标题栏图标不显示
   → 多路径探测 + SVG/PNG 自动选择 + 程序化生成兜底图标
"""
import os
import sys
from typing import Optional
from PyQt5.QtWidgets import QStyle, QApplication
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QPainterPath
from PyQt5.QtCore import Qt, QSize


# ──────────────────────────────────────────────
# 1. 检测系统 emoji 支持
# ──────────────────────────────────────────────
def _detect_emoji_support() -> bool:
    """
    检测当前系统字体是否能渲染 emoji。
    原理: 尝试将 emoji 字符渲染到 QPixmap，若所有像素均为背景色则说明不支持。
    """
    try:
        pm = QPixmap(20, 20)
        pm.fill(Qt.white)
        painter = QPainter(pm)
        font = QFont()
        font.setPointSize(12)
        painter.setFont(font)
        painter.drawText(0, 16, "🚀")
        painter.end()

        img = pm.toImage()
        # 检查是否有非白色像素（说明 emoji 被渲染了）
        for x in range(20):
            for y in range(20):
                color = QColor(img.pixel(x, y))
                if color.red() < 250 or color.green() < 250 or color.blue() < 250:
                    return True
        return False
    except Exception:
        return False


# 全局 emoji 支持标志（懒初始化）
_EMOJI_SUPPORTED: Optional[bool] = None


def emoji_supported() -> bool:
    global _EMOJI_SUPPORTED
    if _EMOJI_SUPPORTED is None:
        _EMOJI_SUPPORTED = _detect_emoji_support()
    return _EMOJI_SUPPORTED


# ──────────────────────────────────────────────
# 2. 按钮文字：emoji / 纯文字自动切换
# ──────────────────────────────────────────────
# 格式: (emoji版本, 纯文字版本)
_BUTTON_LABELS = {
    "start":        ("🚀 {text}",   "▶ {text}"),
    "stop":         ("⏹ {text}",   "■ {text}"),
    "import_clip":  ("📋 {text}",  "⊕ {text}"),
    "edit":         ("✏️ {text}",   "✎ {text}"),
    "folder":       ("📁 {text}",  "▤ {text}"),
}


def btn_text(key: str, text: str) -> str:
    """
    根据系统 emoji 支持情况返回按钮文字。
    key: _BUTTON_LABELS 中的键
    text: 按钮主文字
    """
    template_emoji, template_plain = _BUTTON_LABELS.get(key, ("{text}", "{text}"))
    if emoji_supported():
        return template_emoji.format(text=text)
    else:
        return template_plain.format(text=text)


def drop_area_prefix() -> str:
    """拖拽区域的文件夹图标前缀"""
    return "📁 " if emoji_supported() else "▤ "


def check_mark() -> str:
    """配置加载成功的勾选符号"""
    return "✓ "


# ──────────────────────────────────────────────
# 3. 窗口图标：多路径探测 + 程序化生成兜底
# ──────────────────────────────────────────────
def _make_fallback_icon(size: int = 64) -> QIcon:
    """
    程序化生成一个简洁的 VPN 盾牌图标作为兜底。
    纯 Qt 绘制，无需任何外部文件。
    """
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)

    # 盾牌背景
    shield = QPainterPath()
    s = size
    shield.moveTo(s * 0.5, s * 0.05)
    shield.lineTo(s * 0.95, s * 0.25)
    shield.lineTo(s * 0.95, s * 0.55)
    shield.quadTo(s * 0.95, s * 0.85, s * 0.5, s * 0.95)
    shield.quadTo(s * 0.05, s * 0.85, s * 0.05, s * 0.55)
    shield.lineTo(s * 0.05, s * 0.25)
    shield.closeSubpath()

    painter.fillPath(shield, QColor("#1565C0"))  # 深蓝盾牌

    # 内部高光
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(255, 255, 255, 40))
    inner = QPainterPath()
    inner.moveTo(s * 0.5, s * 0.12)
    inner.lineTo(s * 0.88, s * 0.30)
    inner.lineTo(s * 0.88, s * 0.54)
    inner.quadTo(s * 0.88, s * 0.75, s * 0.5, s * 0.85)
    inner.quadTo(s * 0.12, s * 0.75, s * 0.12, s * 0.54)
    inner.lineTo(s * 0.12, s * 0.30)
    inner.closeSubpath()
    painter.fillPath(inner, QColor(255, 255, 255, 30))

    # 字母 "V"
    font = QFont("Sans Serif", int(size * 0.32), QFont.Bold)
    painter.setFont(font)
    painter.setPen(QColor("white"))
    painter.drawText(pm.rect(), Qt.AlignCenter, "V")

    painter.end()
    return QIcon(pm)


def load_window_icon(app_root: str) -> QIcon:
    """
    按优先级探测窗口图标:
    1. resources/images/ov2n256.png
    2. resources/images/ov2n.png
    3. resources/images/ov2n.svg
    4. /usr/share/pixmaps/ov2n.png (deb 安装后)
    5. 程序化生成的兜底盾牌图标
    """
    candidates = [
        os.path.join(app_root, "resources", "images", "ov2n256.png"),
        os.path.join(app_root, "resources", "images", "ov2n.png"),
        os.path.join(app_root, "resources", "images", "ov2n.svg"),
        "/usr/share/pixmaps/ov2n.png",
        "/usr/share/pixmaps/ov2n256.png",
        os.path.join(app_root, "ov2n.png"),
    ]

    for path in candidates:
        if os.path.exists(path):
            icon = QIcon(path)
            if not icon.isNull():
                return icon

    # 兜底: 程序化生成
    print("⚠ 未找到窗口图标文件，使用程序化生成的图标")
    return _make_fallback_icon(64)


# ──────────────────────────────────────────────
# 4. Qt 标准图标（可选，用于工具栏/菜单）
# ──────────────────────────────────────────────
def get_std_icon(style_enum) -> QIcon:
    """获取 Qt 内置标准图标"""
    app = QApplication.instance()
    if app:
        return app.style().standardIcon(style_enum)
    return QIcon()
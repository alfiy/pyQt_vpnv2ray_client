"""
icon_helper.py
跨 Linux 发行版图标兼容层

解决两个问题:
1. Kylin / 部分国产 Linux: emoji 字符在按钮上显示为方块
   → 改用 Qt 内置 QStyle 标准图标 + Unicode 纯文本符号兜底
2. Ubuntu 等: 窗口标题栏图标不显示
   → 多路径探测 + SVG/PNG 自动选择 + 程序化生成兜底图标

检测原理（v2，修复 Kylin 误判）:
  旧方法的缺陷：不支持 emoji 的字体会渲染"替代方块"(tofu box)，
  方块本身有像素，导致旧的"有非白色像素=支持"逻辑误判为支持。

  新方法：同时渲染 emoji 字符 和 一个确定不存在的私有区字符(U+F0001)，
  比较两张图的像素哈希。若完全相同 → 两者都是 tofu box → 不支持 emoji。
  若不同 → emoji 被正确渲染 → 支持。
"""
import os
from typing import Optional
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QPainterPath
from PyQt5.QtCore import Qt
from Xlib import display as xdisplay, Xatom

# ──────────────────────────────────────────────
# 1. 检测系统 emoji 支持
# ──────────────────────────────────────────────
def _render_char_to_bytes(char: str, size: int = 24) -> bytes:
    """将单个字符渲染到 QPixmap 并返回原始像素字节，用于比较。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.white)
    painter = QPainter(pm)
    font = QFont()
    font.setPointSize(int(size * 0.6))
    painter.setFont(font)
    painter.drawText(pm.rect(), Qt.AlignCenter, char)
    painter.end()
    img = pm.toImage()
    # 提取所有像素的 RGB 值拼成字节串
    result = bytearray()
    for y in range(size):
        for x in range(size):
            c = QColor(img.pixel(x, y))
            result += bytes([c.red(), c.green(), c.blue()])
    return bytes(result)


def _detect_emoji_support() -> bool:
    """
    检测当前系统字体是否真正支持 emoji 渲染（非 tofu box）。

    算法：
      1. 渲染一个 emoji（🚀）
      2. 渲染一个确定不存在于任何字体的私有区字符（U+F0001），
         它一定会显示为 tofu box
      3. 若两者像素完全相同 → emoji 也是 tofu box → 不支持
      4. 若不同 → emoji 被正确渲染 → 支持
    """
    try:
        emoji_bytes  = _render_char_to_bytes("🚀")          # 待检测 emoji
        tofu_bytes   = _render_char_to_bytes("\U000F0001")   # 确定是 tofu 的私有字符

        # 额外验证: emoji 渲染结果不应是纯白（说明确实有内容被渲染）
        all_white = all(b == 255 for b in emoji_bytes)
        if all_white:
            return False  # 什么都没渲染出来，肯定不支持

        # 核心对比: emoji 像素 == tofu 像素 → 都是方块 → 不支持
        return emoji_bytes != tofu_bytes

    except Exception:
        return False  # 出错时保守地返回不支持


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
# 3. 窗口图标
# ──────────────────────────────────────────────
def _draw_shield_pixmap(size: int) -> QPixmap:
    """绘制盾牌图标 Pixmap（仅用于完全没有图标文件时的最终兜底）。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    s = size
    shield = QPainterPath()
    shield.moveTo(s * 0.5,  s * 0.05)
    shield.lineTo(s * 0.95, s * 0.25)
    shield.lineTo(s * 0.95, s * 0.55)
    shield.quadTo(s * 0.95, s * 0.85, s * 0.5,  s * 0.95)
    shield.quadTo(s * 0.05, s * 0.85, s * 0.05, s * 0.55)
    shield.lineTo(s * 0.05, s * 0.25)
    shield.closeSubpath()
    painter.fillPath(shield, QColor("#1565C0"))
    painter.setPen(Qt.NoPen)
    inner = QPainterPath()
    inner.moveTo(s * 0.5,  s * 0.12)
    inner.lineTo(s * 0.88, s * 0.30)
    inner.lineTo(s * 0.88, s * 0.54)
    inner.quadTo(s * 0.88, s * 0.75, s * 0.5,  s * 0.85)
    inner.quadTo(s * 0.12, s * 0.75, s * 0.12, s * 0.54)
    inner.lineTo(s * 0.12, s * 0.30)
    inner.closeSubpath()
    painter.fillPath(inner, QColor(255, 255, 255, 30))
    font = QFont("Sans Serif", int(size * 0.32), QFont.Bold)
    painter.setFont(font)
    painter.setPen(QColor("white"))
    painter.drawText(pm.rect(), Qt.AlignCenter, "V")
    painter.end()
    return pm


def _cleanup_bad_user_icons() -> None:
    """
    清理之前版本错误写入到用户目录的盾牌图标。
    判断依据：若用户目录的 ov2n.png 和系统目录的 ov2n.png 不一致（文件大小不同），
    则删除用户目录的版本，让系统优先使用 /usr/share/icons/ 下的正确图标。
    """
    xdg_data_home = os.environ.get(
        "XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    system_icon = "/usr/share/icons/hicolor/256x256/apps/ov2n.png"

    if not os.path.exists(system_icon):
        return  # 系统没有图标，不操作

    system_size = os.path.getsize(system_icon)

    for size_str in ("16x16", "22x22", "24x24", "32x32", "48x48",
                     "64x64", "128x128", "256x256"):
        user_icon = os.path.join(
            xdg_data_home, "icons", "hicolor", size_str, "apps", "ov2n.png")
        if not os.path.exists(user_icon):
            continue
        try:
            user_size = os.path.getsize(user_icon)
            # 若用户图标与系统图标大小不同 → 是之前写入的错误盾牌图标 → 删除
            ref_system = f"/usr/share/icons/hicolor/{size_str}/apps/ov2n.png"
            ref_size = (os.path.getsize(ref_system)
                        if os.path.exists(ref_system) else system_size)
            if user_size != ref_size:
                os.remove(user_icon)
        except Exception:
            pass

    # 刷新用户图标缓存
    try:
        import subprocess as _sp
        _sp.run(
            ["gtk-update-icon-cache", "-f", "-t",
             os.path.join(xdg_data_home, "icons", "hicolor")],
            capture_output=True, timeout=5)
    except Exception:
        pass


def load_window_icon(app_root: str) -> QIcon:
    """
    加载窗口图标。
    - 启动时自动清理之前版本错误写入的用户盾牌图标
    - 从 resources/images/ 或系统 /usr/share/icons/ 加载正确的 ov2n 图标
    - 同时设置 QApplication 元数据，确保 WM_CLASS 和 _NET_WM_ICON 正确
    - 完全没有图标文件时才程序化生成盾牌（兜底）
    - 绝不向磁盘写入任何图标文件
    """
    # 清理历史遗留的错误用户图标
    _cleanup_bad_user_icons()

    candidates = [
        # resources/images/ 下各尺寸
        os.path.join(app_root, "resources", "images", "ov2n256.png"),
        os.path.join(app_root, "resources", "images", "ov2n128.png"),
        os.path.join(app_root, "resources", "images", "ov2n64.png"),
        os.path.join(app_root, "resources", "images", "ov2n48.png"),
        os.path.join(app_root, "resources", "images", "ov2n22.png"),
        # deb 安装后的系统图标路径
        "/usr/share/icons/hicolor/256x256/apps/ov2n.png",
        "/usr/share/icons/hicolor/128x128/apps/ov2n.png",
        "/usr/share/icons/hicolor/64x64/apps/ov2n.png",
        "/usr/share/icons/hicolor/48x48/apps/ov2n.png",
        "/usr/share/icons/hicolor/22x22/apps/ov2n.png",
        "/usr/share/pixmaps/ov2n256.png",
        "/usr/share/pixmaps/ov2n.png",
    ]

    icon = QIcon()
    for path in candidates:
        if os.path.exists(path):
            icon.addFile(path)

    if icon.isNull():
        for size in (16, 22, 24, 32, 48, 64, 128, 256):
            icon.addPixmap(_draw_shield_pixmap(size))

    # 【关键】在 QApplication 层面设置图标和元数据
    # 必须在 QMainWindow.setWindowIcon() 之前执行，
    # 否则 X11 的 _NET_WM_ICON 属性不会被写入
    app = QApplication.instance()
    if app is not None:
        # 设置应用名，Qt 用此生成正确的 WM_CLASS（需与 StartupWMClass= 一致）
        app.setApplicationName("ov2n")
        # 设置 QApplication 级别图标（影响所有窗口和 _NET_WM_ICON）
        app.setWindowIcon(icon)
        # 关联 .desktop 文件（Qt 5.7+，影响 GNOME 任务栏分组）
        try:
            app.setDesktopFileName("ov2n")
        except AttributeError:
            pass

    return icon

def apply_window_icon(window) -> None:
    icon = window.windowIcon()
    if icon.isNull():
        return

    qwindow = window.windowHandle()
    if qwindow is not None:
        qwindow.setIcon(icon)

    window.setWindowIcon(QIcon())
    window.setWindowIcon(icon)

    app = QApplication.instance()
    if app is not None:
        app.setWindowIcon(icon)

    # python-xlib 直写优先，成功则跳过 xprop
    if force_titlebar_icon_x11(window):
        return

    _write_net_wm_icon_xprop(window, icon)


def _write_net_wm_icon_xprop(window, icon: QIcon) -> bool:
    """
    用 xprop 写入 _NET_WM_ICON。
    ★ 关键修复：只写 32x32，避免大图导致参数超过 ARG_MAX 而静默失败。
    256x256 图像会产生 ~65538 个数字，拼成字符串后超过 xprop 能处理的上限。
    """
    try:
        import subprocess as _sp

        wid = int(window.winId())
        icon_data_parts = []

        # ★ 只用 32x32，够标题栏显示用，参数长度安全
        for size in (32, 16):
            pm = icon.pixmap(size, size)
            if pm.isNull():
                continue
            img = pm.toImage()
            img = img.convertToFormat(img.Format_ARGB32)
            w, h = img.width(), img.height()
            icon_data_parts.append(str(w))
            icon_data_parts.append(str(h))
            for y in range(h):
                for x in range(w):
                    pixel = img.pixel(x, y)
                    icon_data_parts.append(str(pixel & 0xFFFFFFFF))

        if not icon_data_parts:
            return False

        data_str = ",".join(icon_data_parts)
        result = _sp.run(
            ["xprop", "-id", str(wid),
             "-format", "_NET_WM_ICON", "32c",
             "-set", "_NET_WM_ICON", data_str],
            capture_output=True, timeout=5)
        return result.returncode == 0

    except FileNotFoundError:
        return False
    except Exception:
        return False

def force_titlebar_icon_x11(window) -> bool:
    try:
        
        icon = window.windowIcon()
        print(f"[debug] icon.isNull() = {icon.isNull()}")  # ★

        if icon.isNull():
            return False

        wid = int(window.winId())
        print(f"[debug] wid = {wid}")  # ★

        icon_data = []
        for size in (32, 22, 16):
            pm = icon.pixmap(size, size)
            print(f"[debug] pixmap({size}) isNull={pm.isNull()} "
                  f"w={pm.width()} h={pm.height()}")  # ★
            if pm.isNull():
                continue
            img = pm.toImage()
            img = img.convertToFormat(img.Format_ARGB32)
            icon_data.append(size)
            icon_data.append(size)
            for y in range(size):
                for x in range(size):
                    pixel = img.pixel(x, y)
                    icon_data.append(pixel & 0xFFFFFFFF)

        print(f"[debug] icon_data length = {len(icon_data)}")  # ★

        if not icon_data:
            return False

        d = xdisplay.Display()
        root = d.screen().root
        xwin = d.create_resource_object('window', wid)
        net_wm_icon = d.intern_atom('_NET_WM_ICON')
        xwin.change_property(net_wm_icon, Xatom.CARDINAL, 32, icon_data)
        d.flush()
        d.close()
        print("[debug] force_titlebar_icon_x11 写入成功")  # ★
        return True

    except ImportError:
        print("[debug] python-xlib 未安装")  # ★
        return False
    except Exception as e:
        print(f"[debug] force_titlebar_icon_x11 异常: {e}")  # ★
        return False

# ──────────────────────────────────────────────
# 4. Qt 标准图标（可选，用于工具栏/菜单）
# ──────────────────────────────────────────────
def get_std_icon(style_enum) -> QIcon:
    """获取 Qt 内置标准图标"""
    app = QApplication.instance()
    if app:
        return app.style().standardIcon(style_enum)
    return QIcon()
"""
主窗口界面 - 重构版
职责：UI 构建、事件处理、状态显示
配置管理、工作线程、样式定义已分别抽离到独立模块

核心设计变更：
  用户导入配置时，将配置文件复制到用户配置目录下（~/.config/ov2n/ 或 %APPDATA%\ov2n\），
  而非仅保存路径。这样即使用户删除了原始文件，程序仍能正常工作。

跨平台兼容改动:
1. 用 icon_helper.btn_text() 替换所有硬编码 emoji
2. 用 icon_helper.load_window_icon() 多路径探测窗口图标
3. 按钮状态统一由 _refresh_buttons() 管理
4. Windows 停止操作改用 WindowsPrivilegeHandler，不再依赖 pkexec
5. edit_v2ray_config 支持 Windows（os.startfile）
6. 联合启动允许只有单侧配置（Windows 独立启动设计）
7. success_signal 兼容 Windows 服务模式（pid=1 表示服务运行）
"""
import os
import platform
import subprocess
import logging
from pathlib import Path
from typing import Optional

from PyQt5.QtGui import QDragEnterEvent, QDropEvent
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QMainWindow, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QWidget,
    QFileDialog, QMessageBox, QCheckBox, QLineEdit,
    QGroupBox, QFormLayout, QSpinBox, QApplication,
)

from core.config_manager import (
    load_imported_flags, save_imported_flags,
    load_tproxy_config, save_tproxy_config,
    extract_tproxy_config_from_v2ray, init_config_dir,
    has_real_vps_config, validate_v2ray_config,
    import_vpn_config, import_v2ray_config,
    get_user_vpn_config_path, get_user_v2ray_config_path,
)
from core.utils import get_app_root, validate_ip
from core.icon_helper import (
    btn_text, drop_area_prefix, check_mark,
    load_window_icon, apply_window_icon, emoji_supported,
)
from core.ss_config_manager import import_ss_url_from_clipboard, V2RayConfigManager
from ui.styles import (
    group_box_style, drop_area_empty_style, drop_area_ok_style,
    btn_green_style, btn_red_style, btn_blue_style, btn_plain_style,
    status_label_style, readonly_line_edit_style,
    readonly_spinbox_style, editable_spinbox_style,
)
from core.vpn_process import create_managers

IS_WINDOWS = platform.system() == "Windows"

log = logging.getLogger("ov2n.ui")

# Linux 专用导入
if not IS_WINDOWS:
    from core.polkit_helper import PolkitHelper


def _get_windows_handler():
    from core.platform.windows.privilege import WindowsPrivilegeHandler
    return WindowsPrivilegeHandler()


# ══════════════════════════════════════════
# 后台工作线程
# ══════════════════════════════════════════

class OpenVPNWorker(QThread):
    """在后台线程启动 OpenVPN，避免 UI 卡死。"""
    update_signal = pyqtSignal(str)        # 进度消息
    error_signal = pyqtSignal(str)         # 错误信息
    success_signal = pyqtSignal(int)       # 成功，返回 PID

    def __init__(self, config_path: Path, openvpn_manager):
        super().__init__()
        self.config_path = config_path
        self.manager = openvpn_manager

    def run(self):
        try:
            self.update_signal.emit("正在启动 OpenVPN...")
            if self.manager.start(self.config_path):
                pid = self.manager.get_pid() or 1
                self.update_signal.emit("OpenVPN 启动成功")
                self.success_signal.emit(pid)
            else:
                self.error_signal.emit("OpenVPN 启动失败，请检查配置文件")
        except Exception as e:
            log.exception("OpenVPN 启动异常")
            self.error_signal.emit(f"OpenVPN 启动异常: {e}")


class XrayWorker(QThread):
    """在后台线程启动 Xray，避免 UI 卡死。"""
    update_signal = pyqtSignal(str)        # 进度消息
    error_signal = pyqtSignal(str)         # 错误信息
    success_signal = pyqtSignal(dict)      # 成功，返回 {"pid": int, "tproxy_ok": bool}

    def __init__(self, config_path: Path, xray_manager, tproxy_enabled: bool = False):
        super().__init__()
        self.config_path = config_path
        self.manager = xray_manager
        self.tproxy_enabled = tproxy_enabled

    def run(self):
        try:
            self.update_signal.emit("正在启动 V2Ray/Xray...")
            if self.manager.start(self.config_path):
                pid = self.manager.get_pid() or 1
                self.update_signal.emit("V2Ray/Xray 启动成功")
                self.success_signal.emit({
                    "pid": pid,
                    "tproxy_ok": self.tproxy_enabled and not IS_WINDOWS
                })
            else:
                self.error_signal.emit("V2Ray/Xray 启动失败，请检查配置文件")
        except Exception as e:
            log.exception("V2Ray/Xray 启动异常")
            self.error_signal.emit(f"V2Ray/Xray 启动异常: {e}")


class CombinedWorker(QThread):
    """顺序启动 OpenVPN 和 Xray，支持单侧启动。"""
    update_signal = pyqtSignal(str)        # 进度消息
    error_signal = pyqtSignal(str)         # 错误信息
    success_signal = pyqtSignal(dict)      # 成功，返回 {"vpn_pid": int, "v2ray_pid": int, "warnings": []}

    def __init__(self, ovpn_mgr, xray_mgr,
                 ovpn_config: Optional[Path] = None,
                 xray_config: Optional[Path] = None,
                 tproxy_enabled: bool = False):
        super().__init__()
        self.ovpn_mgr = ovpn_mgr
        self.xray_mgr = xray_mgr
        self.ovpn_config = ovpn_config
        self.xray_config = xray_config
        self.tproxy_enabled = tproxy_enabled

    def run(self):
        result = {"vpn_pid": 0, "v2ray_pid": 0, "warnings": []}
        try:
            # 启动 OpenVPN（如果配置存在）
            if self.ovpn_config and self.ovpn_config.exists():
                self.update_signal.emit("正在启动 OpenVPN...")
                if self.ovpn_mgr.start(self.ovpn_config):
                    result["vpn_pid"] = self.ovpn_mgr.get_pid() or 1
                    self.update_signal.emit("OpenVPN 启动成功")
                else:
                    result["warnings"].append("OpenVPN 启动失败")

            # 启动 Xray（如果配置存在）
            if self.xray_config and self.xray_config.exists():
                self.update_signal.emit("正在启动 V2Ray/Xray...")
                if self.xray_mgr.start(self.xray_config):
                    result["v2ray_pid"] = self.xray_mgr.get_pid() or 1
                    result["tproxy_ok"] = self.tproxy_enabled and not IS_WINDOWS
                    self.update_signal.emit("V2Ray/Xray 启动成功")
                else:
                    result["warnings"].append("V2Ray/Xray 启动失败")

            # 检查是否至少有一个服务启动成功
            if result["vpn_pid"] or result["v2ray_pid"]:
                self.success_signal.emit(result)
            else:
                self.error_signal.emit("所有服务启动失败")
        except Exception as e:
            log.exception("联合启动异常")
            self.error_signal.emit(f"启动异常: {e}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ov2n Client")
        self.setGeometry(200, 200, 400, 750)
        self.setAcceptDrops(True)

        # ── 运行状态 ──────────────────────────────
        # Windows 服务模式：vpn_pid=1 表示 OV2NService 运行中（无真实 PID）
        #                   v2ray_pid=1 表示 xray 进程运行中
        # Linux：存储真实 PID
        self.vpn_pid = None
        self.v2ray_pid = None
        self.tproxy_active = False

        # ── 进程管理器 ────────────────────────────
        app_root = Path(get_app_root())
        self.openvpn_mgr, self.xray_mgr = create_managers(app_root)

        # ── 窗口图标 ──────────────────────────────
        self._window_icon = load_window_icon(str(app_root))
        self.setWindowIcon(self._window_icon)
        app = QApplication.instance()
        if app is not None:
            app.setWindowIcon(self._window_icon)

        # ── 构建 UI ──────────────────────────────
        self._build_ui()

        # ── 初始化用户配置目录 ─────────────────────
        init_config_dir()

        # ── 配置路径（固定位于用户配置目录下）─────────
        self.vpn_config_path = Path(get_user_vpn_config_path())
        self.v2ray_config_path = Path(get_user_v2ray_config_path())

        # ── 导入状态 ──────────────────────────────
        # 首次运行：imported_flags 均为 False，用户配置目录下无配置文件
        # 再次运行：从持久化存储恢复导入状态
        flags = load_imported_flags()
        self.vpn_config_imported = flags['vpn']
        self.v2ray_config_imported = flags['v2ray']

        # ── 启动时校验：同步导入标志与实际文件状态 ──
        # 场景1: imported_flags 残留 True 但文件已不存在
        #         （理论上不应发生，因为文件在用户配置目录下由程序管理）
        #         → 重置为 False
        # 场景2: imported_flags 为 False 但文件存在且包含真实 VPS 配置
        #         （如 imported_flags.json 丢失/损坏）→ 恢复为 True
        flags_changed = False

        if self.vpn_config_imported and not self.vpn_config_path.exists():
            log.warning("VPN 配置文件不存在，重置导入标志: %s", self.vpn_config_path)
            self.vpn_config_imported = False
            flags_changed = True

        if self.v2ray_config_imported and not self.v2ray_config_path.exists():
            log.warning("V2Ray 配置文件不存在，重置导入标志: %s", self.v2ray_config_path)
            self.v2ray_config_imported = False
            flags_changed = True

        # 恢复丢失的导入标志：文件存在且包含真实 VPS 配置 → 视为已导入
        if (not self.v2ray_config_imported
                and self.v2ray_config_path.exists()
                and has_real_vps_config(str(self.v2ray_config_path))):
            log.info("V2Ray 配置包含真实 VPS 信息，恢复导入标志")
            self.v2ray_config_imported = True
            flags_changed = True

        if (not self.vpn_config_imported
                and self.vpn_config_path.exists()
                and self.vpn_config_path.stat().st_size > 0):
            log.info("VPN 配置文件存在且非空，恢复导入标志")
            self.vpn_config_imported = True
            flags_changed = True

        if flags_changed:
            save_imported_flags(self.vpn_config_imported, self.v2ray_config_imported)

        self._update_config_display()
        self._auto_extract_tproxy_config()
        self._refresh_buttons()

        log.info("emoji 支持: %s", emoji_supported())
        log.info("平台: %s", "Windows" if IS_WINDOWS else "Linux")

    # ══════════════════════════════════════════
    # UI 构建
    # ══════════════════════════════════════════

    def _build_ui(self):
        """构建所有 UI 控件和布局。"""
        # ── 连接状态 ──────────────────────────────
        self.status_group = QGroupBox("连接状态")
        self.status_group.setStyleSheet(group_box_style())
        sl = QVBoxLayout()
        self.vpn_status_label = QLabel("OpenVPN: 未连接")
        self.v2ray_status_label = QLabel("V2Ray: 未连接")
        for lbl in (self.vpn_status_label, self.v2ray_status_label):
            lbl.setStyleSheet(status_label_style("#999"))
            sl.addWidget(lbl)
        self.status_group.setLayout(sl)

        # ── VPN 配置 ───────────────────────────────
        self.vpn_group = QGroupBox("VPN 配置")
        self.vpn_group.setStyleSheet(group_box_style())
        vl = QVBoxLayout()

        self.vpn_drop_area = QLabel(
            f"{drop_area_prefix()}点击选择或拖拽 .ovpn 配置文件到此处")
        self.vpn_drop_area.setAlignment(Qt.AlignCenter)
        self.vpn_drop_area.setStyleSheet(drop_area_empty_style())
        self.vpn_drop_area.setMinimumHeight(80)
        self.vpn_drop_area.mousePressEvent = lambda e: self.select_vpn_config()
        vl.addWidget(self.vpn_drop_area)

        vbl = QHBoxLayout()
        self.start_vpn_button = QPushButton(btn_text("start", "启动 VPN"))
        self.start_vpn_button.setStyleSheet(btn_green_style())
        self.start_vpn_button.clicked.connect(self.start_vpn_only)
        self.stop_vpn_button = QPushButton(btn_text("stop", "停止 VPN"))
        self.stop_vpn_button.setStyleSheet(btn_red_style())
        self.stop_vpn_button.clicked.connect(self.stop_vpn_only)
        vbl.addWidget(self.start_vpn_button)
        vbl.addWidget(self.stop_vpn_button)
        vl.addLayout(vbl)
        self.vpn_group.setLayout(vl)

        # ── Shadowsocks 配置 ───────────────────────
        self.ss_group = QGroupBox("Shadowsocks 配置")
        self.ss_group.setStyleSheet(group_box_style())
        ssl = QVBoxLayout()

        self.v2ray_drop_area = QLabel(
            f"{drop_area_prefix()}点击选择或拖拽 config.json 到此处")
        self.v2ray_drop_area.setAlignment(Qt.AlignCenter)
        self.v2ray_drop_area.setStyleSheet(drop_area_empty_style())
        self.v2ray_drop_area.setMinimumHeight(60)
        self.v2ray_drop_area.mousePressEvent = lambda e: self.select_v2ray_config()
        ssl.addWidget(self.v2ray_drop_area)

        sr1 = QHBoxLayout()
        self.import_ss_button = QPushButton(btn_text("import_clip", "从剪贴板导入"))
        self.import_ss_button.setStyleSheet(btn_blue_style())
        self.import_ss_button.clicked.connect(self.import_ss_from_clipboard)
        self.edit_ss_button = QPushButton(btn_text("edit", "手动编辑"))
        self.edit_ss_button.setStyleSheet(btn_plain_style())
        self.edit_ss_button.clicked.connect(self.edit_v2ray_config)
        sr1.addWidget(self.import_ss_button)
        sr1.addWidget(self.edit_ss_button)

        sr2 = QHBoxLayout()
        self.start_v2ray_button = QPushButton(btn_text("start", "启动 V2Ray"))
        self.start_v2ray_button.setStyleSheet(btn_green_style(small=True))
        self.start_v2ray_button.clicked.connect(self.start_v2ray_only)
        self.stop_v2ray_button = QPushButton(btn_text("stop", "停止 V2Ray"))
        self.stop_v2ray_button.setStyleSheet(btn_red_style(small=True))
        self.stop_v2ray_button.clicked.connect(self.stop_v2ray_only)
        sr2.addWidget(self.start_v2ray_button)
        sr2.addWidget(self.stop_v2ray_button)

        ssl.addLayout(sr1)
        ssl.addLayout(sr2)
        self.ss_group.setLayout(ssl)

        # ── TProxy ─────────────────────────────────
        tc = load_tproxy_config()
        self.tproxy_group = QGroupBox("透明代理 (TProxy)")
        self.tproxy_group.setStyleSheet(group_box_style())
        tl = QFormLayout()

        self.tproxy_checkbox = QCheckBox("启用透明代理(从配置自动获取参数)")
        self.tproxy_checkbox.setChecked(tc["enabled"])
        tl.addRow(self.tproxy_checkbox)

        self.vps_ip_input = QLineEdit(tc["vps_ip"])
        self.vps_ip_input.setPlaceholderText("将从 V2Ray 配置自动提取")
        self.vps_ip_input.setReadOnly(True)
        self.vps_ip_input.setStyleSheet(readonly_line_edit_style())
        tl.addRow("VPS IP:", self.vps_ip_input)

        self.tproxy_port_input = QSpinBox()
        self.tproxy_port_input.setRange(1, 65535)
        self.tproxy_port_input.setValue(tc["port"])
        self.tproxy_port_input.setReadOnly(True)
        self.tproxy_port_input.setButtonSymbols(QSpinBox.NoButtons)
        self.tproxy_port_input.setStyleSheet(readonly_spinbox_style())
        tl.addRow("TProxy 端口:", self.tproxy_port_input)

        self.mark_input = QSpinBox()
        self.mark_input.setRange(1, 255)
        self.mark_input.setValue(tc["mark"])
        self.mark_input.setButtonSymbols(QSpinBox.NoButtons)
        self.mark_input.setStyleSheet(editable_spinbox_style())
        tl.addRow("fwmark:", self.mark_input)

        self.table_input = QSpinBox()
        self.table_input.setRange(1, 252)
        self.table_input.setValue(tc["table"])
        self.table_input.setButtonSymbols(QSpinBox.NoButtons)
        self.table_input.setStyleSheet(editable_spinbox_style())
        tl.addRow("路由表:", self.table_input)

        self.tproxy_group.setLayout(tl)
        self._toggle_tproxy_inputs(self.tproxy_checkbox.isChecked())
        self.tproxy_checkbox.toggled.connect(self._toggle_tproxy_inputs)

        # Windows 上 TProxy 不适用，隐藏整个分组
        if IS_WINDOWS:
            self.tproxy_group.setVisible(False)

        # ── 底部联合按钮 ───────────────────────────
        self.start_all_button = QPushButton(btn_text("start", "启动 VPN + V2Ray"))
        self.start_all_button.setStyleSheet(btn_green_style(large=True))
        self.start_all_button.clicked.connect(self.start_combined)

        self.stop_all_button = QPushButton(btn_text("stop", "停止 VPN + V2Ray"))
        self.stop_all_button.setStyleSheet(btn_red_style(large=True))
        self.stop_all_button.clicked.connect(self.stop_combined)

        # ── 主布局 ────────────────────────────────
        layout = QVBoxLayout()
        layout.addWidget(self.status_group)
        layout.addWidget(self.vpn_group)
        layout.addWidget(self.ss_group)
        layout.addWidget(self.tproxy_group)
        layout.addSpacing(10)
        layout.addWidget(self.start_all_button)
        layout.addWidget(self.stop_all_button)
        layout.addStretch()

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    # ══════════════════════════════════════════
    # 按钮状态统一管理
    # ══════════════════════════════════════════

    def _refresh_buttons(self, starting: bool = False):
        vpn_running = bool(self.vpn_pid)
        v2ray_running = bool(self.v2ray_pid)
        both_running = vpn_running and v2ray_running

        self.start_vpn_button.setEnabled(not vpn_running and not starting)
        self.start_v2ray_button.setEnabled(not v2ray_running and not starting)
        self.start_all_button.setEnabled(not both_running and not starting)

        self.stop_vpn_button.setEnabled(vpn_running)
        self.stop_v2ray_button.setEnabled(v2ray_running)
        self.stop_all_button.setEnabled(vpn_running or v2ray_running)

    # ══════════════════════════════════════════
    # 配置显示与提取
    # ══════════════════════════════════════════

    def _update_config_display(self):
        cm = check_mark()
        dp = drop_area_prefix()

        if self.vpn_config_imported and self.vpn_config_path.exists():
            self.vpn_drop_area.setText(f"{cm}{self.vpn_config_path.name}")
            self.vpn_drop_area.setStyleSheet(drop_area_ok_style())
        else:
            self.vpn_drop_area.setText(f"{dp}点击选择或拖拽 .ovpn 配置文件到此处")
            self.vpn_drop_area.setStyleSheet(drop_area_empty_style())

        if self.v2ray_config_imported and self.v2ray_config_path.exists():
            self.v2ray_drop_area.setText(f"{cm}{self.v2ray_config_path.name}")
            self.v2ray_drop_area.setStyleSheet(drop_area_ok_style(pad="15px"))
        else:
            self.v2ray_drop_area.setText(f"{dp}点击选择或拖拽 config.json 到此处")
            self.v2ray_drop_area.setStyleSheet(drop_area_empty_style())

    def _auto_extract_tproxy_config(self):
        if not self.v2ray_config_path.exists():
            return
        extracted = extract_tproxy_config_from_v2ray(str(self.v2ray_config_path))
        if extracted:
            self.tproxy_checkbox.setChecked(True)
            self.vps_ip_input.setText(extracted['vps_ip'])
            self.tproxy_port_input.setValue(extracted['tproxy_port'])
            save_tproxy_config(
                True, extracted['vps_ip'], extracted['tproxy_port'],
                self.mark_input.value(), self.table_input.value())

    def _toggle_tproxy_inputs(self, enabled: bool):
        self.mark_input.setEnabled(enabled)
        self.table_input.setEnabled(enabled)

    # ══════════════════════════════════════════
    # 配置就绪检查
    # ══════════════════════════════════════════

    def _check_vpn_ready(self) -> bool:
        if not self.vpn_config_imported or not self.vpn_config_path.exists():
            QMessageBox.warning(self, "未导入 VPN 配置",
                "请先导入 OpenVPN 配置文件 (.ovpn)。\n\n"
                "您可以：\n"
                "• 点击 VPN 配置区域选择文件\n"
                "• 将 .ovpn 文件拖拽到 VPN 配置区域")
            return False
        return True

    def _check_v2ray_ready(self) -> bool:
        if not self.v2ray_config_imported or not self.v2ray_config_path.exists():
            QMessageBox.warning(self, "未导入 V2Ray 配置",
                "请先导入 V2Ray/Shadowsocks 配置。\n\n"
                "您可以：\n"
                "• 点击「从剪贴板导入」粘贴 ss:// 链接\n"
                "• 点击 Shadowsocks 配置区域选择 config.json\n"
                "• 将 config.json 拖拽到配置区域")
            return False
        return True

    def _validate_tproxy_params(self) -> bool:
        """Windows 上 TProxy 不适用，始终返回 True。"""
        if IS_WINDOWS:
            return True
        if not self.tproxy_checkbox.isChecked():
            return True
        vps_ip = self.vps_ip_input.text().strip()
        if not vps_ip or not validate_ip(vps_ip):
            QMessageBox.critical(
                self, "错误", "启用透明代理时必须配置有效的 VPS IP 地址")
            return False
        return True

    def _get_tproxy_params(self) -> dict:
        return {
            'tproxy_enabled': self.tproxy_checkbox.isChecked() and not IS_WINDOWS,
            'tproxy_port': self.tproxy_port_input.value(),
            'tproxy_vps_ip': self.vps_ip_input.text().strip(),
            'tproxy_mark': self.mark_input.value(),
            'tproxy_table': self.table_input.value(),
        }

    # ══════════════════════════════════════════
    # 配置导入（拖拽 + 文件选择 + 剪贴板）
    # ══════════════════════════════════════════

    def _on_vpn_config_imported(self, source_path: str):
        """
        处理 VPN 配置导入：将源文件复制到用户配置目录。

        Args:
            source_path: 用户选择/拖拽的源文件路径
        """
        try:
            import_vpn_config(source_path)
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"复制 VPN 配置文件失败:\n{e}")
            return

        self.vpn_config_imported = True
        save_imported_flags(self.vpn_config_imported, self.v2ray_config_imported)
        self.vpn_drop_area.setText(f"{check_mark()}{Path(source_path).name}")
        self.vpn_drop_area.setStyleSheet(drop_area_ok_style())

    def _on_v2ray_config_imported(self, source_path: str):
        """
        处理 V2Ray 配置导入：将源文件复制到用户配置目录。

        Args:
            source_path: 用户选择/拖拽的源文件路径
        """
        try:
            import_v2ray_config(source_path)
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"复制 V2Ray 配置文件失败:\n{e}")
            return

        self.v2ray_config_imported = True
        save_imported_flags(self.vpn_config_imported, self.v2ray_config_imported)
        self.v2ray_drop_area.setText(f"{check_mark()}{Path(source_path).name}")
        self.v2ray_drop_area.setStyleSheet(drop_area_ok_style(pad="15px"))
        self._auto_extract_tproxy_config()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        if path.endswith('.ovpn'):
            self._on_vpn_config_imported(path)
            QMessageBox.information(
                self, "成功", f"已加载 OpenVPN 配置:\n{Path(path).name}")
        elif path.endswith('.json'):
            self._on_v2ray_config_imported(path)
            QMessageBox.information(
                self, "成功", f"已加载 V2Ray 配置:\n{Path(path).name}")
        else:
            QMessageBox.warning(
                self, "错误", "不支持的文件类型!\n请拖拽 .ovpn 或 .json 文件")

    def select_vpn_config(self):
        start = os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 OpenVPN 配置文件", start,
            "OVPN 文件 (*.ovpn);;所有文件 (*)")
        if path:
            self._on_vpn_config_imported(path)

    def select_v2ray_config(self):
        start = os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 V2Ray 配置文件", start,
            "JSON 文件 (*.json);;所有文件 (*)")
        if path:
            self._on_v2ray_config_imported(path)

    def import_ss_from_clipboard(self):
        """从剪贴板导入 SS URL，生成的配置直接保存到用户配置目录。"""
        try:
            self.v2ray_config_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法创建配置目录: {e}")
            return

        # import_ss_url_from_clipboard 会将配置写入 self.v2ray_config_path
        # 由于 self.v2ray_config_path 已经指向用户配置目录，无需额外复制
        if import_ss_url_from_clipboard(
                self, str(self.v2ray_config_path), replace_existing=True):
            self.v2ray_config_imported = True
            save_imported_flags(self.vpn_config_imported, self.v2ray_config_imported)
            self.v2ray_drop_area.setText(
                f"{check_mark()}{self.v2ray_config_path.name} (已更新)")
            self.v2ray_drop_area.setStyleSheet(drop_area_ok_style(pad="15px"))
            self._auto_extract_tproxy_config()
            QMessageBox.information(
                self, "成功",
                "配置已更新，透明代理参数已自动提取。\n如需应用，请重启 V2Ray。")

    def edit_v2ray_config(self):
        if not self.v2ray_config_path.exists():
            try:
                self.v2ray_config_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法创建配置目录: {e}")
                return
            V2RayConfigManager(str(self.v2ray_config_path)).save_config()
        try:
            if IS_WINDOWS:
                os.startfile(str(self.v2ray_config_path))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(self.v2ray_config_path)])
            QMessageBox.information(
                self, "提示",
                "配置文件已在外部编辑器中打开。\n编辑完成后请重启 V2Ray 以应用更改。")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法打开编辑器: {e}")

    # ══════════════════════════════════════════
    # 状态标签更新
    # ══════════════════════════════════════════

    def _set_vpn_status(self, msg: str, color: str):
        self.vpn_status_label.setText(f"OpenVPN: {msg}")
        self.vpn_status_label.setStyleSheet(status_label_style(color))

    def _set_v2ray_status(self, msg: str, color: str):
        self.v2ray_status_label.setText(f"V2Ray: {msg}")
        self.v2ray_status_label.setStyleSheet(status_label_style(color))

    # ══════════════════════════════════════════
    # VPN 独立启停
    # ══════════════════════════════════════════

    def start_vpn_only(self):
        if not self._check_vpn_ready():
            return
        if self.vpn_pid:
            QMessageBox.warning(self, "警告", "OpenVPN 已在运行")
            return
        self._refresh_buttons(starting=True)
        self._set_vpn_status("正在启动...", "#FF9800")
        self._vpn_worker = OpenVPNWorker(self.vpn_config_path, self.openvpn_mgr)
        self._vpn_worker.update_signal.connect(
            lambda m: self._set_vpn_status(m, "#FF9800"))
        self._vpn_worker.error_signal.connect(self._on_vpn_error)
        self._vpn_worker.success_signal.connect(self._on_vpn_started)
        self._vpn_worker.start()

    def _on_vpn_started(self, pid: int):
        self.vpn_pid = pid
        if IS_WINDOWS:
            self._set_vpn_status("✓ 服务运行中 (OV2NService)", "#4CAF50")
        else:
            self._set_vpn_status(f"✓ 已连接 (PID: {pid})", "#4CAF50")
        self._refresh_buttons()

    def _on_vpn_error(self, err: str):
        self._set_vpn_status("未连接", "#999")
        self._refresh_buttons()
        QMessageBox.critical(self, "OpenVPN 启动失败", err)

    def stop_vpn_only(self):
        if not self.vpn_pid:
            return
        self.stop_vpn_button.setEnabled(False)
        self._set_vpn_status("正在停止...", "#FF9800")
        try:
            self.openvpn_mgr.stop()
            self.vpn_pid = None
            self._set_vpn_status("未连接", "#999")
            self._refresh_buttons()
            QMessageBox.information(self, "成功", "OpenVPN 已停止")
        except Exception as e:
            self._refresh_buttons()
            QMessageBox.critical(self, "错误", f"停止失败: {e}")

    # ══════════════════════════════════════════
    # V2Ray 独立启停
    # ══════════════════════════════════════════

    def start_v2ray_only(self):
        if not self._check_v2ray_ready():
            return
        if self.v2ray_pid:
            QMessageBox.warning(self, "警告", "V2Ray 已在运行")
            return
        if not self._validate_tproxy_params():
            return
        self._refresh_buttons(starting=True)
        self._set_v2ray_status("正在启动...", "#FF9800")
        tproxy_enabled = self.tproxy_checkbox.isChecked() and not IS_WINDOWS
        self._v2ray_worker = XrayWorker(
            self.v2ray_config_path, self.xray_mgr, tproxy_enabled)
        self._v2ray_worker.update_signal.connect(
            lambda m: self._set_v2ray_status(m, "#FF9800"))
        self._v2ray_worker.error_signal.connect(self._on_v2ray_error)
        self._v2ray_worker.success_signal.connect(self._on_v2ray_started)
        self._v2ray_worker.start()

    def _on_v2ray_started(self, result: dict):
        pid = result['pid'] or 1
        self.v2ray_pid = pid
        self.tproxy_active = result.get('tproxy_ok', False)
        if IS_WINDOWS:
            self._set_v2ray_status("✓ Xray 运行中 (TUN)", "#4CAF50")
        else:
            suffix = " + TProxy" if self.tproxy_active else ""
            self._set_v2ray_status(f"✓ 已连接{suffix} (PID: {pid})", "#4CAF50")
        self._refresh_buttons()

    def _on_v2ray_error(self, err: str):
        self._set_v2ray_status("未连接", "#999")
        self._refresh_buttons()
        QMessageBox.critical(self, "V2Ray 启动失败", err)

    def stop_v2ray_only(self):
        if not self.v2ray_pid:
            return
        self.stop_v2ray_button.setEnabled(False)
        self._set_v2ray_status("正在停止...", "#FF9800")
        try:
            self.xray_mgr.stop()
            self.v2ray_pid = None
            self._set_v2ray_status("未连接", "#999")
            self._refresh_buttons()
            QMessageBox.information(self, "成功", "V2Ray 已停止")
        except Exception as e:
            self._refresh_buttons()
            QMessageBox.critical(self, "错误", f"停止失败: {e}")

    # ══════════════════════════════════════════
    # 联合启停
    # ══════════════════════════════════════════

    def start_combined(self):
        """
        Linux: 两侧配置都必须就绪。
        Windows: 至少有一侧配置即可（独立启动设计）。
        """
        if IS_WINDOWS:
            # Windows：有哪个配置就启动哪个，两者都没有才报错
            vpn_ready = (self.vpn_config_imported
                         and self.vpn_config_path.exists())
            v2ray_ready = (self.v2ray_config_imported
                           and self.v2ray_config_path.exists())
            if not vpn_ready and not v2ray_ready:
                QMessageBox.warning(self, "未导入配置",
                    "请至少导入一个配置文件：\n"
                    "• OpenVPN 配置 (.ovpn)\n"
                    "• V2Ray/Xray 配置 (config.json)")
                return
        else:
            if not self._check_vpn_ready() or not self._check_v2ray_ready():
                return
            if not self._validate_tproxy_params():
                return

        self._refresh_buttons(starting=True)
        tproxy_enabled = self.tproxy_checkbox.isChecked() and not IS_WINDOWS
        if not IS_WINDOWS:
            tproxy_params = self._get_tproxy_params()
            save_tproxy_config(
                tproxy_params['tproxy_enabled'],
                tproxy_params['tproxy_vps_ip'],
                tproxy_params['tproxy_port'],
                tproxy_params['tproxy_mark'],
                tproxy_params['tproxy_table'])

        # 确定要启动的配置
        ovpn_cfg = self.vpn_config_path if (
            self.vpn_config_imported and self.vpn_config_path.exists()) else None
        xray_cfg = self.v2ray_config_path if (
            self.v2ray_config_imported and self.v2ray_config_path.exists()) else None

        self._combined_worker = CombinedWorker(
            self.openvpn_mgr, self.xray_mgr,
            ovpn_cfg, xray_cfg, tproxy_enabled)
        self._combined_worker.update_signal.connect(self._on_combined_update)
        self._combined_worker.error_signal.connect(self._on_combined_error)
        self._combined_worker.success_signal.connect(self._on_combined_started)
        self._combined_worker.start()

    def _on_combined_update(self, msg: str):
        if "OpenVPN" in msg:
            self._set_vpn_status(msg, "#FF9800")
        elif "V2Ray" in msg or "Xray" in msg:
            self._set_v2ray_status(msg, "#FF9800")

    def _on_combined_started(self, result: dict):
        vpn_pid = result.get('vpn_pid', 0)
        v2ray_pid = result.get('v2ray_pid', 0)
        warnings = result.get('warnings', [])

        if vpn_pid:
            self.vpn_pid = vpn_pid
            if IS_WINDOWS:
                self._set_vpn_status("✓ 服务运行中 (OV2NService)", "#4CAF50")
            else:
                self._set_vpn_status(f"✓ 已连接 (PID: {vpn_pid})", "#4CAF50")

        if v2ray_pid:
            self.v2ray_pid = v2ray_pid
            self.tproxy_active = result.get('tproxy_ok', False)
            if IS_WINDOWS:
                self._set_v2ray_status("✓ Xray 运行中 (TUN)", "#4CAF50")
            else:
                suffix = " + TProxy" if self.tproxy_active else ""
                self._set_v2ray_status(
                    f"✓ 已连接{suffix} (PID: {v2ray_pid})", "#4CAF50")

        self._refresh_buttons()

        # 部分失败时显示警告，不阻断成功流程
        if warnings:
            QMessageBox.warning(self, "部分启动失败",
                "以下服务启动失败，其他服务已正常启动：\n\n"
                + "\n".join(f"• {w}" for w in warnings))
        else:
            started = []
            if vpn_pid:
                started.append("OpenVPN")
            if v2ray_pid:
                started.append("V2Ray/Xray")
            if started:
                QMessageBox.information(self, "成功",
                    " + ".join(started) + " 已启动")

    def _on_combined_error(self, err: str):
        self._refresh_buttons()
        QMessageBox.critical(self, "启动失败", err)

    def stop_combined(self):
        if not self.vpn_pid and not self.v2ray_pid:
            QMessageBox.warning(self, "警告", "没有运行中的服务")
            return
        self.stop_all_button.setEnabled(False)
        try:
            if self.v2ray_pid:
                self._set_v2ray_status("正在停止...", "#FF9800")
                self.xray_mgr.stop()
                self.v2ray_pid = None
                self._set_v2ray_status("未连接", "#999")

            if self.vpn_pid:
                self._set_vpn_status("正在停止...", "#FF9800")
                self.openvpn_mgr.stop()
                self.vpn_pid = None
                self._set_vpn_status("未连接", "#999")

            self._refresh_buttons()
            QMessageBox.information(self, "成功", "所有服务已停止")
        except Exception as e:
            self._refresh_buttons()
            QMessageBox.critical(self, "错误", f"停止失败: {e}")

    # ══════════════════════════════════════════
    # 窗口事件
    # ══════════════════════════════════════════

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(100, lambda: apply_window_icon(self))

    def closeEvent(self, event):
        if self.vpn_pid or self.v2ray_pid:
            reply = QMessageBox.question(
                self, "确认退出",
                "服务正在运行中，确定要退出吗？\n退出将自动停止所有服务。",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.stop_combined()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
"""
主窗口界面 - 多发行版适配版本
跨平台兼容改动:
1. 用 icon_helper.btn_text() 替换所有硬编码 emoji，Kylin 等不支持 emoji 的系统
   会自动降级为 Unicode 纯文字符号（▶ ■ ⊕ 等），无方块乱码
2. 用 icon_helper.load_window_icon() 多路径探测窗口图标，Ubuntu 标题栏图标不显示
   时自动使用程序化生成的盾牌图标兜底
3. 其余逻辑与上一版本完全一致
"""
import os
import sys
import time
import subprocess
from PyQt5.QtGui import QIcon, QDragEnterEvent, QDropEvent
from PyQt5.QtCore import Qt, QThread, pyqtSignal
import re
import json
from PyQt5.QtWidgets import (
    QMainWindow, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QWidget,
    QFileDialog, QMessageBox, QCheckBox, QLineEdit,
    QGroupBox, QFormLayout, QSpinBox, QApplication
)
from core.ss_config_manager import (
    import_ss_url_from_clipboard,
    V2RayConfigManager
)
from core.polkit_helper import PolkitHelper
from core.icon_helper import (
    btn_text, drop_area_prefix, check_mark,
    load_window_icon, emoji_supported
)

# ============================================
# 辅助函数
# ============================================
def get_app_root():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


TPROXY_CONF_PATH   = os.path.expanduser("~/.config/ov2n/tproxy.conf")
CONFIG_PATHS_FILE  = os.path.expanduser("~/.config/ov2n/config_paths.json")
IMPORTED_FLAGS_FILE = os.path.expanduser("~/.config/ov2n/imported_flags.json")


def load_imported_flags():
    defaults = {'vpn': False, 'v2ray': False}
    if not os.path.exists(IMPORTED_FLAGS_FILE):
        return defaults
    try:
        with open(IMPORTED_FLAGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {'vpn': data.get('vpn', False), 'v2ray': data.get('v2ray', False)}
    except Exception:
        return defaults


def save_imported_flags(vpn_imported, v2ray_imported):
    try:
        os.makedirs(os.path.dirname(IMPORTED_FLAGS_FILE), exist_ok=True)
        with open(IMPORTED_FLAGS_FILE, 'w', encoding='utf-8') as f:
            json.dump({'vpn': vpn_imported, 'v2ray': v2ray_imported}, f)
    except Exception as e:
        print(f"保存导入标志失败: {e}")


def load_config_paths():
    defaults = {
        'vpn_config':   os.path.expanduser("~/.config/ov2n/client.ovpn"),
        'v2ray_config': os.path.expanduser("~/.config/ov2n/config.json")
    }
    if not os.path.exists(CONFIG_PATHS_FILE):
        return defaults
    try:
        with open(CONFIG_PATHS_FILE, 'r', encoding='utf-8') as f:
            saved = json.load(f)
        vpn   = saved.get('vpn_config',   defaults['vpn_config'])
        v2ray = saved.get('v2ray_config', defaults['v2ray_config'])
        return {
            'vpn_config':   vpn   if os.path.exists(vpn)   else defaults['vpn_config'],
            'v2ray_config': v2ray if os.path.exists(v2ray) else defaults['v2ray_config'],
        }
    except Exception as e:
        print(f"加载配置路径失败: {e}")
        return defaults


def save_config_paths(vpn_config, v2ray_config):
    try:
        os.makedirs(os.path.dirname(CONFIG_PATHS_FILE), exist_ok=True)
        with open(CONFIG_PATHS_FILE, 'w', encoding='utf-8') as f:
            json.dump({'vpn_config': vpn_config, 'v2ray_config': v2ray_config},
                      f, indent=2, ensure_ascii=False)
        print("✓ 配置路径已保存")
    except Exception as e:
        print(f"保存配置路径失败: {e}")


def load_tproxy_config():
    defaults = {"enabled": False, "vps_ip": "", "port": 12345, "mark": 1, "table": 100}
    if not os.path.exists(TPROXY_CONF_PATH):
        return defaults
    try:
        data = {}
        with open(TPROXY_CONF_PATH) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    data[k.strip()] = v.strip()
        defaults["enabled"] = data.get("TPROXY_ENABLED", "false").lower() == "true"
        defaults["vps_ip"]  = data.get("VPS_IP", "")
        defaults["port"]    = int(data.get("V2RAY_PORT", 12345))
        defaults["mark"]    = int(data.get("MARK", 1))
        defaults["table"]   = int(data.get("TABLE", 100))
    except Exception as e:
        print(f"加载 tproxy 配置失败: {e}")
    return defaults


def save_tproxy_config(enabled, vps_ip, port, mark, table):
    try:
        os.makedirs(os.path.dirname(TPROXY_CONF_PATH), exist_ok=True)
        with open(TPROXY_CONF_PATH, "w") as f:
            f.write("# ov2n TProxy 配置\n")
            f.write(f"TPROXY_ENABLED={'true' if enabled else 'false'}\n")
            f.write(f"VPS_IP={vps_ip}\n")
            f.write(f"V2RAY_PORT={port}\n")
            f.write(f"MARK={mark}\n")
            f.write(f"TABLE={table}\n")
    except Exception as e:
        print(f"保存 tproxy 配置失败: {e}")


def extract_tproxy_config_from_v2ray(config_path):
    if not os.path.exists(config_path):
        return None
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        vps_ip = tproxy_port = None
        for ob in config.get('outbounds', []):
            if ob.get('protocol') in ['shadowsocks', 'vmess', 'vless', 'trojan', 'socks', 'http']:
                servers = ob.get('settings', {}).get('servers', [])
                if servers:
                    addr = servers[0].get('address', '')
                    if addr and re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', addr):
                        vps_ip = addr
                        break
        for ib in config.get('inbounds', []):
            if ib.get('protocol') == 'dokodemo-door':
                if ib.get('settings', {}).get('network') in ['tcp,udp', 'tcp', 'udp']:
                    tproxy_port = ib.get('port')
                    break
            elif 'tproxy' in ib.get('tag', '').lower():
                tproxy_port = ib.get('port')
                break
        if vps_ip and tproxy_port:
            print(f"✓ 自动提取配置成功: VPS IP={vps_ip}, TProxy端口={tproxy_port}")
            return {'vps_ip': vps_ip, 'tproxy_port': tproxy_port}
        print(f"⚠ 配置提取不完整: VPS IP={vps_ip}, TProxy端口={tproxy_port}")
        return None
    except Exception as e:
        print(f"✗ 提取配置失败: {e}")
        return None


# ============================================
# 独立启动线程
# ============================================
class SingleVPNThread(QThread):
    update_signal  = pyqtSignal(str)
    error_signal   = pyqtSignal(str)
    success_signal = pyqtSignal(int)

    def __init__(self, vpn_config_path):
        super().__init__()
        self.vpn_config_path = vpn_config_path

    def run(self):
        try:
            self.update_signal.emit("正在启动 OpenVPN...")
            cmd = ["pkexec", PolkitHelper.HELPER_SCRIPT, "start-vpn-only", self.vpn_config_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'OpenVPN PID:' in line:
                        self.success_signal.emit(int(line.split(':')[1].strip()))
                        return
                self.error_signal.emit("无法获取 OpenVPN PID\n\n日志: cat /tmp/openvpn.log")
            else:
                err = result.stderr.strip()
                if "dismissed" in err.lower() or "cancelled" in err.lower():
                    self.error_signal.emit("用户取消了权限授权")
                else:
                    detail = f"stderr:\n{err}\n" if err else ""
                    out = result.stdout.strip()
                    if out:
                        detail += f"stdout:\n{out}\n"
                    if not detail:
                        detail = "无详细输出，请查看: cat /tmp/openvpn.log"
                    self.error_signal.emit(f"OpenVPN 启动失败 (退出码 {result.returncode}):\n\n{detail}")
        except subprocess.TimeoutExpired:
            self.error_signal.emit("OpenVPN 启动超时（60s），请检查配置文件是否正确")
        except Exception as e:
            self.error_signal.emit(f"OpenVPN 启动异常: {e}")


class SingleV2RayThread(QThread):
    update_signal  = pyqtSignal(str)
    error_signal   = pyqtSignal(str)
    success_signal = pyqtSignal(dict)

    def __init__(self, v2ray_config_path, tproxy_enabled=False,
                 tproxy_port=12345, tproxy_vps_ip="", tproxy_mark=1, tproxy_table=100):
        super().__init__()
        self.v2ray_config_path = v2ray_config_path
        self.tproxy_enabled    = tproxy_enabled
        self.tproxy_port       = tproxy_port
        self.tproxy_vps_ip     = tproxy_vps_ip
        self.tproxy_mark       = tproxy_mark
        self.tproxy_table      = tproxy_table

    def run(self):
        try:
            self.update_signal.emit("正在启动 V2Ray...")
            cmd = ["pkexec", PolkitHelper.HELPER_SCRIPT, "start-v2ray-only", self.v2ray_config_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                err = result.stderr.strip()
                if "dismissed" in err.lower() or "cancelled" in err.lower():
                    self.error_signal.emit("用户取消了权限授权")
                else:
                    detail = f"stderr:\n{err}\n" if err else ""
                    out = result.stdout.strip()
                    if out:
                        detail += f"stdout:\n{out}\n"
                    if not detail:
                        detail = "无详细输出，请查看: cat /tmp/v2ray.log"
                    self.error_signal.emit(f"V2Ray 启动失败 (退出码 {result.returncode}):\n\n{detail}")
                return

            v2ray_pid = None
            for line in result.stdout.split('\n'):
                if 'V2Ray PID:' in line:
                    v2ray_pid = int(line.split(':')[1].strip())
                    break
            if not v2ray_pid:
                self.error_signal.emit("无法获取 V2Ray PID\n\n日志: cat /tmp/v2ray.log")
                return

            tproxy_ok = False
            if self.tproxy_enabled:
                self.update_signal.emit("正在配置透明代理...")
                time.sleep(1)
                ok, msg = PolkitHelper.start_tproxy(
                    self.tproxy_port, self.tproxy_vps_ip, self.tproxy_mark, self.tproxy_table)
                tproxy_ok = ok
                self.update_signal.emit("✓ 透明代理已配置" if ok else f"⚠ 透明代理配置失败: {msg}")

            self.success_signal.emit({'pid': v2ray_pid, 'tproxy_ok': tproxy_ok})
        except subprocess.TimeoutExpired:
            self.error_signal.emit("V2Ray 启动超时（60s）")
        except Exception as e:
            self.error_signal.emit(f"V2Ray 启动异常: {e}")


class CombinedStartThread(QThread):
    update_signal  = pyqtSignal(str)
    error_signal   = pyqtSignal(str)
    success_signal = pyqtSignal(dict)

    def __init__(self, vpn_config_path, v2ray_config_path,
                 current_vpn_pid, current_v2ray_pid,
                 tproxy_enabled=False, tproxy_port=12345,
                 tproxy_vps_ip="", tproxy_mark=1, tproxy_table=100):
        super().__init__()
        self.vpn_config_path   = vpn_config_path
        self.v2ray_config_path = v2ray_config_path
        self.current_vpn_pid   = current_vpn_pid
        self.current_v2ray_pid = current_v2ray_pid
        self.tproxy_enabled    = tproxy_enabled
        self.tproxy_port       = tproxy_port
        self.tproxy_vps_ip     = tproxy_vps_ip
        self.tproxy_mark       = tproxy_mark
        self.tproxy_table      = tproxy_table

    def _fmt_error(self, result, fallback_log):
        err = result.stderr.strip() if result.stderr else ""
        out = result.stdout.strip() if result.stdout else ""
        detail = (f"stderr:\n{err}\n" if err else "") + (f"stdout:\n{out}\n" if out else "")
        return detail or f"无详细输出，请查看: {fallback_log}"

    def run(self):
        try:
            res_vpn_pid   = self.current_vpn_pid
            res_v2ray_pid = self.current_v2ray_pid
            tproxy_ok     = False

            # 步骤 1: VPN
            if not self.current_vpn_pid:
                self.update_signal.emit("正在启动 OpenVPN...")
                r = subprocess.run(
                    ["pkexec", PolkitHelper.HELPER_SCRIPT, "start-vpn-only", self.vpn_config_path],
                    capture_output=True, text=True, timeout=60)
                if r.returncode != 0:
                    self.error_signal.emit(
                        f"OpenVPN 启动失败 (退出码 {r.returncode}):\n\n"
                        + self._fmt_error(r, "cat /tmp/openvpn.log"))
                    return
                for line in r.stdout.split('\n'):
                    if 'OpenVPN PID:' in line:
                        res_vpn_pid = int(line.split(':')[1].strip())
                        break
                if not res_vpn_pid:
                    self.error_signal.emit("无法获取 OpenVPN PID\n\n日志: cat /tmp/openvpn.log")
                    return
            else:
                self.update_signal.emit("OpenVPN 已在运行，跳过启动")

            # 步骤 2: V2Ray
            if not self.current_v2ray_pid:
                self.update_signal.emit("正在启动 V2Ray...")
                r = subprocess.run(
                    ["pkexec", PolkitHelper.HELPER_SCRIPT, "start-v2ray-only", self.v2ray_config_path],
                    capture_output=True, text=True, timeout=60)
                if r.returncode != 0:
                    self.error_signal.emit(
                        f"V2Ray 启动失败 (退出码 {r.returncode}):\n\n"
                        + self._fmt_error(r, "cat /tmp/v2ray.log"))
                    if res_vpn_pid and not self.current_vpn_pid:
                        self._stop(res_vpn_pid, "openvpn")
                    return
                for line in r.stdout.split('\n'):
                    if 'V2Ray PID:' in line:
                        res_v2ray_pid = int(line.split(':')[1].strip())
                        break
                if not res_v2ray_pid:
                    self.error_signal.emit("无法获取 V2Ray PID\n\n日志: cat /tmp/v2ray.log")
                    if res_vpn_pid and not self.current_vpn_pid:
                        self._stop(res_vpn_pid, "openvpn")
                    return
            else:
                self.update_signal.emit("V2Ray 已在运行，跳过启动")

            # 步骤 3: TProxy
            if self.tproxy_enabled:
                self.update_signal.emit("正在配置透明代理...")
                time.sleep(1)
                ok, msg = PolkitHelper.start_tproxy(
                    self.tproxy_port, self.tproxy_vps_ip, self.tproxy_mark, self.tproxy_table)
                tproxy_ok = ok
                if not ok:
                    self.update_signal.emit(f"⚠ 透明代理配置失败: {msg}")

            self.success_signal.emit({
                'vpn_pid': res_vpn_pid, 'v2ray_pid': res_v2ray_pid, 'tproxy_ok': tproxy_ok})

        except subprocess.TimeoutExpired:
            self.error_signal.emit("启动超时（60s），请检查配置文件是否正确")
        except Exception as e:
            self.error_signal.emit(f"启动异常: {e}")

    def _stop(self, pid, name):
        try:
            subprocess.run(
                ["pkexec", PolkitHelper.HELPER_SCRIPT, "stop", f"--{name}-pid", str(pid)],
                capture_output=True, text=True, timeout=30)
        except Exception:
            pass


# ============================================
# 主窗口
# ============================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ov2n Client")
        self.setGeometry(200, 200, 400, 750)
        self.setAcceptDrops(True)

        # ★ 跨发行版窗口图标加载
        app_root = get_app_root()
        self.setWindowIcon(load_window_icon(app_root))

        # ── 连接状态 ──────────────────────────────
        self.status_group = QGroupBox("连接状态")
        self.status_group.setStyleSheet(self._gs())
        sl = QVBoxLayout()
        self.vpn_status_label   = QLabel("OpenVPN: 未连接")
        self.v2ray_status_label = QLabel("V2Ray: 未连接")
        for lbl in (self.vpn_status_label, self.v2ray_status_label):
            lbl.setStyleSheet("color: #999; padding: 5px; font-size: 12px;")
            sl.addWidget(lbl)
        self.status_group.setLayout(sl)

        # ── VPN 配置 ───────────────────────────────
        self.vpn_group = QGroupBox("VPN 配置")
        self.vpn_group.setStyleSheet(self._gs())
        vl = QVBoxLayout()

        self.vpn_drop_area = QLabel(f"{drop_area_prefix()}点击选择或拖拽 .ovpn 配置文件到此处")
        self.vpn_drop_area.setAlignment(Qt.AlignCenter)
        self.vpn_drop_area.setStyleSheet(self._drop_empty())
        self.vpn_drop_area.setMinimumHeight(80)
        self.vpn_drop_area.mousePressEvent = lambda e: self.select_vpn_config()
        vl.addWidget(self.vpn_drop_area)

        vbl = QHBoxLayout()
        # ★ btn_text() 自动适配 emoji / 纯文字
        self.start_vpn_button = QPushButton(btn_text("start", "启动 VPN"))
        self.start_vpn_button.setStyleSheet(self._btn_green())
        self.start_vpn_button.clicked.connect(self.start_vpn_only)
        self.stop_vpn_button = QPushButton(btn_text("stop", "停止 VPN"))
        self.stop_vpn_button.setStyleSheet(self._btn_red())
        self.stop_vpn_button.setEnabled(False)
        self.stop_vpn_button.clicked.connect(self.stop_vpn_only)
        vbl.addWidget(self.start_vpn_button)
        vbl.addWidget(self.stop_vpn_button)
        vl.addLayout(vbl)
        self.vpn_group.setLayout(vl)

        # ── Shadowsocks 配置 ───────────────────────
        self.ss_group = QGroupBox("Shadowsocks 配置")
        self.ss_group.setStyleSheet(self._gs())
        ssl = QVBoxLayout()

        self.v2ray_drop_area = QLabel(f"{drop_area_prefix()}点击选择或拖拽 config.json 到此处")
        self.v2ray_drop_area.setAlignment(Qt.AlignCenter)
        self.v2ray_drop_area.setStyleSheet(self._drop_empty())
        self.v2ray_drop_area.setMinimumHeight(60)
        self.v2ray_drop_area.mousePressEvent = lambda e: self.select_v2ray_config()
        ssl.addWidget(self.v2ray_drop_area)

        sr1 = QHBoxLayout()
        self.import_ss_button = QPushButton(btn_text("import_clip", "从剪贴板导入"))
        self.import_ss_button.setStyleSheet(self._btn_blue())
        self.import_ss_button.clicked.connect(self.import_ss_from_clipboard)
        self.edit_ss_button = QPushButton(btn_text("edit", "手动编辑"))
        self.edit_ss_button.setStyleSheet(self._btn_plain())
        self.edit_ss_button.clicked.connect(self.edit_v2ray_config)
        sr1.addWidget(self.import_ss_button)
        sr1.addWidget(self.edit_ss_button)

        sr2 = QHBoxLayout()
        self.start_v2ray_button = QPushButton(btn_text("start", "启动 V2Ray"))
        self.start_v2ray_button.setStyleSheet(self._btn_green(small=True))
        self.start_v2ray_button.clicked.connect(self.start_v2ray_only)
        self.stop_v2ray_button = QPushButton(btn_text("stop", "停止 V2Ray"))
        self.stop_v2ray_button.setStyleSheet(self._btn_red(small=True))
        self.stop_v2ray_button.setEnabled(False)
        self.stop_v2ray_button.clicked.connect(self.stop_v2ray_only)
        sr2.addWidget(self.start_v2ray_button)
        sr2.addWidget(self.stop_v2ray_button)

        sbg = QVBoxLayout()
        sbg.addLayout(sr1)
        sbg.addLayout(sr2)
        ssl.addLayout(sbg)
        self.ss_group.setLayout(ssl)

        # ── TProxy ─────────────────────────────────
        tc = load_tproxy_config()
        self.tproxy_group = QGroupBox("透明代理 (TProxy)")
        self.tproxy_group.setStyleSheet(self._gs())
        tl = QFormLayout()

        self.tproxy_checkbox = QCheckBox("启用透明代理(从配置自动获取参数)")
        self.tproxy_checkbox.setChecked(tc["enabled"])
        tl.addRow(self.tproxy_checkbox)

        self.vps_ip_input = QLineEdit(tc["vps_ip"])
        self.vps_ip_input.setPlaceholderText("将从 V2Ray 配置自动提取")
        self.vps_ip_input.setReadOnly(True)
        self.vps_ip_input.setStyleSheet(
            "QLineEdit { background-color: #f5f5f5; color: #666; }")
        tl.addRow("VPS IP:", self.vps_ip_input)

        self.tproxy_port_input = QSpinBox()
        self.tproxy_port_input.setRange(1, 65535)
        self.tproxy_port_input.setValue(tc["port"])
        self.tproxy_port_input.setReadOnly(True)
        self.tproxy_port_input.setButtonSymbols(QSpinBox.NoButtons)
        self.tproxy_port_input.setStyleSheet(
            "QSpinBox { background-color: #f5f5f5; color: #666; "
            "border: 1px solid #ddd; border-radius: 3px; padding: 4px; }")
        tl.addRow("TProxy 端口:", self.tproxy_port_input)

        self.mark_input = QSpinBox()
        self.mark_input.setRange(1, 255)
        self.mark_input.setValue(tc["mark"])
        self.mark_input.setButtonSymbols(QSpinBox.NoButtons)
        self.mark_input.setStyleSheet(
            "QSpinBox { border: 1px solid #ccc; border-radius: 3px; padding: 4px; }")
        tl.addRow("fwmark:", self.mark_input)

        self.table_input = QSpinBox()
        self.table_input.setRange(1, 252)
        self.table_input.setValue(tc["table"])
        self.table_input.setButtonSymbols(QSpinBox.NoButtons)
        self.table_input.setStyleSheet(
            "QSpinBox { border: 1px solid #ccc; border-radius: 3px; padding: 4px; }")
        tl.addRow("路由表:", self.table_input)

        self.tproxy_group.setLayout(tl)
        self._toggle_tproxy_inputs(self.tproxy_checkbox.isChecked())
        self.tproxy_checkbox.toggled.connect(self._toggle_tproxy_inputs)

        # ── 底部联合按钮 ───────────────────────────
        self.start_all_button = QPushButton(btn_text("start", "启动 VPN + V2Ray"))
        self.start_all_button.setStyleSheet(self._btn_green(large=True))
        self.start_all_button.clicked.connect(self.start_combined)

        self.stop_all_button = QPushButton(btn_text("stop", "停止 VPN + V2Ray"))
        self.stop_all_button.setStyleSheet(self._btn_red(large=True))
        self.stop_all_button.setEnabled(False)
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

        # ── 初始化状态 ────────────────────────────
        self.vpn_pid      = None
        self.v2ray_pid    = None
        self.tproxy_active = False

        flags = load_imported_flags()
        self.vpn_config_imported   = flags['vpn']
        self.v2ray_config_imported = flags['v2ray']

        paths = load_config_paths()
        self.vpn_config_path   = paths['vpn_config']
        self.v2ray_config_path = paths['v2ray_config']

        self._init_config_files()
        self._update_config_display()
        self._auto_extract_tproxy_config()

        # ★ 调试信息：打印 emoji 支持状态，方便排查
        print(f"[ov2n] emoji 支持: {emoji_supported()}")

    # ══════════════════════════════════════════
    # 样式辅助（提取为方法，避免重复）
    # ══════════════════════════════════════════
    def _gs(self):  # group style
        return """
            QGroupBox {
                font-size: 13px; font-weight: bold;
                border: 1px solid #ccc; border-radius: 5px;
                margin-top: 10px; padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 10px; padding: 0 5px;
            }
        """

    def _drop_empty(self):
        return """
            QLabel {
                border: 2px dashed #ccc; border-radius: 5px;
                padding: 15px; background-color: #f9f9f9; color: #666;
            }
            QLabel:hover { border-color: #2196F3; background-color: #f0f8ff; }
        """

    def _drop_ok(self, pad="20px"):
        return f"""
            QLabel {{
                border: 2px solid #4CAF50; border-radius: 5px;
                padding: {pad}; background-color: #f1f8f4; color: #4CAF50;
            }}
        """

    def _btn_green(self, small=False, large=False):
        pad  = "15px" if large else ("8px" if small else "10px")
        sz   = "14px" if large else ("11px" if small else "12px")
        bold = "font-weight: bold;" if large else ""
        r    = "5px" if large else "4px"
        return f"""
            QPushButton {{
                background-color: #4CAF50; color: white;
                padding: {pad}; font-size: {sz}; {bold}
                border-radius: {r}; border: none; outline: none;
            }}
            QPushButton:hover    {{ background-color: #45a049; }}
            QPushButton:disabled {{ background-color: #cccccc; color: #666666; }}
            QPushButton:focus    {{ outline: none; }}
        """

    def _btn_red(self, small=False, large=False):
        pad  = "15px" if large else ("8px" if small else "10px")
        sz   = "14px" if large else ("11px" if small else "12px")
        bold = "font-weight: bold;" if large else ""
        r    = "5px" if large else "4px"
        return f"""
            QPushButton {{
                background-color: #f44336; color: white;
                padding: {pad}; font-size: {sz}; {bold}
                border-radius: {r}; border: none; outline: none;
            }}
            QPushButton:hover    {{ background-color: #da190b; }}
            QPushButton:disabled {{ background-color: #cccccc; color: #666666; }}
            QPushButton:focus    {{ outline: none; }}
        """

    def _btn_blue(self):
        return """
            QPushButton {
                background-color: #2196F3; color: white;
                padding: 8px; font-size: 11px;
                border-radius: 4px; border: none; outline: none;
            }
            QPushButton:hover { background-color: #1976D2; }
            QPushButton:focus { outline: none; }
        """

    def _btn_plain(self):
        return """
            QPushButton {
                padding: 8px; font-size: 11px;
                border: 1px solid #ccc; border-radius: 4px;
                background-color: white; outline: none;
            }
            QPushButton:hover { background-color: #f5f5f5; }
            QPushButton:focus { outline: none; border: 1px solid #2196F3; }
        """

    # ══════════════════════════════════════════
    # 初始化
    # ══════════════════════════════════════════
    def _init_config_files(self):
        app_root     = get_app_root()
        dev_vpn      = os.path.join(app_root, "core", "openvpn", "client.ovpn")
        dev_v2ray    = os.path.join(app_root, "core", "xray", "config.json")
        user_cfg_dir = os.path.dirname(self.v2ray_config_path)
        os.makedirs(user_cfg_dir, exist_ok=True)

        if not os.path.exists(self.v2ray_config_path):
            if os.path.exists(dev_v2ray):
                import shutil
                try:
                    shutil.copy2(dev_v2ray, self.v2ray_config_path)
                except Exception as e:
                    print(f"复制失败: {e}")
                    self._create_default_v2ray_config()
            else:
                self._create_default_v2ray_config()
        elif not self._validate_v2ray_config(self.v2ray_config_path):
            import shutil
            try:
                shutil.copy2(self.v2ray_config_path, self.v2ray_config_path + ".backup")
            except Exception:
                pass
            self._create_default_v2ray_config()

        if not os.path.exists(self.vpn_config_path) and os.path.exists(dev_vpn):
            import shutil
            try:
                shutil.copy2(dev_vpn, self.vpn_config_path)
            except Exception:
                pass

    def _validate_v2ray_config(self, path):
        try:
            if os.path.getsize(path) == 0:
                return False
            with open(path, 'r', encoding='utf-8') as f:
                cfg = json.loads(f.read())
            return 'inbounds' in cfg and 'outbounds' in cfg
        except Exception:
            return False

    def _create_default_v2ray_config(self):
        cfg = {
            "log": {"loglevel": "warning"},
            "inbounds": [
                {"tag": "socks", "port": 1080, "protocol": "socks",
                 "settings": {"auth": "noauth", "udp": True}},
                {"tag": "http", "port": 1081, "protocol": "http"},
                {"tag": "tproxy", "port": 12345, "protocol": "dokodemo-door",
                 "settings": {"network": "tcp,udp", "followRedirect": True},
                 "streamSettings": {"sockopt": {"tproxy": "tproxy"}}}
            ],
            "outbounds": [
                {"tag": "proxy", "protocol": "shadowsocks",
                 "settings": {"servers": [{"address": "your.server.com", "port": 8388,
                                           "method": "chacha20-ietf-poly1305",
                                           "password": "your_password_here"}]}},
                {"tag": "direct", "protocol": "freedom", "settings": {}},
                {"tag": "block",  "protocol": "blackhole",
                 "settings": {"response": {"type": "http"}}}
            ],
            "routing": {
                "domainStrategy": "IPOnDemand",
                "rules": [
                    {"type": "field", "ip": ["geoip:private"],    "outboundTag": "direct"},
                    {"type": "field", "domain": ["geosite:cn"],   "outboundTag": "direct"},
                    {"type": "field", "ip": ["geoip:cn"],         "outboundTag": "direct"}
                ]
            }
        }
        try:
            with open(self.v2ray_config_path, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            print("✓ 默认 V2Ray 配置已创建")
        except Exception as e:
            print(f"创建默认 V2Ray 配置失败: {e}")

    def _update_config_display(self):
        cm = check_mark()
        dp = drop_area_prefix()
        if self.vpn_config_imported and os.path.exists(self.vpn_config_path):
            self.vpn_drop_area.setText(f"{cm}{os.path.basename(self.vpn_config_path)}")
            self.vpn_drop_area.setStyleSheet(self._drop_ok())
        else:
            self.vpn_drop_area.setText(f"{dp}点击选择或拖拽 .ovpn 配置文件到此处")
            self.vpn_drop_area.setStyleSheet(self._drop_empty())

        if self.v2ray_config_imported and os.path.exists(self.v2ray_config_path):
            self.v2ray_drop_area.setText(f"{cm}{os.path.basename(self.v2ray_config_path)}")
            self.v2ray_drop_area.setStyleSheet(self._drop_ok(pad="15px"))
        else:
            self.v2ray_drop_area.setText(f"{dp}点击选择或拖拽 config.json 到此处")
            self.v2ray_drop_area.setStyleSheet(self._drop_empty())

    def _auto_extract_tproxy_config(self):
        if not os.path.exists(self.v2ray_config_path):
            return
        extracted = extract_tproxy_config_from_v2ray(self.v2ray_config_path)
        if extracted:
            self.tproxy_checkbox.setChecked(True)
            self.vps_ip_input.setText(extracted['vps_ip'])
            self.tproxy_port_input.setValue(extracted['tproxy_port'])
            save_tproxy_config(True, extracted['vps_ip'], extracted['tproxy_port'],
                               self.mark_input.value(), self.table_input.value())

    def _toggle_tproxy_inputs(self, enabled):
        self.mark_input.setEnabled(enabled)
        self.table_input.setEnabled(enabled)

    def _validate_ip(self, ip):
        m = re.match(r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$', ip)
        return m and all(int(g) <= 255 for g in m.groups())

    # ══════════════════════════════════════════
    # 配置检查
    # ══════════════════════════════════════════
    def _check_vpn_ready(self):
        if not self.vpn_config_imported or not os.path.exists(self.vpn_config_path):
            QMessageBox.warning(self, "未导入 VPN 配置",
                "请先导入 OpenVPN 配置文件 (.ovpn)。\n\n"
                "您可以：\n"
                "• 点击 VPN 配置区域选择文件\n"
                "• 将 .ovpn 文件拖拽到 VPN 配置区域")
            return False
        return True

    def _check_v2ray_ready(self):
        if not self.v2ray_config_imported or not os.path.exists(self.v2ray_config_path):
            QMessageBox.warning(self, "未导入 V2Ray 配置",
                "请先导入 V2Ray/Shadowsocks 配置。\n\n"
                "您可以：\n"
                "• 点击「从剪贴板导入」粘贴 ss:// 链接\n"
                "• 点击 Shadowsocks 配置区域选择 config.json\n"
                "• 将 config.json 拖拽到配置区域")
            return False
        return True

    # ══════════════════════════════════════════
    # 拖拽
    # ══════════════════════════════════════════
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        cm   = check_mark()

        if path.endswith('.ovpn'):
            self.vpn_config_path     = path
            self.vpn_config_imported = True
            save_imported_flags(self.vpn_config_imported, self.v2ray_config_imported)
            self.vpn_drop_area.setText(f"{cm}{os.path.basename(path)}")
            self.vpn_drop_area.setStyleSheet(self._drop_ok())
            save_config_paths(self.vpn_config_path, self.v2ray_config_path)
            QMessageBox.information(self, "成功", f"已加载 OpenVPN 配置:\n{os.path.basename(path)}")

        elif path.endswith('.json'):
            self.v2ray_config_path     = path
            self.v2ray_config_imported = True
            save_imported_flags(self.vpn_config_imported, self.v2ray_config_imported)
            self.v2ray_drop_area.setText(f"{cm}{os.path.basename(path)}")
            self.v2ray_drop_area.setStyleSheet(self._drop_ok(pad="15px"))
            self._auto_extract_tproxy_config()
            save_config_paths(self.vpn_config_path, self.v2ray_config_path)
            QMessageBox.information(self, "成功", f"已加载 V2Ray 配置:\n{os.path.basename(path)}")
        else:
            QMessageBox.warning(self, "错误", "不支持的文件类型!\n请拖拽 .ovpn 或 .json 文件")

    # ══════════════════════════════════════════
    # 文件选择
    # ══════════════════════════════════════════
    def select_vpn_config(self):
        start = os.path.dirname(self.vpn_config_path) if os.path.exists(
            self.vpn_config_path) else os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 OpenVPN 配置文件", start, "OVPN 文件 (*.ovpn);;所有文件 (*)")
        if path:
            self.vpn_config_path     = path
            self.vpn_config_imported = True
            save_imported_flags(self.vpn_config_imported, self.v2ray_config_imported)
            self.vpn_drop_area.setText(f"{check_mark()}{os.path.basename(path)}")
            self.vpn_drop_area.setStyleSheet(self._drop_ok())
            save_config_paths(self.vpn_config_path, self.v2ray_config_path)

    def select_v2ray_config(self):
        start = os.path.dirname(self.v2ray_config_path) if os.path.exists(
            self.v2ray_config_path) else os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 V2Ray 配置文件", start, "JSON 文件 (*.json);;所有文件 (*)")
        if path:
            self.v2ray_config_path     = path
            self.v2ray_config_imported = True
            save_imported_flags(self.vpn_config_imported, self.v2ray_config_imported)
            self.v2ray_drop_area.setText(f"{check_mark()}{os.path.basename(path)}")
            self.v2ray_drop_area.setStyleSheet(self._drop_ok(pad="15px"))
            self._auto_extract_tproxy_config()
            save_config_paths(self.vpn_config_path, self.v2ray_config_path)

    # ══════════════════════════════════════════
    # VPN 独立启停
    # ══════════════════════════════════════════
    def start_vpn_only(self):
        if not self._check_vpn_ready():
            return
        if self.vpn_pid:
            QMessageBox.warning(self, "警告", "OpenVPN 已在运行")
            return
        self.start_vpn_button.setEnabled(False)
        self._set_vpn_status("正在启动...", "#FF9800")
        self.vpn_thread = SingleVPNThread(self.vpn_config_path)
        self.vpn_thread.update_signal.connect(
            lambda m: self._set_vpn_status(m, "#FF9800"))
        self.vpn_thread.error_signal.connect(self._on_vpn_error)
        self.vpn_thread.success_signal.connect(self._on_vpn_started)
        self.vpn_thread.start()

    def _on_vpn_started(self, pid):
        self.vpn_pid = pid
        self._set_vpn_status(f"✓ 已连接 (PID: {pid})", "#4CAF50")
        self.stop_vpn_button.setEnabled(True)
        self.start_vpn_button.setEnabled(True)
        self._update_stop_all()

    def _on_vpn_error(self, err):
        self._set_vpn_status("未连接", "#999")
        self.start_vpn_button.setEnabled(True)
        QMessageBox.critical(self, "OpenVPN 启动失败", err)

    def stop_vpn_only(self):
        if not self.vpn_pid:
            return
        self.stop_vpn_button.setEnabled(False)
        self._set_vpn_status("正在停止...", "#FF9800")
        try:
            r = subprocess.run(
                ["pkexec", PolkitHelper.HELPER_SCRIPT, "stop", "--openvpn-pid", str(self.vpn_pid)],
                capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                self.vpn_pid = None
                self._set_vpn_status("未连接", "#999")
                self._update_stop_all()
                QMessageBox.information(self, "成功", "OpenVPN 已停止")
            else:
                self.stop_vpn_button.setEnabled(True)
                QMessageBox.critical(self, "错误", f"停止失败:\n{r.stderr}")
        except Exception as e:
            self.stop_vpn_button.setEnabled(True)
            QMessageBox.critical(self, "错误", f"停止失败: {e}")

    def _set_vpn_status(self, msg, color):
        self.vpn_status_label.setText(f"OpenVPN: {msg}")
        self.vpn_status_label.setStyleSheet(
            f"color: {color}; padding: 5px; font-size: 12px;")

    # ══════════════════════════════════════════
    # V2Ray 独立启停
    # ══════════════════════════════════════════
    def start_v2ray_only(self):
        if not self._check_v2ray_ready():
            return
        if self.v2ray_pid:
            QMessageBox.warning(self, "警告", "V2Ray 已在运行")
            return
        tproxy_enabled = self.tproxy_checkbox.isChecked()
        if tproxy_enabled:
            vps_ip = self.vps_ip_input.text().strip()
            if not vps_ip or not self._validate_ip(vps_ip):
                QMessageBox.critical(self, "错误", "启用透明代理时必须配置有效的 VPS IP 地址")
                return
        self.start_v2ray_button.setEnabled(False)
        self._set_v2ray_status("正在启动...", "#FF9800")
        self.v2ray_thread = SingleV2RayThread(
            self.v2ray_config_path, tproxy_enabled=tproxy_enabled,
            tproxy_port=self.tproxy_port_input.value(),
            tproxy_vps_ip=self.vps_ip_input.text().strip(),
            tproxy_mark=self.mark_input.value(),
            tproxy_table=self.table_input.value())
        self.v2ray_thread.update_signal.connect(
            lambda m: self._set_v2ray_status(m, "#FF9800"))
        self.v2ray_thread.error_signal.connect(self._on_v2ray_error)
        self.v2ray_thread.success_signal.connect(self._on_v2ray_started)
        self.v2ray_thread.start()

    def _on_v2ray_started(self, result):
        self.v2ray_pid    = result['pid']
        self.tproxy_active = result['tproxy_ok']
        suffix = " + TProxy" if result['tproxy_ok'] else ""
        self._set_v2ray_status(f"✓ 已连接{suffix} (PID: {result['pid']})", "#4CAF50")
        self.stop_v2ray_button.setEnabled(True)
        self.start_v2ray_button.setEnabled(True)
        self._update_stop_all()

    def _on_v2ray_error(self, err):
        self._set_v2ray_status("未连接", "#999")
        self.start_v2ray_button.setEnabled(True)
        QMessageBox.critical(self, "V2Ray 启动失败", err)

    def stop_v2ray_only(self):
        if not self.v2ray_pid:
            return
        self.stop_v2ray_button.setEnabled(False)
        self._set_v2ray_status("正在停止...", "#FF9800")
        try:
            if self.tproxy_active:
                PolkitHelper.stop_tproxy(self.tproxy_port_input.value(),
                    self.vps_ip_input.text().strip(),
                    self.mark_input.value(), self.table_input.value())
                self.tproxy_active = False
            r = subprocess.run(
                ["pkexec", PolkitHelper.HELPER_SCRIPT, "stop", "--v2ray-pid", str(self.v2ray_pid)],
                capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                self.v2ray_pid = None
                self._set_v2ray_status("未连接", "#999")
                self._update_stop_all()
                QMessageBox.information(self, "成功", "V2Ray 已停止")
            else:
                self.stop_v2ray_button.setEnabled(True)
                QMessageBox.critical(self, "错误", f"停止失败:\n{r.stderr}")
        except Exception as e:
            self.stop_v2ray_button.setEnabled(True)
            QMessageBox.critical(self, "错误", f"停止失败: {e}")

    def _set_v2ray_status(self, msg, color):
        self.v2ray_status_label.setText(f"V2Ray: {msg}")
        self.v2ray_status_label.setStyleSheet(
            f"color: {color}; padding: 5px; font-size: 12px;")

    # ══════════════════════════════════════════
    # 联合启停
    # ══════════════════════════════════════════
    def start_combined(self):
        if not self._check_vpn_ready() or not self._check_v2ray_ready():
            return
        tproxy_enabled = self.tproxy_checkbox.isChecked()
        if tproxy_enabled:
            vps_ip = self.vps_ip_input.text().strip()
            if not vps_ip or not self._validate_ip(vps_ip):
                QMessageBox.critical(self, "错误", "启用透明代理时必须配置有效的 VPS IP 地址")
                return
        save_tproxy_config(tproxy_enabled, self.vps_ip_input.text().strip(),
                           self.tproxy_port_input.value(),
                           self.mark_input.value(), self.table_input.value())
        self._set_all_start_enabled(False)

        self.combined_thread = CombinedStartThread(
            self.vpn_config_path, self.v2ray_config_path,
            self.vpn_pid, self.v2ray_pid,
            tproxy_enabled=tproxy_enabled,
            tproxy_port=self.tproxy_port_input.value(),
            tproxy_vps_ip=self.vps_ip_input.text().strip(),
            tproxy_mark=self.mark_input.value(),
            tproxy_table=self.table_input.value())
        self.combined_thread.update_signal.connect(self._on_combined_update)
        self.combined_thread.error_signal.connect(self._on_combined_error)
        self.combined_thread.success_signal.connect(self._on_combined_started)
        self.combined_thread.start()

    def _on_combined_update(self, msg):
        if "OpenVPN" in msg:
            self._set_vpn_status(msg, "#FF9800")
        elif "V2Ray" in msg:
            self._set_v2ray_status(msg, "#FF9800")

    def _on_combined_started(self, result):
        self.vpn_pid       = result['vpn_pid']
        self.v2ray_pid     = result['v2ray_pid']
        self.tproxy_active = result['tproxy_ok']
        if self.vpn_pid:
            self._set_vpn_status(f"✓ 已连接 (PID: {self.vpn_pid})", "#4CAF50")
            self.stop_vpn_button.setEnabled(True)
        if self.v2ray_pid:
            suffix = " + TProxy" if self.tproxy_active else ""
            self._set_v2ray_status(f"✓ 已连接{suffix} (PID: {self.v2ray_pid})", "#4CAF50")
            self.stop_v2ray_button.setEnabled(True)
        self._set_all_start_enabled(True)
        self._update_stop_all()
        QMessageBox.information(self, "成功", "VPN + V2Ray 已启动")

    def _on_combined_error(self, err):
        self._set_all_start_enabled(True)
        QMessageBox.critical(self, "启动失败", err)

    def stop_combined(self):
        if not self.vpn_pid and not self.v2ray_pid:
            QMessageBox.warning(self, "警告", "没有运行中的服务")
            return
        self.stop_all_button.setEnabled(False)
        try:
            if self.tproxy_active:
                PolkitHelper.stop_tproxy(self.tproxy_port_input.value(),
                    self.vps_ip_input.text().strip(),
                    self.mark_input.value(), self.table_input.value())
                self.tproxy_active = False
            if self.v2ray_pid:
                self._set_v2ray_status("正在停止...", "#FF9800")
                r = subprocess.run(
                    ["pkexec", PolkitHelper.HELPER_SCRIPT, "stop",
                     "--v2ray-pid", str(self.v2ray_pid)],
                    capture_output=True, text=True, timeout=30)
                if r.returncode == 0:
                    self.v2ray_pid = None
                    self._set_v2ray_status("未连接", "#999")
                    self.stop_v2ray_button.setEnabled(False)
            if self.vpn_pid:
                self._set_vpn_status("正在停止...", "#FF9800")
                r = subprocess.run(
                    ["pkexec", PolkitHelper.HELPER_SCRIPT, "stop",
                     "--openvpn-pid", str(self.vpn_pid)],
                    capture_output=True, text=True, timeout=30)
                if r.returncode == 0:
                    self.vpn_pid = None
                    self._set_vpn_status("未连接", "#999")
                    self.stop_vpn_button.setEnabled(False)
            self._update_stop_all()
            QMessageBox.information(self, "成功", "所有服务已停止")
        except Exception as e:
            self._update_stop_all()
            QMessageBox.critical(self, "错误", f"停止失败: {e}")

    def _set_all_start_enabled(self, enabled):
        self.start_all_button.setEnabled(enabled)
        self.start_vpn_button.setEnabled(enabled)
        self.start_v2ray_button.setEnabled(enabled)

    def _update_stop_all(self):
        self.stop_all_button.setEnabled(bool(self.vpn_pid or self.v2ray_pid))

    # ══════════════════════════════════════════
    # SS / 编辑
    # ══════════════════════════════════════════
    def import_ss_from_clipboard(self):
        try:
            os.makedirs(os.path.dirname(self.v2ray_config_path), exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法创建配置目录: {e}")
            return
        if import_ss_url_from_clipboard(self, self.v2ray_config_path, replace_existing=True):
            self.v2ray_config_imported = True
            save_imported_flags(self.vpn_config_imported, self.v2ray_config_imported)
            cm = check_mark()
            self.v2ray_drop_area.setText(
                f"{cm}{os.path.basename(self.v2ray_config_path)} (已更新)")
            self.v2ray_drop_area.setStyleSheet(self._drop_ok(pad="15px"))
            self._auto_extract_tproxy_config()
            save_config_paths(self.vpn_config_path, self.v2ray_config_path)
            QMessageBox.information(self, "成功",
                "配置已更新，透明代理参数已自动提取。\n如需应用，请重启 V2Ray。")

    def edit_v2ray_config(self):
        if not os.path.exists(self.v2ray_config_path):
            try:
                os.makedirs(os.path.dirname(self.v2ray_config_path), exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法创建配置目录: {e}")
                return
            V2RayConfigManager(self.v2ray_config_path).save_config()
        try:
            subprocess.Popen(["xdg-open", self.v2ray_config_path])
            QMessageBox.information(self, "提示",
                "配置文件已在外部编辑器中打开。\n编辑完成后请重启 V2Ray 以应用更改。")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法打开编辑器: {e}")

    # ══════════════════════════════════════════
    # 关闭
    # ══════════════════════════════════════════
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
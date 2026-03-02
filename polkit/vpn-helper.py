#!/usr/bin/env python3
"""
VPN Helper Script for Polkit (增强版)
此脚本由 pkexec 以 root 权限调用,负责启动和停止 VPN 服务
以及配置透明代理 (tproxy) 的 iptables 规则

增强功能:
- 优先使用预打包的 geo 文件 (resources 目录)
- 运行时异步检查 geo 文件更新
- 自动检测 V2Ray 版本并使用正确的启动命令
- 完善的错误处理和日志记录
"""
import sys
import subprocess
import os
import signal
import time
import hashlib
import threading

# ============ 最小侵入式调试日志 ============
DEBUG_LOG = "/tmp/vpn-helper-debug.log"

def log_debug(msg):
    """写入调试日志"""
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {msg}\n")
    except:
        pass  # 静默失败,不影响主流程
# ===========================================

# ============ Geo 文件相关常量 ============
GEO_DIR = "/usr/local/share/v2ray"
GEO_MIN_SIZE = 102400  # 100KB，有效 geo 文件的最小大小

# 预打包 geo 文件的可能位置 (按优先级排列)
BUNDLED_GEO_PATHS = [
    # DEB 安装后的位置
    "/usr/local/lib/ov2n/resources",
    # 开发环境: 相对于脚本所在目录
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources"),
    # 开发环境: 相对于当前工作目录
    os.path.join(os.getcwd(), "resources"),
    # /opt 符号链接
    "/opt/ov2n/resources",
]

GEO_FILES_CONFIG = {
    "geoip.dat": [
        "https://github.com/v2fly/geoip/releases/latest/download/geoip.dat",
        "https://cdn.jsdelivr.net/gh/v2fly/geoip@release/geoip.dat"
    ],
    "geosite.dat": [
        "https://github.com/v2fly/domain-list-community/releases/latest/download/dlc.dat",
        "https://cdn.jsdelivr.net/gh/v2fly/domain-list-community@release/dlc.dat"
    ]
}
# ===========================================


def find_xray_binary():
    """查找 xray 或 v2ray 可执行文件"""
    for binary in ['xray', 'v2ray']:
        result = subprocess.run(
            ['which', binary],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return result.stdout.strip()
    return None


def is_geo_file_valid(filepath):
    """
    检查 geo 文件是否存在且有效
    返回: bool
    """
    if not os.path.exists(filepath):
        return False
    try:
        size = os.path.getsize(filepath)
        return size >= GEO_MIN_SIZE
    except Exception:
        return False


def get_file_sha256(filepath):
    """计算文件的 SHA256 哈希值"""
    try:
        sha256 = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception:
        return None


def find_bundled_geo_file(filename):
    """
    在预打包路径中查找 geo 文件
    返回: 文件路径 (str) 或 None
    """
    for base_path in BUNDLED_GEO_PATHS:
        filepath = os.path.join(base_path, filename)
        if is_geo_file_valid(filepath):
            log_debug(f"find_bundled: 在 {filepath} 找到有效的 {filename}")
            return filepath
    return None


def copy_bundled_geo_file(filename, dest_dir):
    """
    从预打包路径复制 geo 文件到目标目录
    返回: (bool, str) (成功/失败, 目标文件路径或错误信息)
    """
    import shutil

    bundled_path = find_bundled_geo_file(filename)
    if not bundled_path:
        return False, f"未找到预打包的 {filename}"

    dest_path = os.path.join(dest_dir, filename)

    try:
        shutil.copy2(bundled_path, dest_path)
        log_debug(f"copy_bundled: 已复制 {bundled_path} -> {dest_path}")
        return True, dest_path
    except Exception as e:
        log_debug(f"copy_bundled: 复制失败 - {e}")
        return False, str(e)


def check_and_prepare_geo_files():
    """
    检查并准备 geo 文件 (优先使用预打包文件)
    
    优先级:
    1. 目标目录已有有效文件 -> 直接使用
    2. 预打包 resources 目录有文件 -> 复制到目标目录
    3. 从网络下载 (仅在前两步都失败时)
    
    返回: (bool, str) (成功/失败, 错误信息)
    """
    log_debug("check_geo: 开始检查 geo 文件 (优先使用预打包文件)")

    # 确保目标目录存在
    try:
        os.makedirs(GEO_DIR, exist_ok=True)
        log_debug(f"check_geo: 目录 {GEO_DIR} 已就绪")
    except Exception as e:
        log_debug(f"check_geo: 创建目录失败 - {e}")
        return False, f"无法创建目录 {GEO_DIR}: {e}"

    missing_files = []
    files_from_bundled = []

    for filename in GEO_FILES_CONFIG.keys():
        dest_path = os.path.join(GEO_DIR, filename)

        # 步骤 1: 检查目标目录是否已有有效文件
        if is_geo_file_valid(dest_path):
            size = os.path.getsize(dest_path)
            log_debug(f"check_geo: {filename} 已存在且有效 ({size} 字节)")
            continue

        # 步骤 2: 尝试从预打包 resources 复制
        log_debug(f"check_geo: {filename} 不存在或无效,尝试从预打包目录复制")
        copied, msg = copy_bundled_geo_file(filename, GEO_DIR)
        if copied:
            size = os.path.getsize(dest_path)
            log_debug(f"check_geo: {filename} 已从预打包目录复制 ({size} 字节)")
            files_from_bundled.append(filename)
            print(f"  ✓ {filename} 已从预打包资源加载", file=sys.stderr)
            continue

        # 步骤 3: 标记为需要下载
        log_debug(f"check_geo: {filename} 预打包也不可用 ({msg}),需要网络下载")
        missing_files.append(filename)

    # 如果所有文件都已就绪 (来自目标目录或预打包)
    if not missing_files:
        log_debug("check_geo: 所有 geo 文件已就绪")
        if files_from_bundled:
            log_debug(f"check_geo: 其中从预打包复制的: {files_from_bundled}")
        create_geo_symlinks(GEO_DIR, GEO_FILES_CONFIG.keys())
        return True, ""

    # 仍有缺失文件,尝试网络下载
    print(f"警告: 检测到缺失的 geo 文件: {', '.join(missing_files)}", file=sys.stderr)
    print("正在尝试从网络下载...", file=sys.stderr)
    log_debug(f"check_geo: 需要从网络下载: {missing_files}")

    download_failed = download_geo_files_from_network(missing_files)

    if download_failed:
        error_msg = f"以下 geo 文件下载失败: {', '.join(download_failed)}\n"
        error_msg += "V2Ray 可能无法正常启动。请手动下载:\n"
        for filename in download_failed:
            error_msg += f"  sudo wget -O {GEO_DIR}/{filename} {GEO_FILES_CONFIG[filename][0]}\n"
        log_debug(f"check_geo: 失败 - {error_msg}")
        return False, error_msg

    log_debug("check_geo: 所有文件下载成功")
    create_geo_symlinks(GEO_DIR, GEO_FILES_CONFIG.keys())
    return True, ""


def download_geo_files_from_network(filenames):
    """
    从网络下载指定的 geo 文件
    返回: 下载失败的文件列表
    """
    import urllib.request

    download_failed = []

    for filename in filenames:
        urls = GEO_FILES_CONFIG[filename]
        filepath = os.path.join(GEO_DIR, filename)
        downloaded = False

        for url in urls:
            try:
                print(f"  下载 {filename}: {url}", file=sys.stderr)
                log_debug(f"download: 尝试从 {url} 下载 {filename}")

                req = urllib.request.Request(
                    url,
                    headers={'User-Agent': 'OV2N-VPN-Helper/1.3.0'}
                )

                with urllib.request.urlopen(req, timeout=30) as response:
                    data = response.read()

                    if len(data) < GEO_MIN_SIZE:
                        log_debug(f"download: {filename} 太小 ({len(data)} 字节)")
                        continue

                    with open(filepath, 'wb') as f:
                        f.write(data)

                    print(f"  ✓ {filename} 下载成功 ({len(data)} 字节)", file=sys.stderr)
                    log_debug(f"download: {filename} 下载成功,大小 {len(data)} 字节")
                    downloaded = True
                    break

            except Exception as e:
                print(f"  ✗ 下载失败: {e}", file=sys.stderr)
                log_debug(f"download: 从 {url} 下载失败 - {e}")
                continue

        if not downloaded:
            download_failed.append(filename)
            log_debug(f"download: {filename} 所有下载源都失败")

    return download_failed


def check_geo_updates_async():
    """
    异步检查 geo 文件是否有更新 (在后台线程中运行)
    通过比较文件大小和 HTTP Content-Length 来判断是否需要更新
    """
    import urllib.request

    log_debug("update_check: 开始异步检查 geo 文件更新")

    for filename, urls in GEO_FILES_CONFIG.items():
        filepath = os.path.join(GEO_DIR, filename)

        if not is_geo_file_valid(filepath):
            log_debug(f"update_check: {filename} 不存在,跳过更新检查")
            continue

        local_size = os.path.getsize(filepath)
        url = urls[0]  # 使用主下载源检查

        try:
            req = urllib.request.Request(
                url,
                method='HEAD',
                headers={'User-Agent': 'OV2N-VPN-Helper/1.3.0'}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                remote_size = int(response.headers.get('Content-Length', 0))

                if remote_size > 0 and abs(remote_size - local_size) > 1024:
                    # 文件大小差异超过 1KB,可能有更新
                    log_debug(
                        f"update_check: {filename} 可能有更新 "
                        f"(本地: {local_size}, 远程: {remote_size})"
                    )
                    # 尝试下载更新
                    _download_update(filename, urls, filepath)
                else:
                    log_debug(f"update_check: {filename} 已是最新 (大小: {local_size})")

        except Exception as e:
            log_debug(f"update_check: 检查 {filename} 更新失败 - {e}")
            # 更新检查失败不影响正常使用


def _download_update(filename, urls, filepath):
    """下载更新的 geo 文件 (替换现有文件)"""
    import urllib.request

    tmp_path = filepath + ".tmp"

    for url in urls:
        try:
            log_debug(f"update_download: 从 {url} 下载 {filename} 更新")

            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'OV2N-VPN-Helper/1.3.0'}
            )

            with urllib.request.urlopen(req, timeout=60) as response:
                data = response.read()

                if len(data) < GEO_MIN_SIZE:
                    continue

                # 写入临时文件
                with open(tmp_path, 'wb') as f:
                    f.write(data)

                # 原子替换
                os.replace(tmp_path, filepath)
                log_debug(f"update_download: {filename} 更新成功 ({len(data)} 字节)")

                # 更新符号链接
                create_geo_symlinks(GEO_DIR, [filename])
                return True

        except Exception as e:
            log_debug(f"update_download: 从 {url} 更新失败 - {e}")
            # 清理临时文件
            try:
                os.unlink(tmp_path)
            except:
                pass
            continue

    log_debug(f"update_download: {filename} 所有更新源都失败")
    return False


def create_geo_symlinks(geo_dir, filenames):
    """创建 geo 文件的符号链接到常见位置"""
    link_dirs = ["/usr/bin", "/usr/local/bin", "/usr/share/v2ray"]

    for link_dir in link_dirs:
        if not os.path.isdir(link_dir):
            continue

        for filename in filenames:
            src = os.path.join(geo_dir, filename)
            dst = os.path.join(link_dir, filename)

            try:
                if os.path.islink(dst) or os.path.exists(dst):
                    os.unlink(dst)
                os.symlink(src, dst)
                log_debug(f"create_symlinks: 创建链接 {dst} -> {src}")
            except Exception as e:
                log_debug(f"create_symlinks: 创建链接失败 {dst} - {e}")


def start_openvpn(config_path):
    """启动 OpenVPN"""
    try:
        log_debug(f"start_openvpn: 配置文件 {config_path}")

        result = subprocess.run(
            ['which', 'openvpn'],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print("错误: openvpn 未安装", file=sys.stderr)
            log_debug("start_openvpn: openvpn 未找到")
            return None

        openvpn_path = result.stdout.strip()
        log_debug(f"start_openvpn: openvpn 路径 {openvpn_path}")

        log_file = open("/tmp/openvpn.log", "w")
        process = subprocess.Popen(
            ['openvpn', '--config', config_path, '--daemon'],
            stdout=log_file,
            stderr=log_file
        )
        log_file.close()

        log_debug(f"start_openvpn: Popen 完成, 初始 PID={process.pid}")

        for i in range(10):
            time.sleep(0.5)
            poll = process.poll()
            if poll is not None:
                log_debug(f"start_openvpn: 初始进程已退出 (daemon fork), poll={poll}")
                break

        search_pattern = f'openvpn.*{os.path.basename(config_path)}'
        log_debug(f"start_openvpn: 查找守护进程 pattern={search_pattern}")

        result = subprocess.run(
            ['pgrep', '-f', search_pattern],
            capture_output=True,
            text=True
        )

        if result.returncode == 0 and result.stdout.strip():
            pid = int(result.stdout.strip().split('\n')[0])
            print(f"OpenVPN PID: {pid}")
            log_debug(f"start_openvpn: ✓ 成功,PID={pid}")
            return pid
        else:
            print("错误: OpenVPN 启动失败", file=sys.stderr)
            log_debug(f"start_openvpn: ✗ pgrep 失败,rc={result.returncode}")
            try:
                with open("/tmp/openvpn.log", "r") as f:
                    log_content = f.read(500)
                if log_content:
                    log_debug(f"start_openvpn: openvpn 日志={log_content}")
                    print(f"OpenVPN 日志: {log_content}", file=sys.stderr)
            except Exception:
                pass
            return None

    except Exception as e:
        print(f"启动 OpenVPN 失败: {e}", file=sys.stderr)
        log_debug(f"start_openvpn: 异常 - {e}")
        import traceback
        log_debug(f"start_openvpn: 堆栈 - {traceback.format_exc()}")
        return None


def start_v2ray(config_path):
    """启动 V2Ray/Xray"""
    try:
        # 【增强】启动前检查 geo 文件 (优先使用预打包文件)
        geo_ok, geo_error = check_and_prepare_geo_files()
        if not geo_ok:
            print(f"警告: geo 文件检查失败", file=sys.stderr)
            print(geo_error, file=sys.stderr)
            log_debug(f"start_v2ray: geo 文件检查失败 - {geo_error}")
            # 不阻止启动,但用户可能会遇到问题

        # 【新增】启动后台线程检查 geo 文件更新
        update_thread = threading.Thread(
            target=check_geo_updates_async,
            daemon=True,
            name="geo-update-checker"
        )
        update_thread.start()
        log_debug("start_v2ray: 已启动 geo 文件更新检查线程")

        # 检查 systemd 服务是否在运行
        log_debug("检查 v2ray.service 状态...")
        systemd_check = subprocess.run(
            ['systemctl', 'is-active', 'v2ray.service'],
            capture_output=True,
            text=True
        )
        if systemd_check.returncode == 0:
            log_debug("警告: v2ray.service 正在运行,尝试停止...")
            print("警告: 检测到 v2ray.service 正在运行,将先停止它", file=sys.stderr)
            subprocess.run(['systemctl', 'stop', 'v2ray.service'], capture_output=True)
            time.sleep(1)
        else:
            log_debug("v2ray.service 未运行")

        # 查找 xray 或 v2ray
        binary = find_xray_binary()
        if not binary:
            print("错误: xray/v2ray 未安装", file=sys.stderr)
            log_debug("start_v2ray: xray/v2ray 未找到")
            return None

        log_debug(f"start_v2ray: 使用 {binary}, 配置文件 {config_path}")

        # 检测版本以确定正确的命令行格式
        version_result = subprocess.run(
            [binary, 'version'],
            capture_output=True,
            text=True
        )

        if 'V2Ray 4' in version_result.stdout or 'V2Ray 3' in version_result.stdout:
            cmd = [binary, '-config', config_path]
            log_debug(f"start_v2ray: 检测到 V2Ray 4.x/3.x,使用旧格式命令")
        else:
            cmd = [binary, 'run', '-c', config_path]
            log_debug(f"start_v2ray: 检测到新版本,使用新格式命令")

        log_debug(f"start_v2ray: 启动命令 {' '.join(cmd)}")

        log_file = open("/tmp/v2ray.log", "w")
        process = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=log_file
        )
        log_file.close()

        initial_pid = process.pid
        log_debug(f"start_v2ray: 进程已启动, 初始 PID={initial_pid}")

        stable = False
        for i in range(10):
            time.sleep(0.5)
            poll = process.poll()
            if poll is not None:
                log_debug(f"start_v2ray: ✗ 进程在第 {i+1} 次检测时退出,退出码={poll}")
                break
            if i >= 1:
                stable = True
                log_debug(f"start_v2ray: 进程稳定运行中 (第 {i+1} 次检测)")
                break

        if not stable:
            print("错误: V2Ray 启动失败", file=sys.stderr)
            try:
                with open("/tmp/v2ray.log", "r") as f:
                    log_content = f.read(1000)
                if log_content:
                    log_debug(f"start_v2ray: v2ray 日志={log_content}")
                    print(f"V2Ray 日志:\n{log_content}", file=sys.stderr)

                    if "geoip.dat" in log_content or "geosite.dat" in log_content:
                        print("\n提示: 这可能是 geo 数据文件问题", file=sys.stderr)
                        print("请手动下载 geo 文件:", file=sys.stderr)
                        print("  sudo wget -O /usr/local/share/v2ray/geoip.dat https://github.com/v2fly/geoip/releases/latest/download/geoip.dat", file=sys.stderr)
                        print("  sudo wget -O /usr/local/share/v2ray/geosite.dat https://github.com/v2fly/domain-list-community/releases/latest/download/dlc.dat", file=sys.stderr)
            except Exception:
                pass
            return None

        if is_process_alive(initial_pid):
            print(f"V2Ray PID: {initial_pid}")
            log_debug(f"start_v2ray: ✓ 成功,PID={initial_pid}")
            return initial_pid
        else:
            print("错误: V2Ray 启动失败", file=sys.stderr)
            log_debug(f"start_v2ray: ✗ initial_pid {initial_pid} 不存在")
            return None

    except Exception as e:
        print(f"启动 V2Ray 失败: {e}", file=sys.stderr)
        log_debug(f"start_v2ray: 异常 - {e}")
        import traceback
        log_debug(f"start_v2ray: 堆栈 - {traceback.format_exc()}")
        return None


def is_process_alive(pid):
    """检查进程是否存在"""
    log_debug(f"is_process_alive({pid}): 开始检查")
    try:
        os.kill(pid, 0)
        log_debug(f"is_process_alive({pid}): 进程存在")
        return True
    except ProcessLookupError as e:
        log_debug(f"is_process_alive({pid}): ProcessLookupError - {e}")
        return False
    except PermissionError as e:
        log_debug(f"is_process_alive({pid}): PermissionError - {e}")
        return True
    except OSError as e:
        log_debug(f"is_process_alive({pid}): OSError - {e}")
        return False


def stop_process(pid):
    """
    停止进程
    如果进程已经不存在 (No such process),视为成功停止
    """
    log_debug(f"stop_process({pid}): 开始停止进程")

    if not is_process_alive(pid):
        print(f"  进程 {pid} 已不存在,无需停止")
        log_debug(f"stop_process({pid}): 进程不存在,返回 True")
        return True

    try:
        log_debug(f"stop_process({pid}): 发送 SIGTERM")
        os.kill(pid, signal.SIGTERM)
        log_debug(f"stop_process({pid}): SIGTERM 发送成功")
    except ProcessLookupError:
        print(f"  进程 {pid} 已退出")
        log_debug(f"stop_process({pid}): ProcessLookupError 在 SIGTERM,返回 True")
        return True
    except OSError as e:
        print(f"  os.kill({pid}, SIGTERM) 失败: {e}, 尝试 kill 命令...")
        log_debug(f"stop_process({pid}): OSError 在 SIGTERM - {e}, 尝试 kill 命令")
        result = subprocess.run(['kill', '-TERM', str(pid)], capture_output=True, text=True)
        log_debug(f"stop_process({pid}): kill -TERM 返回码={result.returncode}, stderr={result.stderr}")

    log_debug(f"stop_process({pid}): 等待进程终止 (最多5秒)")
    for i in range(10):
        if not is_process_alive(pid):
            print(f"  进程 {pid} 已终止")
            log_debug(f"stop_process({pid}): 进程已终止 (耗时 {i*0.5}秒),返回 True")
            return True
        time.sleep(0.5)

    print(f"  进程 {pid} 未响应 SIGTERM,发送 SIGKILL...")
    log_debug(f"stop_process({pid}): SIGTERM 超时,发送 SIGKILL")
    try:
        os.kill(pid, signal.SIGKILL)
        log_debug(f"stop_process({pid}): SIGKILL 发送成功")
    except ProcessLookupError:
        log_debug(f"stop_process({pid}): ProcessLookupError 在 SIGKILL,返回 True")
        return True
    except OSError as e:
        log_debug(f"stop_process({pid}): OSError 在 SIGKILL - {e}, 尝试 kill -9")
        result = subprocess.run(['kill', '-9', str(pid)], capture_output=True, text=True)
        log_debug(f"stop_process({pid}): kill -9 返回码={result.returncode}, stderr={result.stderr}")

    time.sleep(1)
    if not is_process_alive(pid):
        print(f"  进程 {pid} 已强制终止")
        log_debug(f"stop_process({pid}): SIGKILL 成功,返回 True")
        return True

    print(f"  警告: 进程 {pid} 可能仍在运行", file=sys.stderr)
    log_debug(f"stop_process({pid}): 进程仍在运行,返回 False")
    return False


########################################
# TProxy 透明代理相关函数
########################################

def run_cmd(cmd, ignore_error=False):
    """执行 shell 命令"""
    result = subprocess.run(
        cmd, shell=True,
        capture_output=True, text=True
    )
    if result.returncode != 0 and not ignore_error:
        print(f"  命令失败: {cmd}", file=sys.stderr)
        if result.stderr:
            print(f"  错误: {result.stderr.strip()}", file=sys.stderr)
    return result.returncode == 0


def tproxy_clean(v2ray_port, vps_ip, mark, table):
    """清理旧的 tproxy iptables 规则和路由"""
    print("[tproxy] 清理旧规则...")

    run_cmd(f"iptables -t mangle -D OUTPUT -j V2RAY", ignore_error=True)
    run_cmd(f"iptables -t mangle -D PREROUTING -j V2RAY", ignore_error=True)

    run_cmd(f"iptables -t mangle -D PREROUTING -p tcp -m mark --mark {mark} -j TPROXY --on-port {v2ray_port} --tproxy-mark {mark}", ignore_error=True)
    run_cmd(f"iptables -t mangle -D PREROUTING -p udp -m mark --mark {mark} -j TPROXY --on-port {v2ray_port} --tproxy-mark {mark}", ignore_error=True)

    run_cmd("iptables -t mangle -F V2RAY", ignore_error=True)
    run_cmd("iptables -t mangle -X V2RAY", ignore_error=True)

    while True:
        ret = subprocess.run(
            f"ip rule del fwmark {mark} table {table}",
            shell=True, capture_output=True, text=True
        )
        if ret.returncode != 0:
            break

    run_cmd(f"ip route flush table {table}", ignore_error=True)

    print("[tproxy] ✓ 旧规则清理完成")


def tproxy_setup(v2ray_port, vps_ip, mark, table):
    """
    配置 tproxy 透明代理规则
    """
    print(f"[tproxy] 开始配置透明代理...")
    print(f"  V2Ray 端口: {v2ray_port}")
    print(f"  VPS IP: {vps_ip}")
    print(f"  fwmark: {mark}")
    print(f"  路由表: {table}")

    tproxy_clean(v2ray_port, vps_ip, mark, table)

    print("[tproxy] 开启内核转发...")
    run_cmd("sysctl -w net.ipv4.ip_forward=1", ignore_error=True)

    print("[tproxy] 创建策略路由...")
    run_cmd(f"ip rule add fwmark {mark} table {table}", ignore_error=True)
    run_cmd(f"ip route add local 0.0.0.0/0 dev lo table {table}", ignore_error=True)

    print("[tproxy] 创建 iptables mangle 规则...")
    run_cmd("iptables -t mangle -N V2RAY", ignore_error=True)

    local_cidrs = [
        "0.0.0.0/8",
        "127.0.0.0/8",
        "10.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "224.0.0.0/4",
        "240.0.0.0/4",
    ]
    for cidr in local_cidrs:
        run_cmd(f"iptables -t mangle -A V2RAY -d {cidr} -j RETURN")

    run_cmd(f"iptables -t mangle -A V2RAY -d {vps_ip} -j RETURN")
    run_cmd(f"iptables -t mangle -A V2RAY -m mark --mark 255 -j RETURN")

    run_cmd(f"iptables -t mangle -A V2RAY -p tcp -j MARK --set-mark {mark}")
    run_cmd(f"iptables -t mangle -A V2RAY -p udp -j MARK --set-mark {mark}")

    print("[tproxy] 应用 mangle 规则...")
    run_cmd(f"iptables -t mangle -A OUTPUT -j V2RAY")
    run_cmd(f"iptables -t mangle -A PREROUTING -j V2RAY")

    print("[tproxy] 配置 TPROXY 重定向...")
    run_cmd(f"iptables -t mangle -A PREROUTING -m mark --mark {mark} -p tcp -j TPROXY --on-port {v2ray_port} --tproxy-mark {mark}")
    run_cmd(f"iptables -t mangle -A PREROUTING -m mark --mark {mark} -p udp -j TPROXY --on-port {v2ray_port} --tproxy-mark {mark}")

    print("[tproxy] ✓ 透明代理配置完成")
    return True


def main():
    log_debug("=" * 50)
    log_debug(f"脚本启动: {' '.join(sys.argv)}")
    log_debug(f"UID={os.getuid()}, EUID={os.geteuid()}")

    if len(sys.argv) < 2:
        print("用法: vpn-helper.py <start|stop|tproxy-start|tproxy-stop> [参数...]", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]

    if command == "start":
        if len(sys.argv) < 4:
            print("用法: vpn-helper.py start <vpn_config> <v2ray_config>", file=sys.stderr)
            sys.exit(1)

        vpn_config = sys.argv[2]
        v2ray_config = sys.argv[3]

        if not os.path.exists(vpn_config):
            print(f"错误: OpenVPN 配置文件不存在: {vpn_config}", file=sys.stderr)
            sys.exit(1)

        if not os.path.exists(v2ray_config):
            print(f"错误: V2Ray 配置文件不存在: {v2ray_config}", file=sys.stderr)
            sys.exit(1)

        print("正在启动 OpenVPN...")
        openvpn_pid = start_openvpn(vpn_config)

        print("正在启动 V2Ray...")
        v2ray_pid = start_v2ray(v2ray_config)

        if openvpn_pid and v2ray_pid:
            print("启动成功")
            sys.exit(0)
        else:
            print("启动失败", file=sys.stderr)
            if openvpn_pid:
                stop_process(openvpn_pid)
            if v2ray_pid:
                stop_process(v2ray_pid)
            sys.exit(1)

    elif command == "stop":
        log_debug("执行 stop 命令")

        openvpn_pid = None
        v2ray_pid = None

        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--openvpn-pid" and i + 1 < len(sys.argv):
                openvpn_pid = int(sys.argv[i + 1])
                log_debug(f"接收到 openvpn_pid={openvpn_pid}")
                i += 2
            elif sys.argv[i] == "--v2ray-pid" and i + 1 < len(sys.argv):
                v2ray_pid = int(sys.argv[i + 1])
                log_debug(f"接收到 v2ray_pid={v2ray_pid}")
                i += 2
            else:
                log_debug(f"未知参数: {sys.argv[i]}")
                i += 1

        all_ok = True

        if openvpn_pid:
            print(f"正在停止 OpenVPN (PID: {openvpn_pid})...")
            if not stop_process(openvpn_pid):
                log_debug(f"stop_process(openvpn_pid={openvpn_pid}) 返回 False")
                all_ok = False
            else:
                log_debug(f"stop_process(openvpn_pid={openvpn_pid}) 返回 True")

        if v2ray_pid:
            print(f"正在停止 V2Ray (PID: {v2ray_pid})...")
            if not stop_process(v2ray_pid):
                log_debug(f"stop_process(v2ray_pid={v2ray_pid}) 返回 False")
                all_ok = False
            else:
                log_debug(f"stop_process(v2ray_pid={v2ray_pid}) 返回 True")

        log_debug("验证指定 PID 是否已停止...")
        still_running = []

        if openvpn_pid and is_process_alive(openvpn_pid):
            log_debug(f"警告: OpenVPN PID {openvpn_pid} 仍在运行")
            still_running.append(('openvpn', openvpn_pid))

        if v2ray_pid and is_process_alive(v2ray_pid):
            log_debug(f"警告: V2Ray PID {v2ray_pid} 仍在运行")
            still_running.append(('v2ray', v2ray_pid))

        if still_running:
            log_debug(f"✗ 仍有 {len(still_running)} 个进程在运行: {still_running}")
            print(f"警告: 以下进程未能停止:", file=sys.stderr)
            for pname, pid in still_running:
                print(f"  - {pname}: PID {pid}", file=sys.stderr)
            print("停止失败: 部分进程仍在运行", file=sys.stderr)
            log_debug("停止命令失败,退出码 1")
            sys.exit(1)
        else:
            log_debug(f"✓ 所有进程已停止,all_ok={all_ok}")
            print("停止成功")
            log_debug("停止命令成功,退出码 0")
            sys.exit(0)

    elif command == "tproxy-start":
        v2ray_port = 12345
        vps_ip = None
        mark = 1
        table = 100

        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--port" and i + 1 < len(sys.argv):
                v2ray_port = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--vps-ip" and i + 1 < len(sys.argv):
                vps_ip = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--mark" and i + 1 < len(sys.argv):
                mark = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--table" and i + 1 < len(sys.argv):
                table = int(sys.argv[i + 1])
                i += 2
            else:
                i += 1

        if not vps_ip:
            print("错误: 必须指定 --vps-ip 参数", file=sys.stderr)
            sys.exit(1)

        success = tproxy_setup(v2ray_port, vps_ip, mark, table)
        if success:
            print("TPROXY_STATUS: OK")
            sys.exit(0)
        else:
            print("TPROXY_STATUS: FAILED", file=sys.stderr)
            sys.exit(1)

    elif command == "tproxy-stop":
        v2ray_port = 12345
        vps_ip = "0.0.0.0"
        mark = 1
        table = 100

        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--port" and i + 1 < len(sys.argv):
                v2ray_port = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--vps-ip" and i + 1 < len(sys.argv):
                vps_ip = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--mark" and i + 1 < len(sys.argv):
                mark = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--table" and i + 1 < len(sys.argv):
                table = int(sys.argv[i + 1])
                i += 2
            else:
                i += 1

        tproxy_clean(v2ray_port, vps_ip, mark, table)
        print("TPROXY_STATUS: CLEANED")
        sys.exit(0)

    else:
        print(f"未知命令: {command}", file=sys.stderr)
        print("可用命令: start, stop, tproxy-start, tproxy-stop", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_debug("脚本被 Ctrl+C 中断")
        print("\n脚本被中断", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        log_debug(f"未捕获的异常: {e}")
        import traceback
        log_debug(f"异常堆栈:\n{traceback.format_exc()}")
        print(f"致命错误: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        log_debug("脚本执行结束")
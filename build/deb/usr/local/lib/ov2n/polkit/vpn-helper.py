#!/usr/bin/env python3
"""
VPN Helper Script for Polkit
此脚本由 pkexec 以 root 权限调用,负责启动和停止 VPN 服务
以及配置透明代理 (tproxy) 的 iptables 规则
"""
import sys
import subprocess
import os
import signal
import time

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

def start_openvpn(config_path):
    """启动 OpenVPN"""
    try:
        log_debug(f"start_openvpn: 配置文件 {config_path}")

        # 检查 openvpn 是否存在
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

        # 启动 OpenVPN (后台运行, 输出重定向到日志文件)
        log_file = open("/tmp/openvpn.log", "w")
        process = subprocess.Popen(
            ['openvpn', '--config', config_path, '--daemon'],
            stdout=log_file,
            stderr=log_file
        )
        log_file.close()

        log_debug(f"start_openvpn: Popen 完成, 初始 PID={process.pid}")

        # 轮询等待进程稳定 (最多 5 秒)
        for i in range(10):
            time.sleep(0.5)
            poll = process.poll()
            if poll is not None:
                # openvpn --daemon 会 fork 后父进程退出,这是正常的
                log_debug(f"start_openvpn: 初始进程已退出 (daemon fork), poll={poll}")
                break

        # 查找 OpenVPN 真实守护进程 PID (daemon fork 后 PID 会变化)
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
            # 读取日志输出辅助诊断
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

        # 启动 V2Ray/Xray
        # 【修复】输出重定向到日志文件，避免 PIPE 缓冲区填满导致进程阻塞
        log_file = open("/tmp/v2ray.log", "w")
        process = subprocess.Popen(
            [binary, 'run', '-config', config_path],
            stdout=log_file,
            stderr=log_file
        )
        log_file.close()

        initial_pid = process.pid
        log_debug(f"start_v2ray: 进程已启动, 初始 PID={initial_pid}")

        # 【修复】轮询等待，替代硬编码 sleep(2)
        # xray/v2ray 不会 fork，initial_pid 就是真实 PID
        # 只需确认进程在短暂启动期后仍然存活
        stable = False
        for i in range(10):  # 最多等 5 秒
            time.sleep(0.5)
            poll = process.poll()
            if poll is not None:
                # 进程已退出，启动失败
                log_debug(f"start_v2ray: ✗ 进程在第 {i+1} 次检测时退出，退出码={poll}")
                break
            # poll() 返回 None 表示进程仍在运行
            if i >= 1:  # 至少存活 1 秒才认为稳定
                stable = True
                log_debug(f"start_v2ray: 进程稳定运行中 (第 {i+1} 次检测)")
                break

        if not stable:
            # 进程已退出，读取日志辅助诊断
            print("错误: V2Ray 启动失败", file=sys.stderr)
            try:
                with open("/tmp/v2ray.log", "r") as f:
                    log_content = f.read(1000)
                if log_content:
                    log_debug(f"start_v2ray: v2ray 日志={log_content}")
                    print(f"V2Ray 日志:\n{log_content}", file=sys.stderr)
            except Exception:
                pass
            return None

        # 【修复】直接使用 initial_pid 作为权威 PID
        # xray/v2ray 不会 fork daemon，initial_pid 即为真实运行 PID
        # 不再依赖 pgrep（避免搜索模式歧义和自身误匹配）
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
        return True  # 进程存在但无权限
    except OSError as e:
        log_debug(f"is_process_alive({pid}): OSError - {e}")
        return False

def stop_process(pid):
    """
    停止进程
    如果进程已经不存在 (No such process),视为成功停止
    """
    log_debug(f"stop_process({pid}): 开始停止进程")

    # 先检查进程是否存在
    if not is_process_alive(pid):
        print(f"  进程 {pid} 已不存在,无需停止")
        log_debug(f"stop_process({pid}): 进程不存在,返回 True")
        return True

    try:
        # 尝试 SIGTERM 优雅终止
        log_debug(f"stop_process({pid}): 发送 SIGTERM")
        os.kill(pid, signal.SIGTERM)
        log_debug(f"stop_process({pid}): SIGTERM 发送成功")
    except ProcessLookupError:
        # 进程在发送信号前已退出
        print(f"  进程 {pid} 已退出")
        log_debug(f"stop_process({pid}): ProcessLookupError 在 SIGTERM,返回 True")
        return True
    except OSError as e:
        # 其他 OS 错误 (如权限不足),尝试 kill 命令备用方案
        print(f"  os.kill({pid}, SIGTERM) 失败: {e}, 尝试 kill 命令...")
        log_debug(f"stop_process({pid}): OSError 在 SIGTERM - {e}, 尝试 kill 命令")
        result = subprocess.run(['kill', '-TERM', str(pid)], capture_output=True, text=True)
        log_debug(f"stop_process({pid}): kill -TERM 返回码={result.returncode}, stderr={result.stderr}")

    # 等待进程终止 (最多 5 秒)
    log_debug(f"stop_process({pid}): 等待进程终止 (最多5秒)")
    for i in range(10):
        if not is_process_alive(pid):
            print(f"  进程 {pid} 已终止")
            log_debug(f"stop_process({pid}): 进程已终止 (耗时 {i*0.5}秒),返回 True")
            return True
        time.sleep(0.5)

    # 进程仍在运行,使用 SIGKILL 强制终止
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

    # 再等待一下
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

    # 清理 iptables mangle 表中的 V2RAY 链
    # 先从 OUTPUT 和 PREROUTING 中移除引用
    run_cmd(f"iptables -t mangle -D OUTPUT -j V2RAY", ignore_error=True)
    run_cmd(f"iptables -t mangle -D PREROUTING -j V2RAY", ignore_error=True)

    # 清理 TPROXY 规则 (在 PREROUTING 中直接添加的)
    run_cmd(f"iptables -t mangle -D PREROUTING -p tcp -m mark --mark {mark} -j TPROXY --on-port {v2ray_port} --tproxy-mark {mark}", ignore_error=True)
    run_cmd(f"iptables -t mangle -D PREROUTING -p udp -m mark --mark {mark} -j TPROXY --on-port {v2ray_port} --tproxy-mark {mark}", ignore_error=True)

    # 清空并删除 V2RAY 链
    run_cmd("iptables -t mangle -F V2RAY", ignore_error=True)
    run_cmd("iptables -t mangle -X V2RAY", ignore_error=True)

    # 清理路由规则 (循环删除所有匹配的)
    while True:
        ret = subprocess.run(
            f"ip rule del fwmark {mark} table {table}",
            shell=True, capture_output=True, text=True
        )
        if ret.returncode != 0:
            break

    # 清理路由表
    run_cmd(f"ip route flush table {table}", ignore_error=True)

    print("[tproxy] ✓ 旧规则清理完成")

def tproxy_setup(v2ray_port, vps_ip, mark, table):
    """
    配置 tproxy 透明代理规则

    Args:
        v2ray_port: V2Ray TPROXY 监听端口
        vps_ip: VPS 服务器 IP (需要排除,防止代理自身流量)
        mark: fwmark 值
        table: 路由表编号
    """
    print(f"[tproxy] 开始配置透明代理...")
    print(f"  V2Ray 端口: {v2ray_port}")
    print(f"  VPS IP: {vps_ip}")
    print(f"  fwmark: {mark}")
    print(f"  路由表: {table}")

    # [1] 先清理旧规则 (幂等性)
    tproxy_clean(v2ray_port, vps_ip, mark, table)

    # [2] 开启内核转发
    print("[tproxy] 开启内核转发...")
    run_cmd("sysctl -w net.ipv4.ip_forward=1", ignore_error=True)

    # [3] 创建策略路由
    print("[tproxy] 创建策略路由...")
    run_cmd(f"ip rule add fwmark {mark} table {table}", ignore_error=True)
    run_cmd(f"ip route add local 0.0.0.0/0 dev lo table {table}", ignore_error=True)

    # [4] 创建 mangle V2RAY 链
    print("[tproxy] 创建 iptables mangle 规则...")
    run_cmd("iptables -t mangle -N V2RAY", ignore_error=True)

    # 排除本地/私有地址
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

    # 排除 VPS IP (防止代理到 VPS 的流量被再次代理,形成循环)
    run_cmd(f"iptables -t mangle -A V2RAY -d {vps_ip} -j RETURN")

    # 排除 V2Ray 自己发出的流量 (mark 255 防止循环)
    run_cmd(f"iptables -t mangle -A V2RAY -m mark --mark 255 -j RETURN")

    # 标记需要代理的流量
    run_cmd(f"iptables -t mangle -A V2RAY -p tcp -j MARK --set-mark {mark}")
    run_cmd(f"iptables -t mangle -A V2RAY -p udp -j MARK --set-mark {mark}")

    # [5] 应用 V2RAY 链到 OUTPUT 和 PREROUTING
    print("[tproxy] 应用 mangle 规则...")
    run_cmd(f"iptables -t mangle -A OUTPUT -j V2RAY")
    run_cmd(f"iptables -t mangle -A PREROUTING -j V2RAY")

    # [6] 配置 TPROXY 重定向
    print("[tproxy] 配置 TPROXY 重定向...")
    run_cmd(f"iptables -t mangle -A PREROUTING -m mark --mark {mark} -p tcp -j TPROXY --on-port {v2ray_port} --tproxy-mark {mark}")
    run_cmd(f"iptables -t mangle -A PREROUTING -m mark --mark {mark} -p udp -j TPROXY --on-port {v2ray_port} --tproxy-mark {mark}")

    print("[tproxy] ✓ 透明代理配置完成")
    return True


def main():
    log_debug("="*50)
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

        # 验证配置文件
        if not os.path.exists(vpn_config):
            print(f"错误: OpenVPN 配置文件不存在: {vpn_config}", file=sys.stderr)
            sys.exit(1)

        if not os.path.exists(v2ray_config):
            print(f"错误: V2Ray 配置文件不存在: {v2ray_config}", file=sys.stderr)
            sys.exit(1)

        # 启动服务
        print("正在启动 OpenVPN...")
        openvpn_pid = start_openvpn(vpn_config)

        print("正在启动 V2Ray...")
        v2ray_pid = start_v2ray(v2ray_config)

        if openvpn_pid and v2ray_pid:
            print("启动成功")
            sys.exit(0)
        else:
            print("启动失败", file=sys.stderr)
            # 清理已启动的进程
            if openvpn_pid:
                stop_process(openvpn_pid)
            if v2ray_pid:
                stop_process(v2ray_pid)
            sys.exit(1)

    elif command == "stop":
        log_debug("执行 stop 命令")

        # 解析 PID 参数
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

        # 停止进程 (即使某个失败也继续停止另一个)
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

        # 检查指定的 PID 是否还存在
        log_debug("验证指定 PID 是否已停止...")
        still_running = []

        if openvpn_pid and is_process_alive(openvpn_pid):
            log_debug(f"警告: OpenVPN PID {openvpn_pid} 仍在运行")
            still_running.append(('openvpn', openvpn_pid))

        if v2ray_pid and is_process_alive(v2ray_pid):
            log_debug(f"警告: V2Ray PID {v2ray_pid} 仍在运行")
            still_running.append(('v2ray', v2ray_pid))

        # 最终判断
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
        # 用法: vpn-helper.py tproxy-start --port PORT --vps-ip IP [--mark MARK] [--table TABLE]
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
        # 用法: vpn-helper.py tproxy-stop [--port PORT] [--vps-ip IP] [--mark MARK] [--table TABLE]
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

        # 同时关闭内核转发 (可选,如果用户不需要其他转发)
        # run_cmd("sysctl -w net.ipv4.ip_forward=0", ignore_error=True)

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
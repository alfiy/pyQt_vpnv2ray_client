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
        # 检查 openvpn 是否存在
        result = subprocess.run(
            ['which', 'openvpn'],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print("错误: openvpn 未安装", file=sys.stderr)
            return None
        
        # 启动 OpenVPN (后台运行)
        process = subprocess.Popen(
            ['openvpn', '--config', config_path, '--daemon'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # 等待进程启动
        time.sleep(2)
        
        # 查找 OpenVPN 进程 PID
        result = subprocess.run(
            ['pgrep', '-f', f'openvpn.*{os.path.basename(config_path)}'],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0 and result.stdout.strip():
            pid = int(result.stdout.strip().split('\n')[0])
            print(f"OpenVPN PID: {pid}")
            return pid
        else:
            print("错误: OpenVPN 启动失败", file=sys.stderr)
            return None
            
    except Exception as e:
        print(f"启动 OpenVPN 失败: {e}", file=sys.stderr)
        return None

def start_v2ray(config_path):
    """启动 V2Ray/Xray"""
    try:
        # 查找 xray 或 v2ray
        binary = find_xray_binary()
        if not binary:
            print("错误: xray/v2ray 未安装", file=sys.stderr)
            return None
        
        # 启动 V2Ray/Xray (后台运行)
        process = subprocess.Popen(
            [binary, 'run', '-config', config_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # 等待进程启动
        time.sleep(2)
        
        # 验证进程是否运行
        if process.poll() is None:
            print(f"V2Ray PID: {process.pid}")
            return process.pid
        else:
            print("错误: V2Ray 启动失败", file=sys.stderr)
            return None
            
    except Exception as e:
        print(f"启动 V2Ray 失败: {e}", file=sys.stderr)
        return None

def stop_process(pid):
    """停止进程"""
    try:
        os.kill(pid, signal.SIGTERM)
        
        # 等待进程终止
        for _ in range(10):
            try:
                os.kill(pid, 0)  # 检查进程是否存在
                time.sleep(0.5)
            except OSError:
                return True  # 进程已终止
        
        # 如果进程仍在运行,使用 SIGKILL
        try:
            os.kill(pid, signal.SIGKILL)
            return True
        except OSError:
            return True
            
    except Exception as e:
        print(f"停止进程 {pid} 失败: {e}", file=sys.stderr)
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
        # 解析 PID 参数
        openvpn_pid = None
        v2ray_pid = None
        
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--openvpn-pid" and i + 1 < len(sys.argv):
                openvpn_pid = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--v2ray-pid" and i + 1 < len(sys.argv):
                v2ray_pid = int(sys.argv[i + 1])
                i += 2
            else:
                i += 1
        
        # 停止进程
        success = True
        if openvpn_pid:
            print(f"正在停止 OpenVPN (PID: {openvpn_pid})...")
            if not stop_process(openvpn_pid):
                success = False
        
        if v2ray_pid:
            print(f"正在停止 V2Ray (PID: {v2ray_pid})...")
            if not stop_process(v2ray_pid):
                success = False
        
        if success:
            print("停止成功")
            sys.exit(0)
        else:
            print("停止失败", file=sys.stderr)
            sys.exit(1)

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
    main()
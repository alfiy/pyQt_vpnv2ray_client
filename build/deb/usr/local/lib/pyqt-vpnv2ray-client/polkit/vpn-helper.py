#!/usr/bin/env python3
"""
VPN Helper Script for Polkit
此脚本由 pkexec 以 root 权限调用,负责启动和停止 VPN 服务
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

def main():
    if len(sys.argv) < 2:
        print("用法: vpn-helper.py <start|stop> [参数...]", file=sys.stderr)
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
    
    else:
        print(f"未知命令: {command}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
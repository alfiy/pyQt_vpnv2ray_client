"""
Polkit 集成模块
通过 pkexec 执行需要 root 权限的操作
"""
import subprocess
import os
import sys

class PolkitHelper:
    """Polkit 权限提升辅助类"""
    
    # Helper 脚本路径
    HELPER_SCRIPT = "/usr/local/bin/vpn-helper.py"
    
    @staticmethod
    def check_polkit_available():
        """检查 polkit 是否可用"""
        try:
            result = subprocess.run(
                ["which", "pkexec"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            print(f"检查 polkit 失败: {e}")
            return False
    
    @staticmethod
    def check_helper_installed():
        """检查 helper 脚本是否已安装"""
        return os.path.exists(PolkitHelper.HELPER_SCRIPT) and \
               os.access(PolkitHelper.HELPER_SCRIPT, os.X_OK)
    
    @staticmethod
    def start_vpn(vpn_config_path, v2ray_config_path):
        """
        使用 polkit 启动 VPN 和 V2Ray
        
        Args:
            vpn_config_path: OpenVPN 配置文件路径
            v2ray_config_path: V2Ray 配置文件路径
            
        Returns:
            tuple: (success: bool, message: str, pids: dict)
        """
        # 检查 polkit
        if not PolkitHelper.check_polkit_available():
            return False, "系统未安装 pkexec (polkit),无法执行权限提升操作", {}
        
        # 检查 helper 脚本
        if not PolkitHelper.check_helper_installed():
            return False, f"Helper 脚本未安装或无执行权限:\n{PolkitHelper.HELPER_SCRIPT}\n\n请参考 README.md 完成安装", {}
        
        # 验证配置文件
        if not os.path.exists(vpn_config_path):
            return False, f"OpenVPN 配置文件不存在: {vpn_config_path}", {}
        
        if not os.path.exists(v2ray_config_path):
            return False, f"V2Ray 配置文件不存在: {v2ray_config_path}", {}
        
        try:
            # 使用 pkexec 调用 helper 脚本
            # pkexec 会自动弹出密码输入对话框
            cmd = [
                "pkexec",
                PolkitHelper.HELPER_SCRIPT,
                "start",
                vpn_config_path,
                v2ray_config_path
            ]
            
            print(f"执行命令: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60  # 给用户足够时间输入密码
            )
            
            if result.returncode == 0:
                # 解析输出获取 PID
                pids = {}
                for line in result.stdout.split('\n'):
                    if 'OpenVPN PID:' in line:
                        pids['openvpn'] = int(line.split(':')[1].strip())
                    elif 'V2Ray PID:' in line:
                        pids['v2ray'] = int(line.split(':')[1].strip())
                
                return True, "VPN 启动成功", pids
            else:
                error_msg = result.stderr.strip() if result.stderr else "未知错误"
                
                # 处理常见错误
                if "dismissed" in error_msg.lower() or "cancelled" in error_msg.lower():
                    return False, "用户取消了权限授权", {}
                elif "authentication" in error_msg.lower():
                    return False, "密码验证失败,请重试", {}
                else:
                    return False, f"启动失败:\n{error_msg}", {}
                    
        except subprocess.TimeoutExpired:
            return False, "操作超时,请重试", {}
        except Exception as e:
            return False, f"执行失败: {str(e)}", {}
    
    @staticmethod
    def stop_vpn(pids):
        """
        停止 VPN 进程
        
        Args:
            pids: 进程 ID 字典 {'openvpn': pid, 'v2ray': pid}
            
        Returns:
            tuple: (success: bool, message: str)
        """
        if not pids:
            return True, "没有运行中的进程"
        
        try:
            cmd = [
                "pkexec",
                PolkitHelper.HELPER_SCRIPT,
                "stop"
            ]
            
            # 添加 PID 参数
            if 'openvpn' in pids:
                cmd.extend(["--openvpn-pid", str(pids['openvpn'])])
            if 'v2ray' in pids:
                cmd.extend(["--v2ray-pid", str(pids['v2ray'])])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return True, "VPN 已停止"
            else:
                return False, f"停止失败: {result.stderr}"
                
        except Exception as e:
            return False, f"停止失败: {str(e)}"

    @staticmethod
    def start_tproxy(v2ray_port, vps_ip, mark=1, table=100):
        """
        使用 polkit 启动 tproxy 透明代理规则
        
        Args:
            v2ray_port: V2Ray TPROXY 监听端口
            vps_ip: VPS 服务器 IP
            mark: fwmark 值 (默认 1)
            table: 路由表编号 (默认 100)
            
        Returns:
            tuple: (success: bool, message: str)
        """
        if not PolkitHelper.check_polkit_available():
            return False, "系统未安装 pkexec (polkit)"
        
        if not PolkitHelper.check_helper_installed():
            return False, f"Helper 脚本未安装: {PolkitHelper.HELPER_SCRIPT}"
        
        try:
            cmd = [
                "pkexec",
                PolkitHelper.HELPER_SCRIPT,
                "tproxy-start",
                "--port", str(v2ray_port),
                "--vps-ip", str(vps_ip),
                "--mark", str(mark),
                "--table", str(table),
            ]
            
            print(f"执行 tproxy-start 命令: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                print(f"tproxy stdout: {result.stdout}")
                return True, "透明代理规则已配置"
            else:
                error_msg = result.stderr.strip() if result.stderr else "未知错误"
                if "dismissed" in error_msg.lower() or "cancelled" in error_msg.lower():
                    return False, "用户取消了权限授权"
                return False, f"配置透明代理失败:\n{error_msg}"
                
        except subprocess.TimeoutExpired:
            return False, "操作超时"
        except Exception as e:
            return False, f"配置透明代理失败: {str(e)}"

    @staticmethod
    def stop_tproxy(v2ray_port=12345, vps_ip="0.0.0.0", mark=1, table=100):
        """
        使用 polkit 清理 tproxy 透明代理规则
        
        Args:
            v2ray_port: V2Ray TPROXY 监听端口
            vps_ip: VPS 服务器 IP
            mark: fwmark 值
            table: 路由表编号
            
        Returns:
            tuple: (success: bool, message: str)
        """
        if not PolkitHelper.check_polkit_available():
            return False, "系统未安装 pkexec (polkit)"
        
        if not PolkitHelper.check_helper_installed():
            return False, f"Helper 脚本未安装: {PolkitHelper.HELPER_SCRIPT}"
        
        try:
            cmd = [
                "pkexec",
                PolkitHelper.HELPER_SCRIPT,
                "tproxy-stop",
                "--port", str(v2ray_port),
                "--vps-ip", str(vps_ip),
                "--mark", str(mark),
                "--table", str(table),
            ]
            
            print(f"执行 tproxy-stop 命令: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return True, "透明代理规则已清理"
            else:
                error_msg = result.stderr.strip() if result.stderr else "未知错误"
                if "dismissed" in error_msg.lower() or "cancelled" in error_msg.lower():
                    return False, "用户取消了权限授权"
                return False, f"清理透明代理失败:\n{error_msg}"
                
        except subprocess.TimeoutExpired:
            return False, "操作超时"
        except Exception as e:
            return False, f"清理透明代理失败: {str(e)}"
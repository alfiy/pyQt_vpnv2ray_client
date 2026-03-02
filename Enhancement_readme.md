# OV2N 项目增强 - 完整指南

本文档提供了 OV2N 项目的完整增强方案,解决 V2Ray geo 文件缺失问题。

## 📋 目录

1. [问题分析](#问题分析)
2. [解决方案](#解决方案)
3. [文件说明](#文件说明)
4. [使用方法](#使用方法)
5. [故障排查](#故障排查)

---

## 🔍 问题分析

### 原始问题

通过 `apt install ./ov2n_1.2.6_all.deb` 安装时:
- ✅ 能自动安装 V2Ray (如果未安装)
- ❌ **不会自动安装 geoip.dat 和 geosite.dat**
- ❌ 导致 V2Ray 启动失败,报错:
  ```
  failed to open file: geoip.dat > open /usr/bin/geoip.dat: no such file or directory
  failed to open file: geosite.dat > open /usr/bin/geosite.dat: no such file or directory
  ```

### 根本原因

V2Ray 官方安装脚本默认不包含 geo 数据文件,需要单独下载。

---

## ✅ 解决方案

### 方案概述

提供两层保护机制:

1. **安装时自动下载** (build.sh 的 postinst 脚本)
   - 在 deb 包安装后自动下载 geo 文件
   - 支持多个下载源,提高成功率
   
2. **运行时自动检查** (vpn-helper.py)
   - V2Ray 启动前检查 geo 文件
   - 如果缺失,尝试自动下载
   - 下载失败时提供清晰的错误提示

---

## 📁 文件说明

### 1. `build-enhanced.sh` (增强版构建脚本)

**新增功能:**
- ✅ 在 postinst 中自动检查并安装 V2Ray
- ✅ 自动下载 geoip.dat 和 geosite.dat
- ✅ 支持 3 个下载源:
  - GitHub 官方源
  - ghproxy 镜像
  - jsDelivr CDN
- ✅ 创建符号链接到多个常见路径
- ✅ 完善的错误处理和日志输出

**关键改进:**

```bash
# postinst 脚本中的 geo 文件下载逻辑
download_geo_file() {
    local filename=$1
    local filepath="$GEO_DIR/$filename"
    shift
    local urls=("$@")
    
    # 检查文件是否已存在且有效 (至少 100KB)
    if [ -f "$filepath" ]; then
        local size=$(stat -c%s "$filepath" 2>/dev/null || echo "0")
        if [ "$size" -gt 102400 ]; then
            log_info "$filename already exists"
            return 0
        fi
    fi
    
    # 尝试从多个源下载
    for url in "${urls[@]}"; do
        if wget --timeout=30 --tries=2 -q -O "$filepath" "$url" 2>/dev/null; then
            if [ "$(stat -c%s "$filepath")" -gt 102400 ]; then
                log_info "$filename downloaded successfully"
                return 0
            fi
        fi
    done
    
    return 1
}
```

### 2. `vpn-helper-enhanced.py` (增强版帮助脚本)

**新增功能:**
- ✅ `check_and_download_geo_files()` 函数
  - 在 V2Ray 启动前自动检查
  - 支持多源下载
  - 验证文件大小 (至少 100KB)
  
- ✅ 自动检测 V2Ray 版本
  - V2Ray 4.x: 使用 `-config`
  - V2Ray 5.x/Xray: 使用 `run -c`
  
- ✅ 增强的错误提示
  - 识别 geo 文件相关错误
  - 提供具体的解决命令

**关键代码:**

```python
def start_v2ray(config_path):
    """启动 V2Ray/Xray"""
    try:
        # 【新增】启动前检查 geo 文件
        geo_ok, geo_error = check_and_download_geo_files()
        if not geo_ok:
            print(f"警告: geo 文件检查失败", file=sys.stderr)
            print(geo_error, file=sys.stderr)
        
        # 【增强】检测版本以确定正确的命令行格式
        version_result = subprocess.run([binary, 'version'], ...)
        
        if 'V2Ray 4' in version_result.stdout:
            cmd = [binary, '-config', config_path]  # 旧版本
        else:
            cmd = [binary, 'run', '-c', config_path]  # 新版本
        
        # ... 后续启动逻辑
```

---

## 🚀 使用方法

### 替换原有文件

1. **替换 build.sh**
   ```bash
   mv build.sh build.sh.backup
   cp build-enhanced.sh build.sh
   chmod +x build.sh
   ```

2. **替换 vpn-helper.py** (在 polkit 目录中)
   ```bash
   cp vpn-helper-enhanced.py polkit/vpn-helper.py
   chmod +x polkit/vpn-helper.py
   ```

### 构建新的 deb 包

```bash
# 清理旧的构建
./build.sh clean

# 构建新包
./build.sh

# 或者指定版本
./build.sh --version 1.2.7
```

### 安装测试

```bash
# 在干净的测试环境中安装
sudo apt install ./dist/ov2n_1.2.7_all.deb

# 观察安装日志
# 应该看到:
#   ✓ Checking V2Ray/Xray installation...
#   ✓ Checking V2Ray geo data files...
#   ✓ geoip.dat downloaded successfully
#   ✓ geosite.dat downloaded successfully
```

### 验证安装

```bash
# 检查 geo 文件
ls -lh /usr/local/share/v2ray/
# 应该看到:
# geoip.dat (几MB)
# geosite.dat (几MB)

# 检查符号链接
ls -lh /usr/bin/geo*.dat
# 应该看到链接到 /usr/local/share/v2ray/

# 测试 V2Ray 启动
v2ray -config /path/to/your/config.json
# 应该正常启动,不报 geo 文件错误
```

---

## 🔧 故障排查

### 问题 1: geo 文件下载失败

**症状:**
```
⚠ Failed to download geoip.dat from all sources
```

**解决方案:**
```bash
# 手动下载 (使用任意一个源)
sudo wget -O /usr/local/share/v2ray/geoip.dat \
  https://github.com/v2fly/geoip/releases/latest/download/geoip.dat

sudo wget -O /usr/local/share/v2ray/geosite.dat \
  https://github.com/v2fly/domain-list-community/releases/latest/download/dlc.dat

# 创建符号链接
sudo ln -sf /usr/local/share/v2ray/geoip.dat /usr/bin/geoip.dat
sudo ln -sf /usr/local/share/v2ray/geosite.dat /usr/bin/geosite.dat
```

### 问题 2: V2Ray 仍然报错找不到 geo 文件

**可能原因:** V2Ray 在其他路径查找文件

**解决方案:**
```bash
# 查看 V2Ray 实际查找的路径
strace v2ray -config config.json 2>&1 | grep geoip

# 创建额外的符号链接
sudo ln -sf /usr/local/share/v2ray/geoip.dat /usr/share/v2ray/geoip.dat
sudo ln -sf /usr/local/share/v2ray/geosite.dat /usr/share/v2ray/geosite.dat
```

### 问题 3: V2Ray 版本不匹配

**症状:**
```
V2Ray 4.34.0 报错: unknown command: run
```

**解决方案:**

增强版 `vpn-helper.py` 已自动处理版本差异:
- V2Ray 4.x: `v2ray -config config.json`
- V2Ray 5.x/Xray: `v2ray run -c config.json`

如果仍有问题,查看调试日志:
```bash
cat /tmp/vpn-helper-debug.log
```

### 问题 4: 安装时网络问题

**症状:**
```
Failed to download V2Ray installer
```

**解决方案:**
```bash
# 方案 A: 使用代理安装 V2Ray
export http_proxy=http://your-proxy:port
export https_proxy=http://your-proxy:port
sudo -E bash <(curl -L https://raw.githubusercontent.com/v2fly/fhs-install-v2ray/master/install-release.sh)

# 方案 B: 手动下载 V2Ray
wget https://github.com/v2fly/v2ray-core/releases/latest/download/v2ray-linux-64.zip
unzip v2ray-linux-64.zip
sudo mv v2ray /usr/local/bin/
sudo chmod +x /usr/local/bin/v2ray
```

---

## 📊 安装流程图

```
用户执行: sudo apt install ./ov2n_1.2.7_all.deb
    │
    ↓
[dpkg 安装文件]
    │
    ↓
[执行 postinst 脚本]
    │
    ├─→ [检查 V2Ray] ─→ 未安装? ─→ [自动安装 V2Ray]
    │                    │
    │                    ↓ 已安装
    ├─→ [检查 geoip.dat] ─→ 缺失? ─→ [从 3 个源下载]
    │                       │
    │                       ↓ 已存在
    ├─→ [检查 geosite.dat] ─→ 缺失? ─→ [从 3 个源下载]
    │                        │
    │                        ↓ 已存在
    └─→ [创建符号链接] ─→ /usr/bin/
                         ─→ /usr/local/bin/
                         ─→ /usr/share/v2ray/
    ↓
[安装完成]

用户启动 VPN:
    │
    ↓
[vpn-helper.py start]
    │
    ├─→ [启动 OpenVPN]
    │
    └─→ [启动 V2Ray]
        │
        ├─→ [check_and_download_geo_files()]
        │   │
        │   ├─→ 检查 /usr/local/share/v2ray/geoip.dat
        │   ├─→ 检查 /usr/local/share/v2ray/geosite.dat
        │   │
        │   └─→ 缺失? ─→ [尝试自动下载] ─→ 失败? ─→ [显示手动命令]
        │
        └─→ [自动检测版本并启动]
            │
            ├─→ V2Ray 4.x: v2ray -config config.json
            └─→ V2Ray 5.x: v2ray run -c config.json
```

---

## 📝 版本历史

### v1.2.7 (增强版)
- ✅ 新增: postinst 自动下载 geo 文件
- ✅ 新增: vpn-helper 运行时检查 geo 文件
- ✅ 新增: 自动检测 V2Ray 版本
- ✅ 改进: 支持多个下载源
- ✅ 改进: 更详细的错误提示

### v1.2.6 (原始版本)
- ❌ 问题: 不自动处理 geo 文件
- ❌ 问题: V2Ray 版本兼容性问题

---

## 🎯 最佳实践

### 1. 构建前检查

```bash
# 确保所有源文件存在
ls -l main.py requirements.txt polkit/

# 确保 vpn-helper.py 使用增强版
grep "check_and_download_geo_files" polkit/vpn-helper.py
```

### 2. 测试环境

建议在虚拟机或 Docker 容器中测试:

```bash
# 使用 Docker 测试
docker run -it ubuntu:22.04 bash
apt update && apt install -y wget
wget http://your-server/ov2n_1.2.7_all.deb
apt install ./ov2n_1.2.7_all.deb
```

### 3. 日志分析

安装时查看详细日志:

```bash
# 安装日志
cat /tmp/v2ray-install.log

# 运行时日志
cat /tmp/vpn-helper-debug.log
cat /tmp/v2ray.log
```

---

## 🆘 获取帮助

如果遇到问题:

1. 查看调试日志: `/tmp/vpn-helper-debug.log`
2. 检查 geo 文件: `ls -lh /usr/local/share/v2ray/`
3. 验证 V2Ray: `v2ray version`
4. 手动测试: `v2ray -config /path/to/config.json`

---

## 📄 许可证

MIT License - 随意使用和修改

---

## 🙏 致谢

感谢 V2Ray/Xray 项目和社区的支持。

---

**最后更新:** 2026-03-02
**作者:** Alfiy
**项目:** https://github.com/alfiy/pyQt_vpnv2ray_client
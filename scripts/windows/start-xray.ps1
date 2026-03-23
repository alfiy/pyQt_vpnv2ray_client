# ov2n - Xray TUN 启动脚本 (Windows)
# 编码: UTF-8 with BOM
# 需要管理员权限运行
#
# 用法:
#   .\start-xray.ps1                          # 自动查找 config.json
#   .\start-xray.ps1 -ConfigPath "C:\path\to\config.json"  # 指定配置文件

param(
    [string]$ConfigPath = ""
)

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "error: 请以管理员身份运行"; exit 1
}

$dir     = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = (Resolve-Path "$dir\..\..").Path
$xrayDir = Join-Path $appRoot "resources\xray"

Set-Location $xrayDir

# ── 查找 config.json ────────────────────────────────────────
# 优先级：
#   1. 命令行参数 -ConfigPath（privilege.py 传入用户数据目录的路径）
#   2. %APPDATA%\ov2n\config.json（用户通过 GUI 导入的配置）
#   3. resources\xray\config.json（兜底，开发/调试用）

if ($ConfigPath -ne "" -and (Test-Path $ConfigPath)) {
    $resolvedConfigPath = $ConfigPath
    Write-Host "使用指定配置: $resolvedConfigPath"
} else {
    $appDataConfig = Join-Path $env:APPDATA "ov2n\config.json"
    $bundledConfig = Join-Path $xrayDir "config.json"

    if (Test-Path $appDataConfig) {
        $resolvedConfigPath = $appDataConfig
        Write-Host "使用用户配置: $resolvedConfigPath"
    } elseif (Test-Path $bundledConfig) {
        $resolvedConfigPath = $bundledConfig
        Write-Host "使用内置配置: $resolvedConfigPath"
    } else {
        Write-Host "error: config.json not found. Please import Xray config in the GUI first."
        Write-Host "  Searched:"
        Write-Host "    $appDataConfig"
        Write-Host "    $bundledConfig"
        exit 1
    }
}

# 读取并去掉注释
$configContent = Get-Content $resolvedConfigPath -Raw -Encoding utf8
$configContent = $configContent -replace '(?m)^\s*//.*$', ''

try {
    $config = $configContent | ConvertFrom-Json
} catch {
    Write-Host "error: config.json 解析失败 - $_"; exit 1
}

# 获取 VPS 地址
$vpsAddr = $config.outbounds |
    Where-Object { $_.tag -eq "proxy" } |
    Select-Object -ExpandProperty settings |
    Select-Object -ExpandProperty servers |
    Select-Object -First 1 |
    Select-Object -ExpandProperty address

if (-not $vpsAddr) { Write-Host "error: 无法从 config.json 获取 VPS 地址"; exit 1 }
Write-Host "VPS: $vpsAddr"

# 获取默认网关和物理网卡（排除虚拟/VPN 网卡）
$defaultRoute = Get-NetRoute -DestinationPrefix "0.0.0.0/0" |
    Where-Object {
        $_.NextHop -ne "0.0.0.0" -and
        $_.InterfaceAlias -notmatch "(?i)(xray-tun|loopback|isatap|teredo)" -and
        $_.InterfaceAlias -notmatch "(?i)(tap|tun)"
    } |
    Sort-Object RouteMetric |
    Select-Object -First 1

if (-not $defaultRoute) {
    Write-Host "警告: 严格过滤未找到默认路由，尝试宽松过滤..."
    $defaultRoute = Get-NetRoute -DestinationPrefix "0.0.0.0/0" |
        Where-Object {
            $_.NextHop -ne "0.0.0.0" -and
            $_.InterfaceAlias -ne "xray-tun"
        } |
        Sort-Object RouteMetric |
        Select-Object -First 1
}

if (-not $defaultRoute) { Write-Host "error: 找不到默认网关"; exit 1 }

$gateway   = $defaultRoute.NextHop
$realIdx   = $defaultRoute.InterfaceIndex
$realAlias = $defaultRoute.InterfaceAlias
Write-Host "选中网卡: $realAlias (索引: $realIdx), 网关: $gateway"

# 获取本机 IP（排除链路本地地址）
$localIP = Get-NetIPAddress -InterfaceIndex $realIdx -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notmatch "^169\.254\." } |
    Select-Object -First 1 |
    Select-Object -ExpandProperty IPAddress

if (-not $localIP) {
    Write-Host "error: 无法获取本机 IP（网卡 $realAlias 无有效 IPv4 地址）"
    exit 1
}
Write-Host "本机IP: $localIP"

# 注入 sendThrough
foreach ($ob in $config.outbounds) {
    if ($ob.tag -eq "proxy" -or $ob.tag -eq "direct") {
        if ($ob.PSObject.Properties["sendThrough"]) {
            $ob.sendThrough = $localIP
        } else {
            $ob | Add-Member -MemberType NoteProperty -Name "sendThrough" -Value $localIP
        }
    }
}

# 写入 runtime config（无 BOM UTF-8）
$tempConfigPath = Join-Path $xrayDir "config.runtime.json"
$jsonContent = $config | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText(
    $tempConfigPath,
    $jsonContent,
    (New-Object System.Text.UTF8Encoding $false)
)

# 验证编码
$bytes = [System.IO.File]::ReadAllBytes($tempConfigPath)
$header = "{0:X2} {1:X2} {2:X2}" -f $bytes[0], $bytes[1], $bytes[2]
Write-Host "文件头: $header"
if ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
    Write-Host "error: config.runtime.json 含有 BOM"; exit 1
}

# 验证 JSON
try {
    Get-Content $tempConfigPath -Raw | ConvertFrom-Json | Out-Null
    Write-Host "JSON 验证通过"
} catch {
    Write-Host "error: 生成的 JSON 无效 - $_"; exit 1
}

# 清理旧进程
Get-Process -Name "xray" -ErrorAction SilentlyContinue | Stop-Process -Force
$waited = 0
while ((Get-Process -Name "xray" -ErrorAction SilentlyContinue) -and $waited -lt 10) {
    Start-Sleep -Seconds 1; $waited++
}
Write-Host "旧进程已清理"

# 清理旧路由
route delete 0.0.0.0 mask 0.0.0.0 10.0.0.0 2>$null | Out-Null
route delete 0.0.0.0 mask 0.0.0.0 10.0.0.1 2>$null | Out-Null
route delete $vpsAddr 2>$null | Out-Null

# 启动 xray
$xrayPath = Join-Path $xrayDir "xray.exe"
Start-Process -FilePath $xrayPath -ArgumentList "-config `"$tempConfigPath`"" -WindowStyle Minimized
Write-Host "xray 已启动，等待 xray-tun 创建..."

# 等待 xray-tun 出现
$adapter = $null
$waited = 0
do {
    Start-Sleep -Seconds 1
    $waited++
    $adapter = Get-NetAdapter -Name "xray-tun" -ErrorAction SilentlyContinue
    Write-Host "等待 xray-tun... ${waited}s"
} while ($null -eq $adapter -and $waited -lt 20)

if ($null -eq $adapter) {
    Write-Host "error: xray-tun 未出现，请手动运行查看报错："
    Write-Host "  .\xray.exe -config .\config.runtime.json"
    exit 1
}
Write-Host "xray-tun 已出现 (${waited}s)"

Start-Sleep -Seconds 2

# 设置 IP
netsh interface ip set address name="xray-tun" static 10.0.0.1 255.255.255.0
Start-Sleep -Seconds 1

# 重新读取 tunIdx
$adapter = Get-NetAdapter -Name "xray-tun"
$tunIdx  = $adapter.InterfaceIndex
Write-Host "xray-tun 索引: $tunIdx"

# 设置路由
route add $vpsAddr mask 255.255.255.255 $gateway metric 1 if $realIdx
route add $gateway  mask 255.255.255.255 $gateway metric 1 if $realIdx
route add 0.0.0.0   mask 0.0.0.0        10.0.0.0 metric 5 if $tunIdx

# 保存原始 DNS 配置，供 stop-xray.ps1 恢复使用
$dnsFile = Join-Path $xrayDir "dns_backup.txt"
$origDns = (Get-DnsClientServerAddress -InterfaceIndex $realIdx -AddressFamily IPv4).ServerAddresses
if ($origDns -and $origDns.Count -gt 0) {
    # 格式: 网卡名|DNS1,DNS2,...
    "$realAlias|$($origDns -join ',')" | Set-Content $dnsFile -Encoding UTF8
    Write-Host "已保存原始 DNS: $($origDns -join ', ')"
} else {
    # 原来是 DHCP，记录为空
    "$realAlias|DHCP" | Set-Content $dnsFile -Encoding UTF8
    Write-Host "原始 DNS: DHCP"
}

# 设置 DNS（使用固定 DNS 保证 xray 运行期间解析正常）
netsh interface ip set dns name="$realAlias" static 114.114.114.114
netsh interface ip add dns name="$realAlias" 8.8.8.8 index=2
ipconfig /flushdns

Write-Host ""
Write-Host "===== 启动完成 ====="
Write-Host "VPS       : $vpsAddr"
Write-Host "网卡      : $realAlias (索引: $realIdx)"
Write-Host "网关      : $gateway"
Write-Host "sendThrough: $localIP"
Write-Host "tunIdx    : $tunIdx"
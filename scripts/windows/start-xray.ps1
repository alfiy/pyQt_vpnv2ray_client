# ov2n - Xray TUN 启动脚本 (Windows)
# 编码: UTF-8 with BOM
# 需要管理员权限运行

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "error: 请以管理员身份运行"; exit 1
}

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
# 脚本在 scripts/windows/ 下，xray 在 resources/xray/ 下
$appRoot = (Resolve-Path "$dir\..\..").Path
$xrayDir = Join-Path $appRoot "resources\xray"

Set-Location $xrayDir

$configPath = Join-Path $xrayDir "config.json"
if (-not (Test-Path $configPath)) { Write-Host "error: config.json not found at $configPath"; exit 1 }

# 读取并去掉注释
$configContent = Get-Content $configPath -Raw -Encoding utf8
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

# ★ 获取默认网关和物理网卡
# 排除所有虚拟/VPN 网卡：xray-tun、TAP、OpenVPN tap 适配器等
# 匹配条件：NextHop 不是 0.0.0.0，且网卡名不包含 tun/tap/loopback 关键词
$defaultRoute = Get-NetRoute -DestinationPrefix "0.0.0.0/0" |
    Where-Object {
        $_.NextHop -ne "0.0.0.0" -and
        $_.InterfaceAlias -notmatch "(?i)(xray-tun|loopback|isatap|teredo)" -and
        $_.InterfaceAlias -notmatch "(?i)(tap|tun)"
    } |
    Sort-Object RouteMetric |
    Select-Object -First 1

# 如果过滤后找不到，降级为只排除 xray-tun（兼容 TAP 网卡名不规范的情况）
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

# ★ 获取本机 IP：只取 IPv4，排除 169.254.x.x 链路本地地址
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

# 无 BOM 的 UTF-8 写入 runtime config
$tempConfigPath = Join-Path $xrayDir "config.runtime.json"
$jsonContent = $config | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText(
    $tempConfigPath,
    $jsonContent,
    (New-Object System.Text.UTF8Encoding $false)
)

# 验证编码（不能有 BOM）
$bytes = [System.IO.File]::ReadAllBytes($tempConfigPath)
$header = "{0:X2} {1:X2} {2:X2}" -f $bytes[0], $bytes[1], $bytes[2]
Write-Host "文件头: $header"
if ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
    Write-Host "error: config.runtime.json 含有 BOM"; exit 1
}

# 验证 JSON 可解析
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

# 等待 xray-tun 出现，最多 20 秒
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

# 重新读取 tunIdx（网卡重建后索引可能变化）
$adapter = Get-NetAdapter -Name "xray-tun"
$tunIdx  = $adapter.InterfaceIndex
Write-Host "xray-tun 索引: $tunIdx"

# 设置路由
route add $vpsAddr mask 255.255.255.255 $gateway metric 1 if $realIdx
route add $gateway  mask 255.255.255.255 $gateway metric 1 if $realIdx
route add 0.0.0.0   mask 0.0.0.0        10.0.0.0 metric 5 if $tunIdx

# 设置 DNS
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
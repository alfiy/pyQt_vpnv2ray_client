param(
    [string]$ConfigPath = ""
)

# 需要管理员权限运行
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "error: 请以管理员身份运行"; exit 1
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# xray.exe 位于 resources/xray/，脚本位于 scripts/windows/
# 从脚本目录向上两级到项目根目录，再进入 resources/xray
$projectRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)
$xrayDir = Join-Path $projectRoot "resources\xray"

# 配置文件优先级：
# 1. 命令行传入的 -ConfigPath（用户从 GUI 导入的配置）
# 2. %APPDATA%\ov2n\config.json（持久化的用户配置）
# 3. resources\xray\config.json（内置配置）
$configPath = ""
if ($ConfigPath -and (Test-Path $ConfigPath)) {
    $configPath = $ConfigPath
    Write-Host "使用用户配置: $configPath"
} else {
    $appdataConfig = Join-Path $env:APPDATA "ov2n\config.json"
    if (Test-Path $appdataConfig) {
        $configPath = $appdataConfig
        Write-Host "使用 APPDATA 配置: $configPath"
    } else {
        $builtinConfig = Join-Path $xrayDir "config.json"
        if (Test-Path $builtinConfig) {
            $configPath = $builtinConfig
            Write-Host "使用内置配置: $configPath"
        }
    }
}

if (-not $configPath -or -not (Test-Path $configPath)) {
    Write-Host "error: config.json not found (checked: -ConfigPath, APPDATA, resources/xray)"
    exit 1
}

Set-Location $xrayDir

# 读取并去掉注释
$configContent = Get-Content $configPath -Raw -Encoding utf8
$configContent = $configContent -replace '(?m)^\s*//.*$', ''

# 解析 JSON
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

# 获取默认网关和物理网卡
$defaultRoute = Get-NetRoute -DestinationPrefix "0.0.0.0/0" |
    Where-Object { $_.NextHop -ne "0.0.0.0" -and $_.InterfaceAlias -ne "xray-tun" } |
    Sort-Object RouteMetric |
    Select-Object -First 1

if (-not $defaultRoute) { Write-Host "error: 找不到默认网关"; exit 1 }

$gateway   = $defaultRoute.NextHop
$realIdx   = $defaultRoute.InterfaceIndex
$realAlias = $defaultRoute.InterfaceAlias

# 获取本机 IP
$localIP = (Get-NetIPAddress -InterfaceIndex $realIdx -AddressFamily IPv4 |
    Select-Object -First 1).IPAddress

if (-not $localIP) { Write-Host "error: 无法获取本机 IP"; exit 1 }
Write-Host "网卡: $realAlias (索引: $realIdx), 网关: $gateway, 本机IP: $localIP"

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

# ★ 关键：无 BOM 的 UTF-8 写入（runtime 配置写到 xrayDir）
$tempConfigPath = Join-Path $xrayDir "config.runtime.json"
$jsonContent = $config | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText(
    $tempConfigPath,
    $jsonContent,
    (New-Object System.Text.UTF8Encoding $false)
)

# 验证编码（前3字节必须是 7B 开头，不能是 EF BB BF）
$bytes = [System.IO.File]::ReadAllBytes($tempConfigPath)
$header = "{0:X2} {1:X2} {2:X2}" -f $bytes[0], $bytes[1], $bytes[2]
Write-Host "文件头: $header"
if ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
    Write-Host "error: config.runtime.json 含有 BOM，写入方式有问题"; exit 1
}
Write-Host "编码验证通过"

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
route delete 0.0.0.0 mask 0.0.0.0 10.0.0.0 | Out-Null
route delete 0.0.0.0 mask 0.0.0.0 10.0.0.1 | Out-Null
route delete $vpsAddr | Out-Null

# 启动 xray（xray.exe 在 xrayDir 中）
$xrayPath = Join-Path $xrayDir "xray.exe"
# Minimized 启动 xray，避免 xray.exe 窗口弹出
# Hidden 隐藏xray启动窗口
Start-Process -FilePath $xrayPath -ArgumentList "-config `"$tempConfigPath`"" -WindowStyle Hidden
Write-Host "xray 已启动，等待 xray-tun 创建..."

# ★ 等待 xray-tun 出现，最多 20 秒
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
    Write-Host "  .\\xray.exe -config .\\config.runtime.json"
    exit 1
}
Write-Host "xray-tun 已出现 (${waited}s)"

# 等网卡稳定后再操作
Start-Sleep -Seconds 2

# 设置 IP
netsh interface ip set address name="xray-tun" static 10.0.0.1 255.255.255.0
Start-Sleep -Seconds 1

# ★ 重新读取 tunIdx（网卡重建后索引可能变化）
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
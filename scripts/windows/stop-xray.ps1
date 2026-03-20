# ov2n - Xray TUN 停止脚本 (Windows)
# 编码: UTF-8 with BOM
# 需要管理员权限运行

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "error: 请以管理员身份运行"; exit 1
}

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = (Resolve-Path "$dir\..\..").Path
$xrayDir = Join-Path $appRoot "resources\xray"

Write-Host "===== 停止 Xray TUN ====="

# 读取 VPS 地址用于清理路由
$configPath = Join-Path $xrayDir "config.json"
$vpsAddr = ""
if (Test-Path $configPath) {
    try {
        $content = Get-Content $configPath -Raw -Encoding utf8
        $content = $content -replace '(?m)^\s*//.*$', ''
        $config = $content | ConvertFrom-Json
        $vpsAddr = $config.outbounds |
            Where-Object { $_.tag -eq "proxy" } |
            Select-Object -ExpandProperty settings |
            Select-Object -ExpandProperty servers |
            Select-Object -First 1 |
            Select-Object -ExpandProperty address
    } catch {}
}

# 停止 xray 进程
Write-Host "停止 xray 进程..."
Get-Process -Name "xray" -ErrorAction SilentlyContinue | Stop-Process -Force
$waited = 0
while ((Get-Process -Name "xray" -ErrorAction SilentlyContinue) -and $waited -lt 10) {
    Start-Sleep -Seconds 1; $waited++
}
Write-Host "xray 进程已停止"

# 清理路由
Write-Host "清理路由..."
route delete 0.0.0.0 mask 0.0.0.0 10.0.0.0 2>$null | Out-Null
route delete 0.0.0.0 mask 0.0.0.0 10.0.0.1 2>$null | Out-Null
if ($vpsAddr) {
    route delete $vpsAddr 2>$null | Out-Null
    Write-Host "已清理 VPS 路由: $vpsAddr"
}

# 恢复 DNS
Write-Host "恢复 DNS 设置..."
$defaultRoute = Get-NetRoute -DestinationPrefix "0.0.0.0/0" |
    Where-Object { $_.NextHop -ne "0.0.0.0" -and $_.InterfaceAlias -ne "xray-tun" } |
    Sort-Object RouteMetric |
    Select-Object -First 1

if ($defaultRoute) {
    $realAlias = $defaultRoute.InterfaceAlias
    netsh interface ip set dns name="$realAlias" dhcp 2>$null
    Write-Host "已恢复 $realAlias DNS 为 DHCP"
}

ipconfig /flushdns | Out-Null

Write-Host ""
Write-Host "===== Xray TUN 已停止 ====="
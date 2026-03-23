# ov2n - Xray TUN 停止脚本 (Windows)
# 编码: UTF-8 with BOM
# 需要管理员权限运行
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "error: 请以管理员身份运行"; exit 1
}
$dir     = Split-Path -Parent $MyInvocation.MyCommand.Path
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

# ── 恢复 DNS ──────────────────────────────────────────────
# 优先从 start-xray.ps1 保存的 dns_backup.txt 恢复原始配置
# 避免无条件设为 DHCP 导致静态 DNS 用户重启后无法联网
Write-Host "恢复 DNS 配置..."
$dnsFile = Join-Path $xrayDir "dns_backup.txt"

if (Test-Path $dnsFile) {
    try {
        $line = Get-Content $dnsFile -Raw -Encoding UTF8
        $line = $line.Trim()
        $parts = $line -split '\|', 2
        $savedAlias = $parts[0].Trim()
        $savedDns   = $parts[1].Trim()

        if ($savedDns -eq "DHCP" -or $savedDns -eq "") {
            # 原来是 DHCP，恢复为 DHCP
            netsh interface ip set dns name="$savedAlias" dhcp 2>$null
            Write-Host "已恢复 $savedAlias DNS 为 DHCP"
        } else {
            # 原来是静态 DNS，逐条恢复
            $dnsList = $savedDns -split ','
            netsh interface ip set dns name="$savedAlias" static $dnsList[0] 2>$null
            for ($i = 1; $i -lt $dnsList.Count; $i++) {
                netsh interface ip add dns name="$savedAlias" $dnsList[$i] index=($i + 1) 2>$null
            }
            Write-Host "已恢复 $savedAlias 静态 DNS: $savedDns"
        }

        # 恢复完成后删除备份文件
        Remove-Item $dnsFile -Force -ErrorAction SilentlyContinue
    } catch {
        Write-Host "警告: DNS 备份文件读取失败 ($_)，尝试回退到 DHCP"
        $defaultRoute = Get-NetRoute -DestinationPrefix "0.0.0.0/0" |
            Where-Object { $_.NextHop -ne "0.0.0.0" -and $_.InterfaceAlias -ne "xray-tun" } |
            Sort-Object RouteMetric | Select-Object -First 1
        if ($defaultRoute) {
            netsh interface ip set dns name="$($defaultRoute.InterfaceAlias)" dhcp 2>$null
        }
    }
} else {
    # 没有备份文件（旧版本或异常退出），回退到 DHCP
    Write-Host "未找到 DNS 备份，回退到 DHCP"
    $defaultRoute = Get-NetRoute -DestinationPrefix "0.0.0.0/0" |
        Where-Object { $_.NextHop -ne "0.0.0.0" -and $_.InterfaceAlias -ne "xray-tun" } |
        Sort-Object RouteMetric | Select-Object -First 1
    if ($defaultRoute) {
        netsh interface ip set dns name="$($defaultRoute.InterfaceAlias)" dhcp 2>$null
        Write-Host "已恢复 $($defaultRoute.InterfaceAlias) DNS 为 DHCP"
    }
}

ipconfig /flushdns | Out-Null

Write-Host ""
Write-Host "===== Xray TUN 已停止 ====="
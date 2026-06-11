param(
    [string]$AppDir = "C:\wwwroot\lxclgl",
    [string]$ServiceName = "lxclgl",
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

$Diag = Join-Path $AppDir "deploy-diagnostic.txt"
"force_restart=1" | Add-Content -LiteralPath $Diag

Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
Stop-ScheduledTask -TaskName $ServiceName -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

$AppProcesses = Get-CimInstance Win32_Process -Filter "Name LIKE 'python%.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*$AppDir*" }
foreach ($ProcessInfo in $AppProcesses) {
    "kill_app_pid=$($ProcessInfo.ProcessId)" | Add-Content -LiteralPath $Diag
    Stop-Process -Id $ProcessInfo.ProcessId -Force -ErrorAction SilentlyContinue
}

$Listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
foreach ($Listener in $Listeners) {
    $Process = Get-Process -Id $Listener.OwningProcess -ErrorAction SilentlyContinue
    if ($Process -and $Process.ProcessName -match "python") {
        "kill_port_pid=$($Process.Id)" | Add-Content -LiteralPath $Diag
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    }
}

$Service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($Service) {
    Start-Service -Name $ServiceName
} elseif (Get-ScheduledTask -TaskName $ServiceName -ErrorAction SilentlyContinue) {
    Start-ScheduledTask -TaskName $ServiceName
} else {
    throw "Auto-start '$ServiceName' is not installed."
}

Start-Sleep -Seconds 5

$Listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $Listening) {
    throw "App is not listening on port $Port after force restart."
}

"force_restart_done=1" | Add-Content -LiteralPath $Diag

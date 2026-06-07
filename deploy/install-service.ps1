param(
    [string]$AppDir = "C:\wwwroot\lxclgl",
    [string]$ServiceName = "lxclgl",
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $AppDir

$LocalEnv = Join-Path $AppDir "deploy\server.env.ps1"
if (-not (Test-Path -LiteralPath $LocalEnv)) {
    throw "Missing deploy\server.env.ps1. Copy deploy\server.env.ps1.example first and set SECRET_KEY."
}
. $LocalEnv

if (-not $env:SECRET_KEY) {
    throw "SECRET_KEY is missing in deploy\server.env.ps1."
}

$Nssm = Join-Path $AppDir "tools\nssm.exe"
if (-not (Test-Path -LiteralPath $Nssm)) {
    throw "Missing $Nssm. Download NSSM, create tools folder, and place nssm.exe there."
}

$VenvPython = Join-Path $AppDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "Creating virtual environment"
    python -m venv .venv
}

Write-Host "Installing Python dependencies"
& $VenvPython -m pip install -r requirements.txt

$Existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($Existing) {
    Write-Host "Service $ServiceName already exists. Stopping before reconfiguring."
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "Installing Windows service: $ServiceName"
    & $Nssm install $ServiceName $VenvPython "app.py"
}

$OutLog = Join-Path $AppDir ".server-out.log"
$ErrLog = Join-Path $AppDir ".server-err.log"

& $Nssm set $ServiceName AppDirectory $AppDir
& $Nssm set $ServiceName AppEnvironmentExtra "SECRET_KEY=$env:SECRET_KEY"
& $Nssm set $ServiceName AppStdout $OutLog
& $Nssm set $ServiceName AppStderr $ErrLog
& $Nssm set $ServiceName AppRotateFiles 1
& $Nssm set $ServiceName AppRotateOnline 1
& $Nssm set $ServiceName AppRotateSeconds 86400
& $Nssm set $ServiceName Start SERVICE_AUTO_START

Write-Host "Starting service: $ServiceName"
Start-Service -Name $ServiceName
Start-Sleep -Seconds 3

$Listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($Listening) {
    Write-Host "Service installed and app is listening on port $Port."
} else {
    Write-Host "Service started but port $Port is not listening. Last error log:"
    if (Test-Path -LiteralPath $ErrLog) {
        Get-Content -LiteralPath $ErrLog -Tail 80
    }
    exit 1
}

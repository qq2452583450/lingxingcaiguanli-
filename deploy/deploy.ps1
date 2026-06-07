param(
    [string]$AppDir = "C:\wwwroot\lxclgl",
    [string]$ServiceName = "lxclgl",
    [string]$Branch = "main",
    [string]$DbFile = "零星材管理系统.db",
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $AppDir

$LocalEnv = Join-Path $AppDir "deploy\server.env.ps1"
if (Test-Path -LiteralPath $LocalEnv) {
    . $LocalEnv
}

if (-not $env:SECRET_KEY) {
    throw "SECRET_KEY is missing. Create deploy\server.env.ps1 and set `$env:SECRET_KEY='your-long-random-secret'."
}

$BackupDir = Join-Path $AppDir "backups"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

if (Test-Path -LiteralPath $DbFile) {
    $Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $BackupPath = Join-Path $BackupDir "$DbFile.bak-$Timestamp"
    Write-Host "Backing up database to $BackupPath"
    Copy-Item -LiteralPath $DbFile -Destination $BackupPath
} else {
    Write-Host "Database $DbFile not found, skipping backup"
}

Write-Host "Pulling latest code from origin/$Branch"
git fetch origin $Branch
git checkout $Branch
git pull --ff-only origin $Branch

$VenvPython = Join-Path $AppDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "Creating virtual environment"
    python -m venv .venv
}

Write-Host "Installing Python dependencies"
& $VenvPython -m pip install -r requirements.txt

$Service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($Service) {
    Write-Host "Restarting Windows service: $ServiceName"
    Restart-Service -Name $ServiceName -Force
} else {
    throw "Windows service '$ServiceName' is not installed. Run deploy\install-service.ps1 once on the server first."
}

Start-Sleep -Seconds 3

$Listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($Listening) {
    Write-Host "Deploy finished. App is listening on port $Port."
} else {
    Write-Host "App did not start listening on port $Port. Last error log:"
    $ErrLog = Join-Path $AppDir ".server-err.log"
    if (Test-Path -LiteralPath $ErrLog) {
        Get-Content -LiteralPath $ErrLog -Tail 80
    }
    exit 1
}

param(
    [string]$AppDir = "C:\wwwroot\lxclgl",
    [string]$ServiceName = "lxclgl",
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

function Ensure-Nssm {
    param([string]$TargetPath)

    if (Test-Path -LiteralPath $TargetPath) {
        return
    }

    $ToolsDir = Split-Path -Parent $TargetPath
    New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null

    $TempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("lxclgl-nssm-" + [System.Guid]::NewGuid().ToString("N"))
    $ZipPath = Join-Path $TempDir "nssm.zip"
    New-Item -ItemType Directory -Force -Path $TempDir | Out-Null

    try {
        Write-Host "Downloading NSSM service helper"
        Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile $ZipPath
        Expand-Archive -LiteralPath $ZipPath -DestinationPath $TempDir -Force

        $Candidate = Get-ChildItem -LiteralPath $TempDir -Recurse -Filter "nssm.exe" |
            Where-Object { $_.FullName -match "\\win64\\nssm\.exe$" } |
            Select-Object -First 1

        if (-not $Candidate) {
            throw "Could not find win64 nssm.exe in downloaded archive."
        }

        Copy-Item -LiteralPath $Candidate.FullName -Destination $TargetPath -Force
    }
    finally {
        Remove-Item -LiteralPath $TempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

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
Ensure-Nssm -TargetPath $Nssm

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

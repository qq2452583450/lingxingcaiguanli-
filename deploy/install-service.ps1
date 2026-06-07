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

function Stop-AppOnPort {
    param([int]$TargetPort)

    $Listeners = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue
    foreach ($Listener in $Listeners) {
        $Process = Get-Process -Id $Listener.OwningProcess -ErrorAction SilentlyContinue
        if ($Process -and $Process.ProcessName -match "python") {
            Write-Host "Stopping existing Python process on port $TargetPort"
            Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

function Install-StartupTask {
    param(
        [string]$TaskName,
        [string]$TargetAppDir
    )

    $StartScript = Join-Path $TargetAppDir "deploy\start-app.ps1"
    if (-not (Test-Path -LiteralPath $StartScript)) {
        throw "Missing startup script: $StartScript"
    }

    Write-Host "Installing startup task: $TaskName"
    $Action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`" -AppDir `"$TargetAppDir`""
    $Trigger = New-ScheduledTaskTrigger -AtStartup
    $Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
    $Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings | Out-Null
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
$UseNssm = $true
try {
    Ensure-Nssm -TargetPath $Nssm
} catch {
    $UseNssm = $false
    Write-Host "NSSM is unavailable, falling back to Windows startup task."
    Write-Host $_.Exception.Message
}

$VenvPython = Join-Path $AppDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "Creating virtual environment"
    python -m venv .venv
}

Write-Host "Installing Python dependencies"
& $VenvPython -m pip install -r requirements.txt

if ($UseNssm) {
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
} else {
    Stop-AppOnPort -TargetPort $Port
    Install-StartupTask -TaskName $ServiceName -TargetAppDir $AppDir
    Write-Host "Starting startup task: $ServiceName"
    Start-ScheduledTask -TaskName $ServiceName
}

Start-Sleep -Seconds 3

$Listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($Listening) {
    Write-Host "Auto-start installed and app is listening on port $Port."
} else {
    $ErrLog = Join-Path $AppDir ".server-err.log"
    Write-Host "Auto-start was configured but port $Port is not listening. Last error log:"
    if (Test-Path -LiteralPath $ErrLog) {
        Get-Content -LiteralPath $ErrLog -Tail 80
    }
    exit 1
}

param(
    [string]$AppDir = "C:\wwwroot\lxclgl",
    [string]$ServiceName = "lxclgl",
    [string]$Branch = "main",
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $AppDir

function Invoke-NativeCommandWithRetry {
    param(
        [string]$Description,
        [scriptblock]$Command,
        [string]$FailureMessage,
        [int]$Attempts = 5,
        [int]$DelaySeconds = 15
    )

    for ($Attempt = 1; $Attempt -le $Attempts; $Attempt++) {
        Write-Host "$Description (attempt $Attempt/$Attempts)"
        & $Command
        if ($LASTEXITCODE -eq 0) {
            return
        }
        if ($Attempt -lt $Attempts) {
            Start-Sleep -Seconds $DelaySeconds
        }
    }
    throw $FailureMessage
}

function Stop-PythonListenerOnPort {
    param([int]$TargetPort)

    Write-Host "Clearing Python listener on port $TargetPort before service start."
    $Listeners = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue
    foreach ($Listener in $Listeners) {
        $Process = Get-Process -Id $Listener.OwningProcess -ErrorAction SilentlyContinue
        if ($Process) {
            Write-Host "Stopping stale listener $($Process.ProcessName) (PID $($Process.Id)) on port $TargetPort."
            Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

function Stop-AppPythonProcesses {
    Write-Host "Clearing Python processes launched from $AppDir before service start."
    $EscapedAppDir = $AppDir.Replace('\', '\\')
    $Processes = Get-CimInstance Win32_Process -Filter "Name LIKE 'python%.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*$AppDir*" -or $_.CommandLine -match $EscapedAppDir }
    foreach ($ProcessInfo in $Processes) {
        Stop-Process -Id $ProcessInfo.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-ExamScoreRegrade {
    Write-Host "Regrading exam scores and normalizing paper totals"
    & $VenvPython "tools\regrade_practice_attempts.py" --apply --backup
    if ($LASTEXITCODE -ne 0) { throw "exam score regrade failed" }

    Write-Host "Applying one-time exam data fixes"
    & $VenvPython "tools\apply_exam_data_fixes.py" --apply
    if ($LASTEXITCODE -ne 0) { throw "exam data fixes failed" }
}

$LocalEnv = Join-Path $AppDir "deploy\server.env.ps1"
if (Test-Path -LiteralPath $LocalEnv) {
    . $LocalEnv
}

if (-not $env:SECRET_KEY) {
    throw "SECRET_KEY is missing. Create deploy\server.env.ps1 and set `$env:SECRET_KEY='your-long-random-secret'."
}

$BackupDir = Join-Path $AppDir "backups"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

$DbFiles = Get-ChildItem -LiteralPath $AppDir -Filter "*.db" -File -ErrorAction SilentlyContinue
if ($DbFiles) {
    $Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    foreach ($DbFile in $DbFiles) {
        $BackupPath = Join-Path $BackupDir "$($DbFile.Name).bak-$Timestamp"
        Write-Host "Backing up database to $BackupPath"
        Copy-Item -LiteralPath $DbFile.FullName -Destination $BackupPath
    }
} else {
    Write-Host "No .db files found, skipping backup"
}

Write-Host "Pulling latest code from origin/$Branch"
Invoke-NativeCommandWithRetry "git fetch origin $Branch" { git fetch origin $Branch } "git fetch origin $Branch failed"
Invoke-NativeCommandWithRetry "git checkout $Branch" { git checkout $Branch } "git checkout $Branch failed"
Invoke-NativeCommandWithRetry "git pull --ff-only origin $Branch" { git pull --ff-only origin $Branch } "git pull origin $Branch failed"

$VenvPython = Join-Path $AppDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "Creating virtual environment"
    python -m venv .venv
}

Write-Host "Installing Python dependencies"
& $VenvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

$Service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($Service) {
    Write-Host "Restarting Windows service: $ServiceName"
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    $Stopped = $false
    for ($i = 0; $i -lt 12; $i++) {
        $Service.Refresh()
        if ($Service.Status -eq "Stopped") {
            $Stopped = $true
            break
        }
        Start-Sleep -Seconds 5
    }
    if (-not $Stopped) {
        Write-Host "Service did not stop in time."
    }
    Stop-AppPythonProcesses
    Stop-PythonListenerOnPort -TargetPort $Port
    Invoke-ExamScoreRegrade
    Start-Service -Name $ServiceName
    Start-Sleep -Seconds 3
    $Service.Refresh()
    if ($Service.Status -ne "Running") {
        throw "Windows service $ServiceName failed to start"
    }
} elseif (Get-ScheduledTask -TaskName $ServiceName -ErrorAction SilentlyContinue) {
    Write-Host "Restarting startup task: $ServiceName"
    Stop-ScheduledTask -TaskName $ServiceName -ErrorAction SilentlyContinue
    Stop-AppPythonProcesses
    Stop-PythonListenerOnPort -TargetPort $Port
    Invoke-ExamScoreRegrade
    Start-ScheduledTask -TaskName $ServiceName
} else {
    throw "Auto-start '$ServiceName' is not installed. Run deploy\install-service.ps1 once on the server first."
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

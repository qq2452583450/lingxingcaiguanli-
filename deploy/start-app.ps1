param(
    [string]$AppDir = "C:\wwwroot\lxclgl"
)

$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $AppDir

$LocalEnv = Join-Path $AppDir "deploy\server.env.ps1"
if (Test-Path -LiteralPath $LocalEnv) {
    . $LocalEnv
}

if (-not $env:SECRET_KEY) {
    throw "SECRET_KEY is missing. Create deploy\server.env.ps1 first."
}

$VenvPython = Join-Path $AppDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "Virtual environment Python not found: $VenvPython"
}

$OutLog = Join-Path $AppDir ".server-out.log"
$ErrLog = Join-Path $AppDir ".server-err.log"

& $VenvPython "app.py" 1>> $OutLog 2>> $ErrLog

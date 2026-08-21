<#
Agent Hub - local Windows run script.

Run from PowerShell, from inside the agent-hub folder:
    .\deploy\windows-run.ps1

First run does the full one-time setup (builds the frontend, creates a
Python virtual environment, installs dependencies) and then starts the
server. Later runs just start the server, unless you pass -Rebuild.

If Windows refuses to run this script at all with a message about execution
policies, run this once in the same PowerShell window first, then try again:
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#>

param(
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RootDir "backend"
$FrontendDir = Join-Path $RootDir "frontend"
$StaticDir = Join-Path $BackendDir "app\static"
$VenvDir = Join-Path $BackendDir ".venv"

function Test-Command($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

Write-Host "==> Checking prerequisites"
$PythonCmd = $null
if (Test-Command "python") { $PythonCmd = "python" }
elseif (Test-Command "py") { $PythonCmd = "py" }
else {
    Write-Host "Python not found. Install it from https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host "(check 'Add python.exe to PATH' during install), then re-run this script." -ForegroundColor Red
    exit 1
}

if (-not (Test-Command "npm")) {
    Write-Host "Node.js not found. Install the LTS version from https://nodejs.org, then re-run this script." -ForegroundColor Red
    exit 1
}

$staticIsEmpty = -not (Test-Path $StaticDir) -or ((Get-ChildItem $StaticDir -ErrorAction SilentlyContinue).Count -eq 0)
if ($Rebuild -or $staticIsEmpty) {
    Write-Host "==> Building the frontend"
    Push-Location $FrontendDir
    npm install
    npm run build
    Pop-Location
    if (Test-Path $StaticDir) { Remove-Item -Recurse -Force $StaticDir }
    Copy-Item -Recurse (Join-Path $FrontendDir "dist") $StaticDir
} else {
    Write-Host "==> Frontend already built (use -Rebuild to force a fresh build)"
}

if ($Rebuild -or -not (Test-Path $VenvDir)) {
    Write-Host "==> Creating Python virtual environment and installing dependencies"
    & $PythonCmd -m venv $VenvDir
    & "$VenvDir\Scripts\python.exe" -m pip install --upgrade pip --quiet
    & "$VenvDir\Scripts\pip.exe" install -r (Join-Path $BackendDir "requirements.txt") --quiet
} else {
    Write-Host "==> Virtual environment already set up (use -Rebuild to reinstall)"
}

Write-Host ""
Write-Host "==> Starting Agent Hub - open http://localhost:8811 in your browser" -ForegroundColor Green
Write-Host "    Press Ctrl+C in this window to stop it."
Write-Host ""

Push-Location $BackendDir
& "$VenvDir\Scripts\uvicorn.exe" app.main:app --host 127.0.0.1 --port 8811
Pop-Location

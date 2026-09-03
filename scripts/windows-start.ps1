# Windows start helper for Hermes Agent
# Builds the dashboard frontend if missing, optionally packs the desktop app.
#
# Usage (from repo root):
#   powershell -File scripts\windows-start.ps1
#   powershell -File scripts\windows-start.ps1 -Desktop
#   powershell -File scripts\windows-start.ps1 -PackInstaller

param(
    [switch]$Desktop,
    [switch]$PackInstaller
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Hermes repo: $Root"

$webIndex = Join-Path $Root "hermes_cli\web_dist\index.html"
if (-not (Test-Path $webIndex)) {
    Write-Host "Dashboard frontend missing — building web/"
    Push-Location (Join-Path $Root "web")
    if (-not (Test-Path "node_modules")) {
        npm install
    }
    npm run build
    Pop-Location
} else {
    Write-Host "Dashboard frontend already built."
}

if ($PackInstaller) {
    Write-Host "Building Windows NSIS installer (this takes several minutes)..."
    Push-Location (Join-Path $Root "apps\desktop")
    npm run dist:win:nsis
    Pop-Location
    Write-Host "Installer output: apps\desktop\release\"
    Get-ChildItem (Join-Path $Root "apps\desktop\release") -ErrorAction SilentlyContinue | Select-Object Name, Length
    return
}

if ($Desktop) {
    Write-Host "Starting Hermes desktop (python -m hermes_cli.main desktop)..."
    python -m hermes_cli.main desktop
    return
}

Write-Host ""
Write-Host "Starting dashboard at http://127.0.0.1:9119"
Write-Host "If the page is blank, wait for the first model/config load."
Write-Host ""

python -m hermes_cli.main dashboard --host 127.0.0.1 --port 9119

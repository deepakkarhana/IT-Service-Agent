# One-time setup: creates the Python virtual environment, installs the backend
# dependencies and installs the frontend dependencies.
#
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host '==> Creating Python virtual environment (.venv)' -ForegroundColor Cyan
if (-not (Test-Path '.venv')) { python -m venv .venv }

Write-Host '==> Installing backend dependencies' -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

Write-Host '==> Installing frontend dependencies' -ForegroundColor Cyan
Push-Location frontend
npm install --no-audit --no-fund
Pop-Location

if (-not (Test-Path '.env')) {
  Copy-Item '.env.example' '.env'
  Write-Host '==> Created .env from .env.example (no API key needed to run)' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Setup complete. Start the app with: scripts\dev.ps1' -ForegroundColor Green

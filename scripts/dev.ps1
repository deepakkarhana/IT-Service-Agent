# Starts the backend and the frontend together, each in its own window.
#
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
#
# Backend : http://127.0.0.1:8020  (API docs at /docs)
# Frontend: http://localhost:5173
#
# If port 8020 is taken on your machine, pass another one:
#   scripts\dev.ps1 -BackendPort 8030

param([int]$BackendPort = 8020)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path '.venv\Scripts\python.exe')) {
  Write-Host 'Virtual environment not found. Run scripts\setup.ps1 first.' -ForegroundColor Red
  exit 1
}

Write-Host "==> Backend  : http://127.0.0.1:$BackendPort" -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
  '-NoExit', '-Command',
  "Set-Location '$root'; .\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port $BackendPort --reload"
)

Start-Sleep -Seconds 2

Write-Host '==> Frontend : http://localhost:5173' -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
  '-NoExit', '-Command',
  "Set-Location '$root\frontend'; `$env:VITE_API_TARGET='http://127.0.0.1:$BackendPort'; npm run dev"
)

Write-Host ''
Write-Host 'Both servers are starting in separate windows.' -ForegroundColor Green
Write-Host 'Open http://localhost:5173 in your browser.' -ForegroundColor Green

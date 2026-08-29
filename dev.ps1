# Start both dev servers: FastAPI on :8000 and Vite on :5173.
#
# Open http://localhost:5173 — Vite serves the UI with hot reload and proxies
# /api straight through to FastAPI, so there is no CORS setup and no base URL
# to configure.
#
# Node lives in a portable folder under %LOCALAPPDATA% rather than being
# installed system-wide (the MSI needs admin). This script puts it on PATH for
# this session only; nothing outside this window is changed.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# --- locate the portable Node -------------------------------------------------
$nodeRoot = Join-Path $env:LOCALAPPDATA "nodejs"
$nodeDir = $null
if (Test-Path $nodeRoot) {
    $nodeDir = (Get-ChildItem $nodeRoot -Directory |
        Where-Object { $_.Name -like "node-*" } |
        Sort-Object Name -Descending |
        Select-Object -First 1)
}
if ($nodeDir) {
    $env:Path = "$($nodeDir.FullName);$env:Path"
} elseif (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "Node not found." -ForegroundColor Red
    Write-Host "Install it system-wide with:  winget install OpenJS.NodeJS.LTS" -ForegroundColor Yellow
    Write-Host "or re-run the portable download in docs/FRONTEND.md." -ForegroundColor Yellow
    exit 1
}
Write-Host "node $(node --version)  npm $(npm --version)" -ForegroundColor DarkGray

# --- Python env ---------------------------------------------------------------
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}

# --- frontend deps ------------------------------------------------------------
if (-not (Test-Path "frontend\node_modules")) {
    Write-Host "Installing frontend dependencies..." -ForegroundColor Cyan
    Push-Location frontend
    npm install
    Pop-Location
}

# --- run both -----------------------------------------------------------------
Write-Host ""
Write-Host "  API  http://127.0.0.1:8000/docs" -ForegroundColor DarkGray
Write-Host "  UI   http://localhost:5173" -ForegroundColor Green
Write-Host "  Ctrl+C stops the UI; close the API window separately." -ForegroundColor DarkGray
Write-Host ""

$api = Start-Process -PassThru -NoNewWindow `
    -FilePath ".\.venv\Scripts\python.exe" `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--port", "8000", "--reload"

try {
    Push-Location frontend
    npm run dev
} finally {
    Pop-Location
    if ($api -and -not $api.HasExited) {
        Write-Host "Stopping API..." -ForegroundColor DarkGray
        Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue
    }
}

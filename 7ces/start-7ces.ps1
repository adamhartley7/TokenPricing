<#
.SYNOPSIS
    Start 7C's: the spend-guard gateway (and optionally bring up LibreChat).

.DESCRIPTION
    Run this from PowerShell:  ./start-7Cs.ps1
    It will:
      1. create the gateway's Python venv (first run only) and install dependencies,
      2. ensure 7Cs/gateway/.env exists (copied from .env.example if missing),
      3. launch the gateway with uvicorn in a NEW window (close that window to stop it),
      4. open the cost meter at http://localhost:8787/,
      5. print the next steps for LibreChat (or bring it up if you pass -LibreChatPath).

    The gateway binds 0.0.0.0 by default so LibreChat-in-Docker can reach it via
    host.docker.internal. Your spend caps + Windows Firewall are the backstops (see README).

.PARAMETER LibreChatPath
    Optional path to your LibreChat clone. If given (and Docker is running), the script copies our
    librechat.yaml + docker-compose.override.yml in and runs `docker compose up -d`.

.PARAMETER Port
    Gateway port (default 8787).

.PARAMETER BindHost
    Gateway bind address (default 0.0.0.0). Use 127.0.0.1 if you never call it from a container.

.PARAMETER NoBrowser
    Do not open the meter page.

.EXAMPLE
    ./start-7Cs.ps1
.EXAMPLE
    ./start-7Cs.ps1 -LibreChatPath C:\Users\me\LibreChat
#>
param(
    [string]$LibreChatPath = "",
    [int]$Port = 8787,
    [string]$BindHost = "0.0.0.0",
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$GatewayDir = Join-Path $PSScriptRoot 'gateway'
$VenvPython = Join-Path $GatewayDir '.venv\Scripts\python.exe'

function Resolve-Python {
    foreach ($cmd in @('python', 'py')) {
        if (Get-Command $cmd -ErrorAction SilentlyContinue) { return $cmd }
    }
    Write-Error "Python 3.11+ not found on PATH. Install it from https://www.python.org/downloads/ and re-run."
    exit 1
}

# --- 1. venv + dependencies -----------------------------------------------------
if (-not (Test-Path $VenvPython)) {
    $py = Resolve-Python
    Write-Host "Creating gateway virtual environment (first run only)…" -ForegroundColor Cyan
    & $py -m venv (Join-Path $GatewayDir '.venv')
}
Write-Host "Installing/updating gateway dependencies…" -ForegroundColor Cyan
& $VenvPython -m pip install --quiet --upgrade pip
& $VenvPython -m pip install --quiet -r (Join-Path $GatewayDir 'requirements.txt')

# --- 2. .env --------------------------------------------------------------------
$EnvFile = Join-Path $GatewayDir '.env'
$EnvExample = Join-Path $GatewayDir '.env.example'
if (-not (Test-Path $EnvFile)) {
    Copy-Item $EnvExample $EnvFile
    Write-Host "Created 7Cs/gateway/.env from the example. Open it and add your keys (or rely on" -ForegroundColor Yellow
    Write-Host "  a git-ignored .deepseek-key / .anthropic-key at the repo root)." -ForegroundColor Yellow
}

# --- 3. launch gateway in a new window ------------------------------------------
Write-Host "Starting the gateway on ${BindHost}:${Port} (new window — close it to stop)…" -ForegroundColor Green
Start-Process -FilePath $VenvPython `
    -ArgumentList @('-m', 'uvicorn', 'app:app', '--host', $BindHost, '--port', "$Port") `
    -WorkingDirectory $GatewayDir

# Give it a moment, then health-check.
Start-Sleep -Seconds 3
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 5
    Write-Host ("Gateway healthy. Keys present — DeepSeek: {0}, Anthropic: {1}." -f `
        $health.providers.deepseek, $health.providers.anthropic) -ForegroundColor Green
} catch {
    Write-Host "Gateway did not answer /health yet — check the new window for errors." -ForegroundColor Yellow
}

if (-not $NoBrowser) { Start-Process "http://localhost:$Port/" }

# --- 4. optional: bring up LibreChat -------------------------------------------
if ($LibreChatPath -ne "") {
    if (-not (Test-Path $LibreChatPath)) { Write-Error "LibreChat path not found: $LibreChatPath"; exit 1 }
    Write-Host "Wiring 7C's config into LibreChat at $LibreChatPath…" -ForegroundColor Cyan
    Copy-Item (Join-Path $PSScriptRoot 'librechat\librechat.yaml') (Join-Path $LibreChatPath 'librechat.yaml') -Force
    Copy-Item (Join-Path $PSScriptRoot 'librechat\docker-compose.override.yml') (Join-Path $LibreChatPath 'docker-compose.override.yml') -Force
    Write-Host "Copied librechat.yaml + docker-compose.override.yml." -ForegroundColor DarkGray
    Write-Host "NOTE: add the keys from 7Cs/librechat/.env.example to LibreChat's own .env first." -ForegroundColor Yellow
    Push-Location $LibreChatPath
    try { docker compose up -d } finally { Pop-Location }
    Write-Host "LibreChat starting at http://localhost:3080" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Next: start LibreChat (see 7Cs/README.md). In short:" -ForegroundColor Cyan
    Write-Host "  1. Copy 7Cs/librechat/librechat.yaml and docker-compose.override.yml into your LibreChat clone."
    Write-Host "  2. Add the entries from 7Cs/librechat/.env.example to LibreChat's .env."
    Write-Host "  3. In the clone:  docker compose up -d   ->  http://localhost:3080"
}

Write-Host ""
Write-Host "Cost meter: http://localhost:$Port/   |   raw JSON: http://localhost:$Port/meter" -ForegroundColor Green

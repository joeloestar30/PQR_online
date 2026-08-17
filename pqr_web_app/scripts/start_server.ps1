param(
    [string]$AppHost = "0.0.0.0",
    [int]$Port = 8000,
    [string]$DbPath = "D:\PQR\data\pqr.db",
    [string]$LogDir = "D:\PQR\logs",
    [switch]$Production
)

$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $AppDir ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Python virtual environment not found at $Python. Run the local setup first."
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $DbPath) | Out-Null
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$env:PQR_HOST = $AppHost
$env:PQR_PORT = [string]$Port
$env:PQR_SQLITE_PATH = $DbPath

if ($Production) {
    $env:FLASK_ENV = "production"
    if (-not $env:SECRET_KEY -or $env:SECRET_KEY.Length -lt 32) {
        throw "Set SECRET_KEY to at least 32 characters before using -Production."
    }
    if (-not $env:PQR_ADMIN_PASSWORD -or $env:PQR_ADMIN_PASSWORD.Length -lt 12) {
        throw "Set PQR_ADMIN_PASSWORD to at least 12 characters before first production start."
    }
} else {
    $env:FLASK_ENV = "development"
}

$serverLog = Join-Path $LogDir "server.log"
$serverErr = Join-Path $LogDir "server.err"
$args = "`"$AppDir\run_prod.py`""

Start-Process `
    -FilePath $Python `
    -ArgumentList $args `
    -WorkingDirectory $AppDir `
    -RedirectStandardOutput $serverLog `
    -RedirectStandardError $serverErr `
    -WindowStyle Hidden

Write-Host "PQR server started at http://$AppHost`:$Port"
Write-Host "SQLite database path: $DbPath"
Write-Host "Logs: $LogDir"

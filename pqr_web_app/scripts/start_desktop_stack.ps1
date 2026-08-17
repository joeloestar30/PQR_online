param(
    [string]$AppHost = "0.0.0.0",
    [int]$Port = 8000,
    [string]$DbPath = "D:\PQR\data\pqr.db",
    [string]$LogDir = "D:\PQR\logs",
    [switch]$Production
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

& (Join-Path $ScriptDir "start_server.ps1") `
    -AppHost $AppHost `
    -Port $Port `
    -DbPath $DbPath `
    -LogDir $LogDir `
    -Production:$Production

& (Join-Path $ScriptDir "start_worker.ps1") `
    -DbPath $DbPath `
    -LogDir $LogDir `
    -Production:$Production

Write-Host "PQR desktop stack is running."

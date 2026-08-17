$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$pattern = "*" + $AppDir.Replace("\", "\\") + "*run_prod.py*"

$targets = Get-CimInstance Win32_Process -Filter "name = 'python.exe' or name = 'pythonw.exe'" |
    Where-Object { $_.CommandLine -like $pattern -or $_.CommandLine -like "*pqr_web_app*run_prod.py*" }

foreach ($process in $targets) {
    Stop-Process -Id $process.ProcessId -ErrorAction SilentlyContinue
}

Write-Host "Stopped $($targets.Count) PQR server process(es)."

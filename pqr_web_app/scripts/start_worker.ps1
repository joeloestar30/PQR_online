param(
    [string]$DbPath = "",
    [string]$LogDir = "",
    [switch]$Production
)

$AppDir = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $AppDir ".venv\Scripts\python.exe"
$Worker = Join-Path $AppDir "run_worker.py"
$PidFile = Join-Path $AppDir "worker.pid"

function Get-WorkerFromPidFile {
    if (-not (Test-Path $PidFile)) {
        return $null
    }

    try {
        $PidText = (Get-Content -Path $PidFile -TotalCount 1).Trim()
        if (-not $PidText) {
            Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
            return $null
        }
        $WorkerPid = [int]$PidText
        if ($WorkerPid -le 0) {
            Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
            return $null
        }
        return Get-Process -Id $WorkerPid -ErrorAction SilentlyContinue
    } catch {
        Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
        return $null
    }
}

function Get-WorkerFromCommandLine {
    try {
        return Get-CimInstance Win32_Process -ErrorAction Stop |
            Where-Object { $_.Name -like "python*" -and $_.CommandLine -match "run_worker\.py" }
    } catch {
        Write-Warning "Could not inspect Python command lines: $($_.Exception.Message)"
        return $null
    }
}

function Start-WorkerProcess {
    try {
        return Start-Process -FilePath $Python `
            -ArgumentList "`"$Worker`"" `
            -WorkingDirectory $AppDir `
            -WindowStyle Hidden `
            -RedirectStandardOutput $OutLog `
            -RedirectStandardError $ErrLog `
            -PassThru `
            -ErrorAction Stop
    } catch {
        Write-Warning "Start-Process failed: $($_.Exception.Message)"
    }

    $FallbackLog = Join-Path $AppDir "worker-launcher.log"
    $Launcher = @"
import contextlib
import os
import runpy
import sys

os.chdir(r'''$AppDir''')
sys.argv = [r'''$Worker''']

with open(r'''$OutLog''', 'a', encoding='utf-8') as stdout, open(r'''$ErrLog''', 'a', encoding='utf-8') as stderr:
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        runpy.run_path(r'''$Worker''', run_name='__main__')
"@

    Set-Content -Path $FallbackLog -Value $Launcher -Encoding UTF8

    $ProcessInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $ProcessInfo.FileName = $Python
    $ProcessInfo.Arguments = "`"$FallbackLog`""
    $ProcessInfo.WorkingDirectory = $AppDir
    $ProcessInfo.CreateNoWindow = $true
    $ProcessInfo.UseShellExecute = $false
    return [System.Diagnostics.Process]::Start($ProcessInfo)
}

if ($DbPath) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $DbPath) | Out-Null
    $env:PQR_SQLITE_PATH = $DbPath
}

if ($Production) {
    $env:FLASK_ENV = "production"
}

if ($LogDir) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    $OutLog = Join-Path $LogDir "worker.log"
    $ErrLog = Join-Path $LogDir "worker.err"
} else {
    $OutLog = Join-Path $AppDir "worker.log"
    $ErrLog = Join-Path $AppDir "worker.err"
}

$Existing = Get-WorkerFromPidFile
if (-not $Existing) {
    $Existing = Get-WorkerFromCommandLine
}

if ($Existing) {
    Write-Host "PQR worker is already running."
    $Existing | Select-Object Id, ProcessId, CommandLine
    exit 0
}

$Process = Start-WorkerProcess
if (-not $Process) {
    Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
    throw "Failed to start PQR worker."
}

Set-Content -Path $PidFile -Value $Process.Id -Encoding ASCII

Start-Sleep -Seconds 2
Write-Host "Worker logs: $OutLog"
if ($DbPath) {
    Write-Host "Worker SQLite database path: $DbPath"
}
Get-WorkerFromPidFile | Select-Object Id, ProcessName, StartTime, Path

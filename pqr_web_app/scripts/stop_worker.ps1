$AppDir = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $AppDir "worker.pid"

$Workers = @()
if (Test-Path $PidFile) {
    try {
        $PidText = (Get-Content -Path $PidFile -TotalCount 1).Trim()
        if ($PidText) {
            $WorkerPid = [int]$PidText
            if ($WorkerPid -gt 0) {
                $Worker = Get-Process -Id $WorkerPid -ErrorAction SilentlyContinue
                if ($Worker) {
                    $Workers += $Worker
                }
            }
        }
    } catch {
        Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
    }
}

if (-not $Workers) {
    try {
        $Workers = Get-CimInstance Win32_Process -ErrorAction Stop |
            Where-Object { $_.Name -like "python*" -and $_.CommandLine -match "run_worker\.py" }
    } catch {
        Write-Warning "Could not inspect Python command lines: $($_.Exception.Message)"
        $Workers = @()
    }
}

if (-not $Workers) {
    Write-Host "No PQR worker is running."
    Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
    exit 0
}

foreach ($Worker in $Workers) {
    $WorkerPid = if ($Worker.ProcessId) { $Worker.ProcessId } else { $Worker.Id }
    Stop-Process -Id $WorkerPid -Force
    Write-Host "Stopped PQR worker PID $WorkerPid."
}

Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue

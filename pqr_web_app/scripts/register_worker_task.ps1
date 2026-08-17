param(
    [string]$DbPath = "",
    [string]$LogDir = "",
    [switch]$Production
)

$ErrorActionPreference = "Stop"

$TaskName = "PQR Background Worker"
$AppDir = Split-Path -Parent $PSScriptRoot
$StartScript = Join-Path $AppDir "scripts\start_worker.ps1"
$UserId = "$env:USERDOMAIN\$env:USERNAME"

if (-not (Test-Path $StartScript)) {
    Write-Error "Worker start script was not found: $StartScript"
    exit 1
}

$StartArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`""
if ($DbPath) {
    $StartArgs += " -DbPath `"$DbPath`""
}
if ($LogDir) {
    $StartArgs += " -LogDir `"$LogDir`""
}
if ($Production) {
    $StartArgs += " -Production"
}

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $StartArgs
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Principal = New-ScheduledTaskPrincipal `
    -UserId $UserId `
    -LogonType Interactive `
    -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Principal $Principal `
        -Settings $Settings `
        -Description "Starts the PQR background worker at logon so PHIVOLCS sync runs automatically." `
        -Force `
        -ErrorAction Stop | Out-Null

    Write-Host "Registered scheduled task '$TaskName'."
} catch {
    $StartupDir = [Environment]::GetFolderPath("Startup")
    $StartupCommand = Join-Path $StartupDir "Start PQR Background Worker.cmd"
    $Command = "@echo off`r`npowershell.exe $StartArgs`r`n"
    Set-Content -Path $StartupCommand -Value $Command -Encoding ASCII
    Write-Warning "Scheduled task registration failed: $($_.Exception.Message)"
    Write-Host "Created Startup launcher instead: $StartupCommand"
}

Write-Host "Starting worker now..."
& $StartScript -DbPath $DbPath -LogDir $LogDir -Production:$Production

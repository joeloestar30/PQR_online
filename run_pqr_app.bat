@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "APP_DIR=%PROJECT_DIR%pqr_web_app"
set "PYTHON=%APP_DIR%\.venv\Scripts\python.exe"
set "DB_PATH=D:\PQR\data\pqr.db"
set "LOG_DIR=D:\PQR\logs"

echo.
echo ========================================
echo   PQR App Launcher
echo ========================================
echo.

if not exist "%PYTHON%" (
  echo ERROR: Python virtual environment was not found:
  echo %PYTHON%
  echo.
  echo Please check that pqr_web_app\.venv exists.
  pause
  exit /b 1
)

echo Stopping old PQR app processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$appDir = '%APP_DIR%';" ^
  "$old = Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -and (($_.CommandLine -like '*run_dev.py*') -or ($_.CommandLine -like '*run_prod.py*') -or ($_.CommandLine -like '*run_worker.py*')) -and ($_.CommandLine -like ('*' + $appDir + '*') -or $_.ExecutablePath -like ($appDir + '*')) };" ^
  "foreach ($proc in $old) { try { Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop; Write-Host ('Stopped old PQR process PID ' + $proc.ProcessId) } catch {} }"

echo Stopping any remaining listeners on ports 5001 and 8000...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":5001 .*LISTENING" /C:":8000 .*LISTENING"') do (
  taskkill /PID %%P /F >nul 2>nul
)

timeout /t 2 /nobreak >nul

echo Starting development server on http://127.0.0.1:5001 ...
start "PQR 5001" /min /D "%APP_DIR%" "%PYTHON%" "%APP_DIR%\run_dev.py"

echo Starting main server on http://127.0.0.1:8000 ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%APP_DIR%\scripts\start_server.ps1" -AppHost 0.0.0.0 -Port 8000 -DbPath "%DB_PATH%" -LogDir "%LOG_DIR%"

echo Starting background worker for PHIVOLCS sync, Google sync, and Google Sheet import...
powershell -NoProfile -ExecutionPolicy Bypass -File "%APP_DIR%\scripts\start_worker.ps1" -DbPath "%DB_PATH%" -LogDir "%LOG_DIR%"

timeout /t 3 /nobreak >nul

echo.
echo Current PQR listeners:
netstat -ano | findstr /R /C:":5001 .*LISTENING" /C:":8000 .*LISTENING"

echo.
echo Current PQR Python processes:
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -and (($_.CommandLine -like '*run_dev.py*') -or ($_.CommandLine -like '*run_prod.py*') -or ($_.CommandLine -like '*run_worker.py*')) } | Select-Object ProcessId, CommandLine | Format-Table -AutoSize"

echo.
echo Open these URLs:
echo   http://127.0.0.1:5001
echo   http://127.0.0.1:8000
echo.
echo If one port is missing above, check:
echo   %LOG_DIR%\server.err
echo.
pause

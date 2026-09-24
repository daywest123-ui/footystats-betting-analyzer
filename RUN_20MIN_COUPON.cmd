@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ==========================================
echo  FOOTY 20-MIN COUPON ENGINE
echo ==========================================
echo.

if exist "%CD%\app\run_20min_coupon.py" goto :FOUND
for /d %%D in ("%CD%\*") do (
    if exist "%%~fD\app\run_20min_coupon.py" (
        cd /d "%%~fD"
        goto :FOUND
    )
)

echo ERROR: app\run_20min_coupon.py bulunamadi.
pause
exit /b 1

:FOUND
set "PYTHONPATH=%CD%;%PYTHONPATH%"
echo Project root: %CD%
echo.

REM One-time local dependency bootstrap.
python -c "import oddsharvester, playwright" >nul 2>&1
if errorlevel 1 (
    echo [SETUP] Installing local scraper dependencies...
    python -m pip install -r requirements-local.txt
    if errorlevel 1 (
        echo [SETUP FAILED] Python dependencies could not be installed.
        pause
        exit /b 1
    )
)

REM Playwright Chromium is required by OddsHarvester.
if not exist "%LOCALAPPDATA%\ms-playwright" (
    echo [SETUP] Installing Chromium for OddsHarvester...
    python -m playwright install chromium
    if errorlevel 1 (
        echo [SETUP FAILED] Chromium could not be installed.
        pause
        exit /b 1
    )
)

echo [ENGINE] Starting...
python -m app.run_20min_coupon
if errorlevel 1 (
    echo.
    echo ENGINE FAILED - see output above.
    pause
    exit /b 1
)

echo.
echo Report: %CD%\reports\latest_20min_coupon.md
echo JSON:   %CD%\reports\latest_20min_coupon.json
pause

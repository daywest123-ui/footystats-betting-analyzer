@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ==========================================
echo  FOOTY 20-MIN COUPON ENGINE
echo ==========================================
echo.

REM Find the project root even if the ZIP created a nested folder.
if exist "%CD%\app\run_20min_coupon.py" goto :FOUND

for /d %%D in ("%CD%\*") do (
    if exist "%%~fD\app\run_20min_coupon.py" (
        cd /d "%%~fD"
        goto :FOUND
    )
)

echo ERROR: app\run_20min_coupon.py bulunamadi.
echo.
echo Bu CMD dosyasini projenin kok klasorunden calistirin.
echo Klasorde su yapi bulunmali:
echo   app\run_20min_coupon.py
echo   app\football_data_client.py
echo   RUN_20MIN_COUPON.cmd
echo.
pause
exit /b 1

:FOUND
echo Project root: %CD%
echo.

REM Ensure Python can resolve the "app" package from the project root.
set "PYTHONPATH=%CD%;%PYTHONPATH%"

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

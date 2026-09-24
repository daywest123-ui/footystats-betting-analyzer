@echo off
setlocal
cd /d "%~dp0"
echo ==========================================
echo  FOOTY 20-MIN COUPON ENGINE
echo ==========================================
python -m app.run_20min_coupon
if errorlevel 1 (
  echo.
  echo ENGINE FAILED - see output above.
  pause
  exit /b 1
)
echo.
echo Report: reports\latest_20min_coupon.md
echo JSON:   reports\latest_20min_coupon.json
pause

@echo off
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 serve.py 0 --open
  pause
  exit /b
)
where python >nul 2>nul
if not errorlevel 1 (
  python serve.py 0 --open
  pause
  exit /b
)
echo Python 3.10 or newer is required. Install Python from python.org, then run Start.cmd again.
pause

@echo off
cd /d "%~dp0"
echo Clone public delivery source. No login required. Existing folders are preserved.
choice /C YN /N /M "Clone delivery source? [Y/N] "
if errorlevel 2 exit /b
where py >nul 2>nul
if not errorlevel 1 (
  py -3 clone_repositories.py --delivery
  pause
  exit /b
)
python clone_repositories.py --delivery
pause

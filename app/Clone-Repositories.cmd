@echo off
cd /d "%~dp0"
echo Clone public source repositories to the repos folder. Existing paths are skipped.
echo No cloned code, hooks or submodules are executed.
choice /C YN /N /M "Continue? [Y/N] "
if errorlevel 2 exit /b
where py >nul 2>nul
if not errorlevel 1 (
  py -3 clone_repositories.py
  pause
  exit /b
)
where python >nul 2>nul
if not errorlevel 1 (
  python clone_repositories.py
  pause
  exit /b
)
echo Python 3.10 or newer is required. Install manually from python.org.
pause

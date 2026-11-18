@echo off
setlocal
cd /d "%~dp0"
if exist "TouchlineLab.exe" (
    start "" "%~dp0TouchlineLab.exe"
    exit /b
)
where pythonw.exe >nul 2>nul
if not errorlevel 1 (
    start "" pythonw.exe "%~dp0desktop.py"
    exit /b
)
where pyw.exe >nul 2>nul
if not errorlevel 1 (
    start "" pyw.exe -3 "%~dp0desktop.py"
    exit /b
)
echo Open TouchlineLab.exe, or install Python 3.10 or newer to run the source.
pause

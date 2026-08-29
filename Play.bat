@echo off
rem ===========================================================================
rem  Space Harvest - one-click launcher for Windows.
rem
rem  Double-click this file to play. On first run it creates a private .venv,
rem  installs the game's dependencies into it (ursina, numpy, pillow), and
rem  launches. Nothing is installed system-wide and nothing is downloaded on
rem  later runs. Pass any setup.py flags through, e.g.  Play.bat --shortcut
rem ===========================================================================
setlocal
cd /d "%~dp0"

set "PYLAUNCH=py -3.11"
rem Fall back to plain "py" if the 3.11 launcher entry is missing.
%PYLAUNCH% --version >nul 2>&1 || set "PYLAUNCH=py"
%PYLAUNCH% --version >nul 2>&1 || set "PYLAUNCH=python"

if not exist ".venv\Scripts\python.exe" (
    echo [Space Harvest] First run - creating a private environment in .venv ...
    %PYLAUNCH% -m venv .venv
    if errorlevel 1 (
        echo.
        echo [Space Harvest] Could not create the environment.
        echo Install Python 3.11 or newer from https://www.python.org/downloads/ ^(tick
        echo "Add python.exe to PATH"^) and run this file again.
        pause
        exit /b 1
    )
    echo [Space Harvest] Installing game dependencies ^(one-time, needs internet^)...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [Space Harvest] Dependency install failed. Check your connection and retry,
        echo or run:  .venv\Scripts\python.exe -m pip install -r requirements.txt
        pause
        exit /b 1
    )
)

".venv\Scripts\python.exe" setup.py %*
if errorlevel 1 pause
endlocal

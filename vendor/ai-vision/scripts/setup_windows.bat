@echo off
REM AI Vision Lab — one-click Windows setup (Phase 25).
REM Double-click this file (or run it from a terminal) in the project
REM folder. It creates the venv, installs the dependencies, downloads
REM the vision models and runs the system check — then the app starts
REM with:  python main.py
REM
REM Honest behavior: every step prints what it does and stops with a
REM readable message on failure. Nothing is installed outside the
REM project folder except a Python from python.org (not included here).

setlocal
cd /d "%~dp0.."

echo ============================================
echo  AI VISION LAB - ONE-CLICK SETUP
echo ============================================
echo.

REM --- 1) Python 3.11+ required -----------------------------------------
set "PY=python"
%PY% --version >nul 2>nul || set "PY=py"
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 (
    echo [FAIL] Python 3.11 or newer is required.
    echo        Install it from https://www.python.org/downloads/
    echo        and enable "Add Python to PATH" during setup.
    pause
    exit /b 1
)
echo [OK] Python found:
%PY% --version

REM --- 2) Virtual environment -------------------------------------------
if exist .venv\Scripts\python.exe (
    echo [OK] Virtual environment already exists - reusing it.
) else (
    echo [..] Creating virtual environment .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo [FAIL] Could not create the virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
)

call .venv\Scripts\activate.bat

REM --- 3) Dependencies ---------------------------------------------------
echo [..] Installing dependencies (numpy, OpenCV, MediaPipe, PySide6) ...
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt
if errorlevel 1 (
    echo [FAIL] Dependency installation failed - check your internet
    echo        connection and run this script again.
    pause
    exit /b 1
)
echo [OK] Dependencies installed.

REM --- 4) Vision models (one-time download, ~26 MB) ---------------------
echo [..] Downloading vision models ...
python scripts\download_models.py
if errorlevel 1 (
    echo [WARN] Model download failed. The app downloads them on first
    echo        start too - just make sure you have internet once.
)

REM --- 5) System check ----------------------------------------------------
echo.
python main.py --check
echo.

echo ============================================
echo  SETUP COMPLETE
echo  Start the app:        python start.py
echo                    or  python main.py
echo  Guided product tour:  python main.py --demo
echo  Hardware acceptance:  scripts\accept_windows.bat
echo ============================================
pause
endlocal

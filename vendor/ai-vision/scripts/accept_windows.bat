@echo off
REM AI Vision Lab — one-click hardware acceptance (Phase 28).
REM Run this ON the target Windows machine (webcam + optional GPU /
REM Ollama / SD WebUI / ComfyUI). It does not invent results.
REM
REM What it does:
REM   1. System check          python main.py --check
REM   2. Hardware smoke        scripts\hardware_smoke.py --json smoke.json
REM   3. Acceptance (auto)     scripts\hardware_acceptance.py --auto --json acceptance.json --reports .
REM   4. Stability (2 min)     scripts\stability_probe.py --minutes 2 --json stability.json
REM   5. Merge + re-judge      scripts\hardware_acceptance.py --auto --json acceptance.json --reports .
REM
REM Then follow the printed checklist for the interactive E2E steps
REM (person in front of the camera) and the EXE/shortcut build.
REM
REM Optional flags (pass through as arguments):
REM   --minutes N          stability duration (default 2; use 10 for READY)
REM   --require-ollama     make Ollama production-relevant
REM   --require-sdwebui    make SD WebUI production-relevant
REM   --camera N           camera index for the stability probe

setlocal EnableExtensions
cd /d "%~dp0.."

set "MINUTES=2"
set "CAMERA=0"
set "EXTRA="
:parse
if "%~1"=="" goto run
if /I "%~1"=="--minutes" (
    set "MINUTES=%~2"
    shift & shift & goto parse
)
if /I "%~1"=="--camera" (
    set "CAMERA=%~2"
    shift & shift & goto parse
)
if /I "%~1"=="--require-ollama" (
    set "EXTRA=%EXTRA% --require-ollama"
    shift & goto parse
)
if /I "%~1"=="--require-sdwebui" (
    set "EXTRA=%EXTRA% --require-sdwebui"
    shift & goto parse
)
echo Unknown argument: %~1
exit /b 2

:run
if exist .venv\Scripts\python.exe (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

echo ============================================================
echo  AI VISION LAB - HARDWARE ACCEPTANCE
echo  Target machine only. Nothing is invented.
echo ============================================================
echo.

echo [1/5] System check
%PY% main.py --check
echo.

echo [2/5] Hardware smoke -^> smoke.json
%PY% scripts\hardware_smoke.py --json smoke.json
echo.

echo [3/5] Acceptance (auto; human camera steps stay UNTESTABLE)
%PY% scripts\hardware_acceptance.py --auto --json acceptance.json --reports . %EXTRA%
echo.

echo [4/5] Stability probe (%MINUTES% min, camera %CAMERA%) -^> stability.json
%PY% scripts\stability_probe.py --minutes %MINUTES% --camera %CAMERA% --json stability.json
echo.

echo [5/5] Merge reports and re-judge
%PY% scripts\hardware_acceptance.py --auto --json acceptance.json --reports . %EXTRA%
echo.

echo ============================================================
echo  NEXT STEPS (you, at the machine)
echo ============================================================
echo  1. Re-run the interactive acceptance for the 20 E2E steps:
echo       python scripts\hardware_acceptance.py --json acceptance.json --reports .
echo  2. For a production READY verdict run stability for 10 minutes:
echo       python scripts\stability_probe.py --minutes 10 --camera 0 --json stability.json
echo  3. Build the Windows EXE + desktop shortcut:
echo       packaging\windows.bat
echo       powershell -ExecutionPolicy Bypass -File scripts\create_shortcut.ps1
echo  4. Confirm READY:
echo       python scripts\hardware_acceptance.py --json acceptance.json --reports .
echo       python scripts\release_gate.py
echo.
echo  Printed checklist: scripts\acceptance_checklist.txt
echo ============================================================
pause
endlocal

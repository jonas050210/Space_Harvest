@echo off
REM AI Vision Lab — Windows build + shortcut helper.
REM Run from the project root on Windows 11 with the venv activated.
setlocal

echo === AI Vision Lab build ===
where python >nul 2>nul || (echo ERROR: python not found & exit /b 1)

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
    echo ERROR: Python 3.11 or newer is required.
    exit /b 1
)

echo [1/3] Installing build dependencies...
pip install -r packaging\requirements-build.txt || exit /b 1

echo [2/3] Building with PyInstaller (onedir)...
pyinstaller --noconfirm --clean packaging\windows.spec || exit /b 1

echo [3/3] Done.
echo.
echo Executable: dist\AI-Vision-Lab\AI-Vision-Lab.exe
echo Vision models are downloaded automatically on first start.
echo Create a desktop shortcut with:
echo     powershell -ExecutionPolicy Bypass -File scripts\create_shortcut.ps1
endlocal

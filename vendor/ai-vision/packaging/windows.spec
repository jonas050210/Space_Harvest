# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for AI Vision Lab (Windows target).

Build (on Windows 11, from the project root):

    pip install -r packaging/requirements-build.txt
    pyinstaller --noconfirm --clean packaging/windows.spec

Output: dist/AI-Vision-Lab/AI-Vision-Lab.exe (onedir — keeps startup fast;
a onefile build with MediaPipe would unpack hundreds of MB on every start).

* Assets are bundled (app icon, demo images).
* Vision models are bundled IF data/models/ exists next to the spec
  (a prepared offline build). Otherwise the app downloads them on first
  start into its data/ directory (ModelManager), or you can copy them
  from data/models/ next to the exe.
* Ollama / SD WebUI are external local services and are never bundled.
* The API key (AI_VISION_LAB_API_KEY) is an environment variable and is
  never written into the build.
"""

from pathlib import Path

ROOT = Path.cwd()

datas = [
    (str(ROOT / "assets"), "assets"),
]

# Optional: bundle already-downloaded vision models for offline installs.
models_dir = ROOT / "data" / "models"
if models_dir.is_dir() and any(models_dir.iterdir()):
    datas.append((str(models_dir), "data" / "models"))

hiddenimports = [
    "mediapipe",
    "mediapipe.tasks.python",
    "mediapipe.tasks.python.vision",
    "mediapipe.tasks.python.components.containers",
    "cv2",
    "numpy",
]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "PyInstaller"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AI-Vision-Lab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "assets" / "app_icon.png")
    if (ROOT / "assets" / "app_icon.png").exists()
    else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="AI-Vision-Lab",
)

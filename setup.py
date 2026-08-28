#!/usr/bin/env python3
"""Space Harvest — install deps, desktop shortcut, and Windows EXE build.

This is the owner-facing entry the original asteroid-colony used. It does
**not** compile machine code by itself: it drives **PyInstaller**, which freezes
the Python game + Ursina/Panda3D into ``dist/SpaceHarvest.exe`` (or a folder).

How the EXE works
-----------------
1. ``pip install -r requirements.txt`` pulls runtime deps (and pyinstaller).
2. ``python setup.py --build`` runs PyInstaller on ``start.py``.
3. PyInstaller bundles the interpreter, your ``src/`` package, ``assets/``,
   and native Panda3D libs into one folder or one file.
4. On a Windows 11 box the player double-clicks ``SpaceHarvest.exe`` — no
   Python install required.

You cannot hand-write a PE executable in this repo; PyInstaller *generates*
it on a machine that has Python. Build on Windows for a Windows EXE
(cross-building from Linux to Windows needs a Windows wine/CI host).

Usage
-----
    python setup.py                  # deps only
    python setup.py --build          # deps + PyInstaller onedir build
    python setup.py --build --onefile
    python setup.py --shortcut       # Windows desktop .lnk (PowerShell)
    python setup.py --build --shortcut
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, cwd=PROJECT_DIR)


def install_deps() -> None:
    print("[setup] Installing dependencies...")
    _run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    _run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    # Ensure packager is present even if requirements pin is skipped.
    _run([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0.0"])


def get_desktop_path() -> str:
    """Resolve Desktop (OneDrive-aware on Windows)."""
    if sys.platform.startswith("win"):
        try:
            cmd = [
                "powershell", "-NoProfile", "-Command",
                "Write-Host ([System.Environment]::GetFolderPath('Desktop'))",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            desktop = (result.stdout or "").strip()
            if desktop:
                return desktop
        except Exception:
            pass
        up = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        return os.path.join(up, "Desktop")
    return os.path.join(os.path.expanduser("~"), "Desktop")


def create_shortcut(target_name: str = "SpaceHarvest") -> None:
    desktop = get_desktop_path()
    os.makedirs(desktop, exist_ok=True)
    onedir = os.path.join(PROJECT_DIR, "dist", target_name, f"{target_name}.exe")
    onefile = os.path.join(PROJECT_DIR, "dist", f"{target_name}.exe")
    if os.path.isfile(onedir):
        target_path = onedir
    elif os.path.isfile(onefile):
        target_path = onefile
    else:
        # Dev fallback: launch via Python.
        target_path = sys.executable
        args = f'"{os.path.join(PROJECT_DIR, "start.py")}"'
        print("[setup] No EXE yet — shortcut will run start.py with this Python.")
    if os.path.isfile(onedir) or os.path.isfile(onefile):
        args = ""
    else:
        args = f'"{os.path.join(PROJECT_DIR, "start.py")}"'

    shortcut_path = os.path.join(desktop, f"{target_name}.lnk")
    if not sys.platform.startswith("win"):
        # POSIX: write a .desktop file instead.
        desktop_file = os.path.join(desktop, f"{target_name}.desktop")
        exe = onedir if os.path.isfile(onedir) else (
            onefile if os.path.isfile(onefile) else f"{sys.executable} {os.path.join(PROJECT_DIR, 'start.py')}"
        )
        with open(desktop_file, "w", encoding="utf-8") as fh:
            fh.write(
                "[Desktop Entry]\n"
                f"Name=Space Harvest\n"
                f"Exec={exe}\n"
                f"Path={PROJECT_DIR}\n"
                "Type=Application\n"
                "Categories=Game;\n"
            )
        os.chmod(desktop_file, 0o755)
        print(f"[setup] Desktop entry: {desktop_file}")
        return

    ps_script = f'''
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
$Shortcut.TargetPath = "{target_path}"
$Shortcut.Arguments = {repr(args)}
$Shortcut.WorkingDirectory = "{PROJECT_DIR if not (os.path.isfile(onedir) or os.path.isfile(onefile)) else os.path.dirname(target_path)}"
$Shortcut.Description = "Space Harvest — orbital farming on real launch windows"
$Shortcut.IconLocation = "{target_path},0"
$Shortcut.Save()
'''
    tmp = os.path.join(PROJECT_DIR, "_tmp_create_sc.ps1")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(ps_script)
    try:
        subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", tmp],
            cwd=PROJECT_DIR, capture_output=True, text=True, timeout=20,
        )
        print(f"[setup] Shortcut created: {shortcut_path} -> {target_path}")
    finally:
        if os.path.isfile(tmp):
            os.remove(tmp)


def build_exe(onefile: bool = False) -> str:
    """Freeze Space Harvest with PyInstaller. Returns output path."""
    sys.path.insert(0, PROJECT_DIR)
    from src.config import EXECUTABLE_NAME, GAME_NAME, GAME_VERSION, STEAM_APP_ID

    name = EXECUTABLE_NAME
    print(f"[setup] Building {GAME_NAME} v{GAME_VERSION} ({name}) with PyInstaller...")
    # Prefer the dedicated steam builder (keeps one code path).
    cmd = [sys.executable, os.path.join("scripts", "build_steam.py")]
    if onefile:
        cmd.append("--onefile")
    try:
        _run(cmd)
    except subprocess.CalledProcessError:
        print("[setup] scripts/build_steam.py failed — falling back to inline PyInstaller.")
        _inline_pyinstaller(name, onefile=onefile)

    # Write steam sidecars if the steam builder did not.
    out_dir = os.path.join(PROJECT_DIR, "dist", name)
    out_one = os.path.join(PROJECT_DIR, "dist", f"{name}.exe")
    if os.path.isdir(out_dir):
        app_id = os.path.join(out_dir, "steam_appid.txt")
        if not os.path.isfile(app_id):
            with open(app_id, "w", encoding="utf-8") as fh:
                fh.write(str(STEAM_APP_ID or 480))
        print(f"[setup] EXE folder ready: {out_dir}")
        return out_dir
    if os.path.isfile(out_one):
        print(f"[setup] EXE ready: {out_one}")
        return out_one
    print("[setup] WARNING: build finished but no EXE was found under dist/.")
    return os.path.join(PROJECT_DIR, "dist")


def _inline_pyinstaller(name: str, onefile: bool = False) -> None:
    sep = ";" if sys.platform.startswith("win") else ":"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        f"--name={name}",
        "--paths", PROJECT_DIR,
        "--hidden-import=ursina",
        "--hidden-import=panda3d",
        "--hidden-import=numpy",
        "--hidden-import=PIL",
        "--hidden-import=src.main",
        "--hidden-import=src.config",
        "--collect-all", "ursina",
        "--collect-all", "panda3d",
        "--add-data", f"assets{sep}assets",
        "--add-data", f"src{sep}src",
    ]
    if sys.platform.startswith("win"):
        cmd.append("--windowed")
    cmd.append("--onefile" if onefile else "--onedir")
    cmd.append(os.path.join(PROJECT_DIR, "start.py"))
    _run(cmd)


def run_tests() -> int:
    print("[setup] Running test suite...")
    return subprocess.call(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=PROJECT_DIR,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Space Harvest setup — deps, EXE build, desktop shortcut",
    )
    parser.add_argument("--build", action="store_true",
                        help="build SpaceHarvest.exe with PyInstaller")
    parser.add_argument("--onefile", action="store_true",
                        help="single-file EXE (slower startup; use with --build)")
    parser.add_argument("--shortcut", action="store_true",
                        help="create a desktop shortcut / .desktop entry")
    parser.add_argument("--test", action="store_true",
                        help="run pytest after installing deps")
    parser.add_argument("--skip-deps", action="store_true",
                        help="do not pip install (use existing venv)")
    args = parser.parse_args()

    if not args.skip_deps:
        try:
            install_deps()
        except Exception as exc:
            print(f"[setup] WARNING: pip install failed: {exc}")

    rc = 0
    if args.test:
        rc = run_tests()
        if rc != 0:
            print("[setup] Tests failed — aborting build.")
            return rc

    if args.build:
        try:
            build_exe(onefile=args.onefile)
        except Exception as exc:
            print(f"[setup] Build failed: {exc}")
            return 1

    if args.shortcut or (args.build and sys.platform.startswith("win")):
        try:
            create_shortcut()
        except Exception as exc:
            print(f"[setup] Shortcut skipped: {exc}")

    if not any((args.build, args.shortcut, args.test)):
        print("[setup] Dependencies installed.")
        print("  Play:            python start.py")
        print("  Or:              python -m src.main")
        print("  Build EXE:       python setup.py --build")
        print("  Build + tests:   python setup.py --test --build")
        print("  See STEAM.md / README.md for depot packaging.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

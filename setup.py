#!/usr/bin/env python3
"""Space Harvest — one entry for play, shortcut, tests, and EXE build.

Default (no flags): install deps if needed and **launch the game**.

    python setup.py                 # play
    python setup.py --shortcut      # desktop icon that runs setup.py
    python setup.py --build         # PyInstaller → dist/SpaceHarvest/
    python setup.py --build --onefile
    python setup.py --test          # pytest
    python setup.py --test --build  # verify then freeze

Windows owner flow
------------------
1. ``py -3.11 -m venv .venv``
2. ``.\\venv\\Scripts\\python setup.py --shortcut``
3. Double-click **Space Harvest** on the Desktop forever after.

The shortcut targets this ``setup.py`` (or the built EXE once ``--build`` has
run). There is no separate ``start.py``.

EXE note: PyInstaller generates the binary on a machine with Python. Build on
Windows 11 for a Windows EXE.
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


def _ensure_path() -> None:
    if PROJECT_DIR not in sys.path:
        sys.path.insert(0, PROJECT_DIR)
    os.chdir(PROJECT_DIR)


def install_deps() -> None:
    print("[setup] Installing dependencies...")
    _run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    req = os.path.join(PROJECT_DIR, "requirements.txt")
    if os.path.isfile(req):
        _run([sys.executable, "-m", "pip", "install", "-r", req])
    _run([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0.0"])


def get_desktop_path() -> str:
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


def _exe_paths(name: str = "SpaceHarvest") -> tuple[str | None, str | None]:
    onedir = os.path.join(PROJECT_DIR, "dist", name, f"{name}.exe")
    onefile = os.path.join(PROJECT_DIR, "dist", f"{name}.exe")
    # Linux binary names without .exe
    onedir_nix = os.path.join(PROJECT_DIR, "dist", name, name)
    onefile_nix = os.path.join(PROJECT_DIR, "dist", name)
    if os.path.isfile(onedir):
        return onedir, os.path.dirname(onedir)
    if os.path.isfile(onedir_nix):
        return onedir_nix, os.path.dirname(onedir_nix)
    if os.path.isfile(onefile):
        return onefile, PROJECT_DIR
    if os.path.isfile(onefile_nix) and os.access(onefile_nix, os.X_OK):
        return onefile_nix, PROJECT_DIR
    return None, None


def create_shortcut(target_name: str = "SpaceHarvest") -> None:
    """Desktop shortcut → EXE if built, else ``python setup.py`` (play)."""
    desktop = get_desktop_path()
    os.makedirs(desktop, exist_ok=True)
    _ensure_path()
    try:
        from src.config import EXECUTABLE_NAME, GAME_NAME
        target_name = EXECUTABLE_NAME
        label = GAME_NAME
    except Exception:
        label = "Space Harvest"

    exe, work = _exe_paths(target_name)
    setup_py = os.path.join(PROJECT_DIR, "setup.py")

    if exe:
        target_path, arguments, workdir = exe, "", work or PROJECT_DIR
        print(f"[setup] Shortcut → built EXE {exe}")
    else:
        target_path = sys.executable
        arguments = f'"{setup_py}"'
        workdir = PROJECT_DIR
        print("[setup] Shortcut → python setup.py (play). Run --build later for a real EXE icon.")

    if not sys.platform.startswith("win"):
        desktop_file = os.path.join(desktop, f"{target_name}.desktop")
        if exe:
            exec_line = exe
        else:
            exec_line = f"{sys.executable} {setup_py}"
        with open(desktop_file, "w", encoding="utf-8") as fh:
            fh.write(
                "[Desktop Entry]\n"
                f"Name={label}\n"
                f"Exec={exec_line}\n"
                f"Path={workdir}\n"
                "Type=Application\n"
                "Categories=Game;\n"
                "Terminal=false\n"
            )
        os.chmod(desktop_file, 0o755)
        print(f"[setup] Desktop entry: {desktop_file}")
        return

    shortcut_path = os.path.join(desktop, f"{label}.lnk")
    ps_script = f'''
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
$Shortcut.TargetPath = "{target_path}"
$Shortcut.Arguments = {repr(arguments)}
$Shortcut.WorkingDirectory = "{workdir}"
$Shortcut.Description = "{label} — orbital farming on real launch windows"
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
        print(f"[setup] Shortcut created: {shortcut_path}")
    finally:
        if os.path.isfile(tmp):
            os.remove(tmp)


def build_exe(onefile: bool = False) -> str:
    _ensure_path()
    from src.config import EXECUTABLE_NAME, GAME_NAME, GAME_VERSION, STEAM_APP_ID

    name = EXECUTABLE_NAME
    print(f"[setup] Building {GAME_NAME} v{GAME_VERSION} ({name})...")

    pack = os.path.join(PROJECT_DIR, "packaging", "build_exe.py")
    if os.path.isfile(pack):
        cmd = [sys.executable, pack]
        if onefile:
            cmd.append("--onefile")
        try:
            _run(cmd)
        except subprocess.CalledProcessError:
            print("[setup] packaging builder failed — inline PyInstaller fallback.")
            _inline_pyinstaller(name, onefile=onefile)
    else:
        _inline_pyinstaller(name, onefile=onefile)

    out_dir = os.path.join(PROJECT_DIR, "dist", name)
    if os.path.isdir(out_dir):
        app_id = os.path.join(out_dir, "steam_appid.txt")
        if not os.path.isfile(app_id):
            with open(app_id, "w", encoding="utf-8") as fh:
                fh.write(str(STEAM_APP_ID or 480))
        print(f"[setup] Ready: {out_dir}")
        return out_dir
    out_one = os.path.join(PROJECT_DIR, "dist", f"{name}.exe")
    if os.path.isfile(out_one):
        print(f"[setup] Ready: {out_one}")
        return out_one
    print("[setup] WARNING: no EXE under dist/ — see PyInstaller log.")
    return os.path.join(PROJECT_DIR, "dist")


def _inline_pyinstaller(name: str, onefile: bool = False) -> None:
    sep = ";" if sys.platform.startswith("win") else ":"
    # Entry is setup.py itself with a frozen play path — use a tiny launcher module.
    launcher = os.path.join(PROJECT_DIR, "packaging", "play_entry.py")
    if not os.path.isfile(launcher):
        os.makedirs(os.path.dirname(launcher), exist_ok=True)
        with open(launcher, "w", encoding="utf-8") as fh:
            fh.write(
                "from src.app import run_game\n"
                "raise SystemExit(run_game())\n"
            )
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
        "--hidden-import=src.ops",
        "--hidden-import=src.ops.simulation",
        "--hidden-import=src.colony",
        "--collect-all", "ursina",
        "--collect-all", "panda3d",
        "--add-data", f"assets{sep}assets",
        "--add-data", f"src{sep}src",
    ]
    if sys.platform.startswith("win"):
        cmd.append("--windowed")
    cmd.append("--onefile" if onefile else "--onedir")
    cmd.append(launcher)
    _run(cmd)


def run_tests() -> int:
    print("[setup] Running tests...")
    return subprocess.call(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=PROJECT_DIR,
    )


def play() -> int:
    """Default action: run the game."""
    _ensure_path()
    from src.app import run_game

    return run_game()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Space Harvest — play (default), shortcut, test, or build EXE",
    )
    parser.add_argument("--build", action="store_true", help="build SpaceHarvest with PyInstaller")
    parser.add_argument("--onefile", action="store_true", help="single-file EXE (with --build)")
    parser.add_argument("--shortcut", action="store_true", help="create desktop shortcut")
    parser.add_argument("--test", action="store_true", help="run pytest")
    parser.add_argument("--skip-deps", action="store_true", help="do not pip install")
    parser.add_argument(
        "--install-only", action="store_true",
        help="only install deps, do not play",
    )
    # Pass-through game flags after -- 
    args, game_argv = parser.parse_known_args()

    if not args.skip_deps and (args.build or args.install_only or args.test):
        try:
            install_deps()
        except Exception as exc:
            print(f"[setup] WARNING: pip install failed: {exc}")

    if args.test:
        rc = run_tests()
        if rc != 0:
            print("[setup] Tests failed.")
            return rc
        if not args.build and not args.shortcut and not args.install_only:
            return 0

    if args.build:
        try:
            build_exe(onefile=args.onefile)
        except Exception as exc:
            print(f"[setup] Build failed: {exc}")
            return 1
        # After build, refresh shortcut to point at EXE
        try:
            create_shortcut()
        except Exception as exc:
            print(f"[setup] Shortcut after build skipped: {exc}")
        return 0

    if args.shortcut:
        try:
            if not args.skip_deps:
                try:
                    install_deps()
                except Exception:
                    pass
            create_shortcut()
        except Exception as exc:
            print(f"[setup] Shortcut failed: {exc}")
            return 1
        return 0

    if args.install_only:
        if not args.skip_deps:
            install_deps()
        print("[setup] Dependencies ready.")
        print("  Play:      python setup.py")
        print("  Shortcut:  python setup.py --shortcut")
        print("  EXE:       python setup.py --build")
        return 0

    # Default: PLAY
    if game_argv:
        # e.g. python setup.py --headless --sim-days 100
        _ensure_path()
        from src.app import run_game
        return run_game(game_argv)
    return play()


if __name__ == "__main__":
    raise SystemExit(main())

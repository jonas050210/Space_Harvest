#!/usr/bin/env python3
"""Build a Steam-ready Windows / Linux package for Space Harvest.

Usage (from repo root, inside the venv):

    python packaging/build_exe.py (or setup.py --build)              # one-folder build into dist/
    python packaging/build_exe.py (or setup.py --build) --onefile    # single executable (slower start)

Produces:
    dist/SpaceHarvest/                 # ship this folder as the depot
        SpaceHarvest[.exe]
        steam_appid.txt
        steam_install.json
        assets/
        ...

Target hardware:
    i7-12700F / 32 GB DDR4 / RTX 4060 Ti 8 GB -- Ultra preset
    Minimum: any DX11 / GL 3.3 box -- Low preset
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)


def build(onefile: bool = False) -> str:
    sys.path.insert(0, ROOT)
    from src.config import EXECUTABLE_NAME, GAME_NAME, GAME_VERSION, STEAM_APP_ID

    name = EXECUTABLE_NAME
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        _run([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0.0"])

    work = os.path.join(DIST, "_work")
    spec_dist = os.path.join(DIST, "_pyi")
    os.makedirs(DIST, exist_ok=True)

    # packaging/play_entry.py is the frozen entry (resolves assets next to the EXE).
    entry = os.path.join(ROOT, "packaging", "play_entry.py")
    # PyInstaller --add-data separator is ";" on Windows, ":" elsewhere
    sep = ";" if sys.platform.startswith("win") else ":"
    add_data = [
        f"assets{sep}assets",
        f"src{sep}src",
    ]
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        f"--name={name}",
        f"--distpath={spec_dist}",
        f"--workpath={work}",
        "--paths", ROOT,
        "--hidden-import=ursina",
        "--hidden-import=panda3d",
        "--hidden-import=numpy",
        "--hidden-import=PIL",
        "--hidden-import=src.main",
        "--hidden-import=src.ops",
        "--hidden-import=src.ops.simulation",
        "--hidden-import=src.colony",
        "--hidden-import=src.colony.savegame",
        "--hidden-import=src.colony.state",
        "--hidden-import=src.app",
        "--hidden-import=src.app.audio",
        "--hidden-import=src.app.controls",
        "--hidden-import=src.config",
        "--hidden-import=src.config.units",
        "--hidden-import=src.config.ships",
        "--hidden-import=src.config.mining",
        "--hidden-import=src.config.market",
        "--hidden-import=src.config.crew",
        "--hidden-import=src.config.life",
        "--hidden-import=src.config.parts",
        "--hidden-import=src.config.depot",
        "--hidden-import=src.config.campaign",
        "--hidden-import=src.config.difficulty",
        "--hidden-import=src.config.quality",
        "--hidden-import=src.config.game",
        "--hidden-import=src.routes",
        "--hidden-import=src.mining",
        "--hidden-import=src.market",
        "--collect-all", "ursina",
        "--collect-all", "panda3d",
    ]
    if sys.platform.startswith("win"):
        cmd.append("--windowed")
    for item in add_data:
        cmd += ["--add-data", item]
    cmd.append("--onefile" if onefile else "--onedir")
    cmd.append(entry)
    _run(cmd)

    built = os.path.join(
        spec_dist,
        name if not onefile else (f"{name}.exe" if sys.platform.startswith("win") else name),
    )
    out_dir = os.path.join(DIST, name)
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    if onefile:
        os.makedirs(out_dir, exist_ok=True)
        shutil.copy2(built, out_dir)
    else:
        shutil.copytree(built, out_dir)

    from src.steam_bridge import write_steam_manifest

    app_id_path = os.path.join(out_dir, "steam_appid.txt")
    with open(app_id_path, "w", encoding="utf-8") as fh:
        fh.write(str(STEAM_APP_ID or 480))  # 480 = Spacewar test app if unset
    write_steam_manifest(out_dir)

    assets_src = os.path.join(ROOT, "assets")
    assets_dst = os.path.join(out_dir, "assets")
    if os.path.isdir(assets_src) and not os.path.isdir(assets_dst):
        shutil.copytree(assets_src, assets_dst)

    readme = os.path.join(out_dir, "README_STEAM.txt")
    with open(readme, "w", encoding="utf-8") as fh:
        fh.write(
            f"{GAME_NAME}  v{GAME_VERSION}\n"
            f"{'=' * (len(GAME_NAME) + len(GAME_VERSION) + 3)}\n\n"
            f"Launch {name}.exe (Windows) or ./{name} (Linux).\n"
            "Orbital farming on real launch windows: wait for GO, harvest the belt,\n"
            "sell without flooding Earth, keep the colony iced and crewed.\n\n"
            "Graphics: Low / Medium / High / Ultra (Settings or K in-game).\n"
            "Saves: Documents/My Games/SpaceHarvest (Windows) or\n"
            "~/.local/share/SpaceHarvest (Linux) when shipped; dev uses ./saves.\n\n"
            "Recommended: i7-12700F / 16+ GB / RTX 3060+, High or Ultra.\n"
            "Minimum: dual-core / 8 GB / GTX 1050 or Intel UHD, Low.\n"
        )
    print(f"[build] Steam package ready: {out_dir}")
    return out_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--onefile", action="store_true", help="single-file executable")
    args = parser.parse_args()
    build(onefile=args.onefile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

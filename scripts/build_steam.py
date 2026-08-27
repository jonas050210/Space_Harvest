#!/usr/bin/env python3
"""Build a Steam-ready Windows / Linux package for Orbital Supply Chains.

Usage (from repo root, inside the venv):

    python scripts/build_steam.py              # one-folder build into dist/
    python scripts/build_steam.py --onefile    # single executable (slower start)

Produces:
    dist/OrbitalSupplyChains/                 # ship this folder as the depot
        OrbitalSupplyChains[.exe]
        steam_appid.txt
        steam_install.json
        assets/
        ...

Target hardware reference (from project.md):
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
NAME = "OrbitalSupplyChains"


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)


def build(onefile: bool = False) -> str:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        _run([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0.0"])

    work = os.path.join(DIST, "_work")
    spec_dist = os.path.join(DIST, "_pyi")
    os.makedirs(DIST, exist_ok=True)

    entry = os.path.join(ROOT, "src", "main.py")
    sep = os.pathsep
    add_data = [
        f"assets{sep}assets",
        f"src{sep}src",
    ]
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        f"--name={NAME}",
        f"--distpath={spec_dist}",
        f"--workpath={work}",
        "--paths", ROOT,
        "--hidden-import=ursina",
        "--hidden-import=panda3d",
        "--hidden-import=numpy",
        "--hidden-import=PIL",
        "--collect-all", "ursina",
        "--collect-all", "panda3d",
    ]
    for item in add_data:
        cmd += ["--add-data", item]
    if onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")
    cmd.append(entry)
    _run(cmd)

    built = os.path.join(spec_dist, NAME if not onefile else f"{NAME}.exe" if sys.platform.startswith("win") else NAME)
    out_dir = os.path.join(DIST, NAME)
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    if onefile:
        os.makedirs(out_dir, exist_ok=True)
        shutil.copy2(built, out_dir)
    else:
        shutil.copytree(built, out_dir)

    # Steam sidecar files.
    sys.path.insert(0, ROOT)
    from src.config import GAME_VERSION, STEAM_APP_ID
    from src.steam_bridge import write_steam_manifest

    app_id_path = os.path.join(out_dir, "steam_appid.txt")
    with open(app_id_path, "w", encoding="utf-8") as fh:
        fh.write(str(STEAM_APP_ID or 480))  # 480 = Spacewar test app if unset
    write_steam_manifest(out_dir)

    # Copy committed textures so the frozen build never regenerates on first boot.
    assets_src = os.path.join(ROOT, "assets")
    assets_dst = os.path.join(out_dir, "assets")
    if os.path.isdir(assets_src) and not os.path.isdir(assets_dst):
        shutil.copytree(assets_src, assets_dst)

    readme = os.path.join(out_dir, "README_STEAM.txt")
    with open(readme, "w", encoding="utf-8") as fh:
        fh.write(
            f"Orbital Supply Chains  v{GAME_VERSION}\n"
            "=====================================\n\n"
            "Launch OrbitalSupplyChains.exe (Windows) or ./OrbitalSupplyChains (Linux).\n"
            "Graphics presets: Low / Medium / High / Ultra (Settings menu or K in-game).\n"
            "Saves live in Documents/My Games/OrbitalSupplyChains (Windows) or\n"
            "~/.local/share/OrbitalSupplyChains (Linux) when shipped; dev builds use ./saves.\n\n"
            "Recommended: i7-12700F / 16+ GB / RTX 3060 or better, High or Ultra preset.\n"
            "Minimum: dual-core / 8 GB / GTX 1050 or Intel UHD, Low preset.\n"
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

"""Packaging metadata + one-command bootstrap for AI Vision Lab.

``python setup.py`` with no setuptools command bootstraps the project
(venv, dependencies, models, system check). That matches what people
type first on Windows (``py setup.py``).

Packaging still works:

    pip install -e .              # editable install
    python setup.py sdist         # source dist
    python setup.py egg_info      # setuptools metadata
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Keep this literal — scripts/release_gate.py greps for version="…".
_VERSION = "2.1.1"

_SETUPTOOLS_COMMANDS = {
    "alias",
    "bdist",
    "bdist_egg",
    "bdist_rpm",
    "bdist_wheel",
    "bdist_wininst",
    "build",
    "build_ext",
    "build_py",
    "check",
    "clean",
    "develop",
    "dist",
    "egg_info",
    "install",
    "install_data",
    "install_egg_info",
    "install_lib",
    "install_scripts",
    "pointer",
    "register",
    "rotate",
    "saveopts",
    "setopt",
    "sdist",
    "test",
    "upload",
}

_HELP = """
AI Vision Lab — setup

  python setup.py              Create .venv, install deps, download models
  python setup.py --dry-run    Show the plan without changing anything
  python start.py              Guided launcher (after setup)
  python main.py               Start the studio
  python main.py --check       System diagnostics only
  python main.py --demo        Guided product tour (no camera needed)

  pip install -e .             Install as a package (developers)
  pip install -r requirements.txt

If MediaPipe prints MessageFactory.GetPrototype, pin protobuf:

  pip install "protobuf>=4.25.3,<5"
"""


def is_setuptools_invocation(argv: list[str]) -> bool:
    """True when argv is a real setuptools command (sdist, egg_info, …)."""
    for arg in argv[1:]:
        if arg.startswith("-"):
            continue
        if arg in _SETUPTOOLS_COMMANDS or arg.startswith("bdist_"):
            return True
        if arg.startswith("install_"):
            return True
    return False


def _in_venv() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix) or bool(
        os.environ.get("VIRTUAL_ENV")
    )


def _venv_python(root: Path) -> Path:
    if os.name == "nt":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def bootstrap(argv: list[str] | None = None) -> int:
    """Create the venv, install requirements, fetch models, run --check."""
    args = list(sys.argv[1:] if argv is None else argv)
    if "-h" in args or "--help" in args:
        print(_HELP.strip())
        return 0
    if "--version" in args:
        print(_VERSION)
        return 0

    root = Path(__file__).resolve().parent
    dry_run = "--dry-run" in args
    print("AI Vision Lab — bootstrap")
    print(f"  project: {root}")
    print(f"  python:  {sys.executable} ({sys.version.split()[0]})")

    if sys.version_info < (3, 11):
        print("ERROR: Python 3.11 or newer is required.")
        print(f"       You are running Python {sys.version.split()[0]}.")
        return 1

    venv_python = _venv_python(root)
    if dry_run:
        print("  plan:")
        if not _in_venv():
            print(f"    - create virtual environment at {root / '.venv'}")
            print("    - re-run this script inside .venv")
        print("    - python -m pip install --upgrade pip")
        print("    - pip install -r requirements.txt")
        print("    - python scripts/download_models.py")
        print("    - python main.py --check")
        print("    - print how to start (python start.py / python main.py)")
        return 0

    if not _in_venv():
        if not venv_python.exists():
            print("[..] Creating virtual environment .venv ...")
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "venv", str(root / ".venv")]
                )
            except (OSError, subprocess.CalledProcessError) as exc:
                print(f"[FAIL] Could not create the virtual environment: {exc}")
                print("       Install Python 3.11+ from python.org and retry.")
                return 1
            print("[OK] Virtual environment created.")
        else:
            print("[OK] Virtual environment already exists — reusing it.")
        print("[..] Continuing setup inside .venv ...")
        return int(subprocess.call([str(venv_python), str(root / "setup.py"), *args]))

    requirements = root / "requirements.txt"
    print("[..] Installing dependencies (numpy, OpenCV, MediaPipe, PySide6) ...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip"]
        )
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", str(requirements)]
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"[FAIL] Dependency installation failed: {exc}")
        print("       Check your internet connection and run this again.")
        return 1
    print("[OK] Dependencies installed.")

    print("[..] Downloading vision models ...")
    model_code = subprocess.call(
        [sys.executable, str(root / "scripts" / "download_models.py")]
    )
    if model_code != 0:
        print("[WARN] Model download failed. The app downloads them on first")
        print("       start too — just make sure you have internet once.")

    print()
    subprocess.call([sys.executable, str(root / "main.py"), "--check"])
    print()
    print("============================================")
    print(" SETUP COMPLETE")
    print(" Start the app:        python start.py")
    print("                   or  python main.py")
    print(" Guided product tour:  python main.py --demo")
    print("============================================")
    return 0


def setup_package() -> None:
    from setuptools import find_packages, setup

    setup(
        name="ai-vision-lab",
        version="2.1.1",
        description=(
            "Computer vision desktop lab: live AI vision, "
            "image generation and image analysis"
        ),
        author="AI Vision Lab",
        license="MIT",
        python_requires=">=3.11",
        packages=find_packages(include=["app", "app.*"]),
        py_modules=["main"],
        include_package_data=True,
        entry_points={
            "console_scripts": [
                "ai-vision-lab=main:main",
            ],
        },
        install_requires=[
            "numpy>=1.26,<3",
            "opencv-python-headless>=4.10,<5",
            "mediapipe>=0.10.21,<0.11",
            "protobuf>=4.25.3,<5",
            "PySide6>=6.8,<7",
        ],
    )


if __name__ == "__main__":
    if is_setuptools_invocation(sys.argv):
        setup_package()
    else:
        raise SystemExit(bootstrap())
else:
    # ``pip install -e .`` may import this module; expose setuptools metadata.
    setup_package()

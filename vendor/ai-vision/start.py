"""Guided launcher: checks Python + dependencies, then starts the app.

Double-click friendly: prints a readable banner and, if a dependency is
missing or broken (including the MediaPipe/protobuf MessageFactory
mismatch), tells the user exactly what to install instead of a traceback.
"""

from __future__ import annotations

import sys

BANNER = r"""
   █████╗ ██╗    ██╗   ██╗██╗███████╗██╗ ██████╗ ███╗   ██╗
  ██╔══██╗██║    ██║   ██║██║██╔════╝██║██╔═══██╗████╗  ██║
  ███████║██║ █╗ ██║   ██║██║███████╗██║██║   ██║██╔██╗ ██║
  ██╔══██╗██║███╗╚██╗ ██╔╝██║╚════██║██║██║   ██║██║╚██╗██║
  ██║  ██║╚███╔███╗╚████╔╝ ██║███████║██║╚██████╔╝██║ ╚████║
  ╚═╝  ╚═╝ ╚══╝╚══╝  ╚═══╝  ╚═╝╚══════╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝
        A I   V I S I O N   L A B   —   L I V E   A I   S T U D I O
"""

REQUIRED_MODULES = (
    ("cv2", "opencv-python-headless"),
    ("PySide6", "PySide6"),
    ("mediapipe", "mediapipe"),
    ("numpy", "numpy"),
)


def check_dependencies() -> list[str]:
    """Return missing or broken dependency packages (import-level check).

    Applies the MediaPipe/protobuf shim first so a too-new protobuf does
    not look like a missing install. Any exception (not just ImportError)
    is treated as a broken package — AttributeError from MessageFactory
    used to slip through and crash later.
    """
    from app.utils.protobuf_compat import apply_protobuf_compat

    apply_protobuf_compat()
    missing: list[str] = []
    for module, package in REQUIRED_MODULES:
        try:
            __import__(module)
        except Exception:  # noqa: BLE001 — any import failure is "missing"
            missing.append(package)
    return missing


def check_python_version() -> bool:
    """True if the interpreter is Python 3.11 or newer."""
    return sys.version_info >= (3, 11)


def main() -> int:
    print(BANNER)

    if not check_python_version():
        print("ERROR: Python 3.11 or newer is required.")
        print(f"       You are running Python {sys.version.split()[0]}.")
        return 1

    missing = check_dependencies()
    if missing:
        print("ERROR: missing or broken dependencies detected:")
        for package in missing:
            print(f"       - {package}")
        print("\nFix it with:")
        print("       python setup.py")
        print("   or: pip install -r requirements.txt")
        if "mediapipe" in missing:
            print('       pip install "protobuf>=4.25.3,<5"')
        return 1

    from main import main as app_main  # deferred: all checks passed

    return app_main()


if __name__ == "__main__":
    sys.exit(main())

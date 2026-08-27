#!/usr/bin/env python3
"""Install dependencies, create a OneDrive-aware shortcut, and build an executable."""
import os
import sys
import subprocess
import argparse

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

def get_desktop_path():
    """Resolve a OneDrive-compatible desktop path through PowerShell."""
    try:
        ps = [
            "powershell", "-NoProfile", "-Command",
            "$env:USERPROFILE = [Environment]::GetFolderPath('Desktop'); "
            "if ([System.IO.Path]::IsPathRooted($env:USERPROFILE) -eq $false) { $env:USERPROFILE = [System.IO.Path]::Combine($env:HOME, 'Desktop') }; "
            "Write-Host $env:USERPROFILE"
        ]
        # The desktop API returns the correct folder even when OneDrive redirects it.
        cmd = [
            "powershell", "-NoProfile", "-Command",
            "Write-Host ([System.Environment]::GetFolderPath('Desktop'))"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        desktop = result.stdout.strip()
        if desktop:
            return desktop
    except Exception:
        pass
    # Fall back to USERPROFILE or HOME.
    up = os.environ.get("USERPROFILE") or os.environ.get("HOME", ".")
    return os.path.join(up, "Desktop")

def install_deps():
    print("[setup] Installing dependencies...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

def create_shortcut(target_name="AsteroidColony"):
    desktop = get_desktop_path()
    # Use start.py unless a built executable is available.
    exe_path = os.path.join(PROJECT_DIR, "start.py")
    dist_exe = os.path.join(PROJECT_DIR, "dist", "AsteroidColony.exe")
    if os.path.isfile(dist_exe):
        target_path = dist_exe
    else:
        target_path = exe_path
    shortcut_path = os.path.join(desktop, f"{target_name}.lnk")
    # PowerShell script that creates the shortcut.
    ps_script = f'''
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
$Shortcut.TargetPath = "{target_path}"
$Shortcut.Arguments = ""
$Shortcut.WorkingDirectory = "{PROJECT_DIR}"
$Shortcut.Description = "Asteroid Colony — Start 3D Game"
$Shortcut.IconLocation = "{target_path},0"
$Shortcut.Save()
'''
    with open(os.path.join(PROJECT_DIR, "_tmp_create_sc.ps1"), "w", encoding="utf-8") as f:
        f.write(ps_script)
    try:
        subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", "_tmp_create_sc.ps1"], cwd=PROJECT_DIR, capture_output=True, text=True, timeout=20)
        print(f"[setup] Shortcut created: {shortcut_path} -> {target_path}")
    finally:
        tmp = os.path.join(PROJECT_DIR, "_tmp_create_sc.ps1")
        if os.path.isfile(tmp):
            os.remove(tmp)

def build_exe():
    print("[setup] Building executable with PyInstaller...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "AsteroidColony",
        "--onefile",
        "--windowed",
        "--add-data", "game;game",
        "--collect-all", "ursina",
        "--hidden-import", "ursina.entity",
        "--hidden-import", "ursina.scene",
        "--hidden-import", "panda3d.core",
        "--hidden-import", "direct",
        "start.py",
    ]
    # PyInstaller data separators differ by platform; this configuration targets Windows.
    subprocess.check_call(cmd, cwd=PROJECT_DIR)
    print("[setup] Executable is ready in dist/.")

def main():
    parser = argparse.ArgumentParser(description="Asteroid Colony setup")
    parser.add_argument("--build", action="store_true", help="build an executable with PyInstaller")
    parser.add_argument("--shortcut", action="store_true", help="create a desktop shortcut")
    args = parser.parse_args()
    # Always install dependencies.
    try:
        install_deps()
    except Exception as e:
        print(f"Warning: pip installation failed: {e}")
    # Create the shortcut.
    try:
        create_shortcut()
    except Exception as e:
        print(f"Warning: shortcut creation failed: {e}")
    if args.build:
        build_exe()
    if not args.build and not args.shortcut:
        # Default behavior: dependencies and shortcut.
        print("[setup] Complete. Use --build for an executable or --shortcut for a new shortcut.")
    elif args.build:
        # Refresh the shortcut to target the executable after building.
        create_shortcut()

if __name__ == "__main__":
    main()

# AI Vision Lab — desktop shortcut creator (Windows).
# Usage (from the project root):
#   powershell -ExecutionPolicy Bypass -File scripts\create_shortcut.ps1
# Creates a shortcut to dist\AI-Vision-Lab\AI-Vision-Lab.exe on the Desktop.

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $root "dist\AI-Vision-Lab\AI-Vision-Lab.exe"
$icon = Join-Path $root "assets\app_icon.png"

if (-not (Test-Path $exe)) {
    Write-Host "ERROR: $exe not found." -ForegroundColor Red
    Write-Host "Run packaging\windows.bat first." -ForegroundColor Yellow
    exit 1
}

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "AI Vision Lab.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $exe
$shortcut.WorkingDirectory = Split-Path -Parent $exe
$shortcut.Description = "AI Vision Lab — Live AI Vision Studio"
if (Test-Path $icon) { $shortcut.IconLocation = "$icon,0" }
$shortcut.Save()

Write-Host "Shortcut created: $shortcutPath" -ForegroundColor Green

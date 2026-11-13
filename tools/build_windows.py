"""Build reproducible Windows x64 GUI package with PyInstaller.

Running this script on Windows is intentionally explicit. Bundles ffmpeg and
ffprobe from the build machine rather than downloading binaries at app startup.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def main():
    if sys.platform != "win32":
        raise SystemExit("Windows packaging must run on a Windows CI runner")
    root = Path(__file__).resolve().parents[1]
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise SystemExit("ffmpeg.exe and ffprobe.exe must be on PATH")

    import PyInstaller.__main__

    sep = os.pathsep
    options = [
        str(root / "desktop_launcher.py"),
        "--noconfirm", "--clean", "--onedir", "--windowed",
        "--name=GTA6Clips",
        f"--distpath={root / 'dist'}",
        f"--workpath={root / 'build'}",
        f"--specpath={root / 'build'}",
        f"--add-data={root / 'clipforge' / 'static'}{sep}clipforge/static",
        f"--add-data={root / 'clipforge' / 'templates'}{sep}clipforge/templates",
        f"--add-binary={ffmpeg}{sep}clipforge/bin",
        f"--add-binary={ffprobe}{sep}clipforge/bin",
        "--collect-submodules=webview",
        "--collect-submodules=clr_loader",
        "--hidden-import=webview.platforms.edgechromium",
    ]
    PyInstaller.__main__.run(options)
    destination = root / "dist" / "GTA6Clips" / "GTA6Clips.exe"
    if not destination.is_file():
        raise SystemExit("Build did not produce a desktop executable")
    print(f"WINDOWS BUILD PASS: {destination}")


if __name__ == "__main__":
    main()

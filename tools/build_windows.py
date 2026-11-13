"""Build reproducible Windows x64 GUI package with PyInstaller.

Running this script on Windows is intentionally explicit. Bundles ffmpeg and
ffprobe from the build machine rather than downloading binaries at app startup.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    if sys.platform != "win32":
        raise SystemExit("Windows packaging must run on a Windows CI runner")
    root = Path(__file__).resolve().parents[1]
    def find_real_executable(name: str) -> Path:
        """Avoid Chocolatey shims: copy the actual large FFmpeg distribution."""
        base = Path(os.environ.get("ChocolateyInstall",
                                   r"C:\ProgramData\chocolatey"))
        potential = list((base / "lib" / "ffmpeg").rglob(name + ".exe"))
        found = shutil.which(name)
        if found:
            potential.append(Path(found))
        # Prefer binaries from the installed package instead of tiny .exe shims.
        potential = sorted(
            (p for p in potential if p.is_file()),
            key=lambda p: (
                "chocolatey" in str(p).lower()
                and str(base / "bin").lower() not in str(p).lower(),
                p.stat().st_size,
            ),
            reverse=True,
        )
        for path in potential:
            try:
                check = subprocess.run(
                    [str(path), "-version"], capture_output=True,
                    check=False, timeout=15
                )
                if check.returncode == 0 and name.encode() in check.stdout.lower():
                    print(f"PACKAGING {name}: {path} ({path.stat().st_size} bytes)")
                    return path
            except (OSError, subprocess.SubprocessError):
                pass
        raise SystemExit(f"Real {name}.exe not found (Chocolatey shim is insufficient)")

    ffmpeg = find_real_executable("ffmpeg")
    ffprobe = find_real_executable("ffprobe")

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
        *[
            f"--add-binary={library}{sep}clipforge/bin"
            for library in sorted(set(ffmpeg.parent.glob("*.dll")) |
                                  set(ffprobe.parent.glob("*.dll")))
        ],
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

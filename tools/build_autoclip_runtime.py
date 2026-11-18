"""Bundle AutoClip's real Python 3.12 CLI runtime alongside Nexus Windows.

CI-only build, never downloads code at the user's PC. AutoClip is pinned to an
auditable git SHA and isolated from the PyInstaller GUI interpreter.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

AUTOCLIP_COMMIT = "5d0eac36fa615b79dd2104083bf273a96f8d68bb"
AUTOCLIP_REPO = "https://github.com/artbyjazi/autoclip.git"


def _ignore_stdlib(directory, names):
    blocked = {"site-packages", "__pycache__", "test", "tests", "ensurepip",
               "idlelib", "tkinter", "turtledemo", "venv", "pip"}
    return {name for name in names if name in blocked or name.endswith(".pyc")}


def main():
    if sys.platform != "win32" or sys.version_info[:2] != (3, 12):
        raise SystemExit("AutoClip Windows sidecar must build with CPython 3.12")
    project = Path(__file__).resolve().parents[1]
    source = Path(sys.base_prefix)
    target = project / "dist" / "GTA6Clips" / "autoclip_runtime"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in ("python.exe", "python312.dll", "python3.dll",
                 "vcruntime140.dll", "vcruntime140_1.dll"):
        dll = source / name
        if not dll.is_file():
            if name.startswith("vcruntime"):
                continue
            raise SystemExit(f"Missing CPython runtime component: {name}")
        shutil.copy2(dll, target / name)
    for folder in ("DLLs", "Lib"):
        shutil.copytree(source / folder, target / folder, ignore=_ignore_stdlib)
    package_dir = target / "Lib" / "site-packages"
    package_dir.mkdir(exist_ok=True)

    spec = f"git+{AUTOCLIP_REPO}@{AUTOCLIP_COMMIT}"
    subprocess.run([
        sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
        "--no-cache-dir", "--no-compile", "--target", str(package_dir), spec,
    ], check=True, timeout=1800)

    (target / "nexus_autoclip_runner.py").write_text(
        "from autoclip.cli import app\n"
        "if __name__ == '__main__':\n"
        "    app()\n", encoding="utf-8"
    )
    url = (f"https://raw.githubusercontent.com/artbyjazi/autoclip/"
           f"{AUTOCLIP_COMMIT}/LICENSE")
    with urllib.request.urlopen(url, timeout=30) as response:
        license_text = response.read(100_000)
    if not license_text.startswith(b"MIT License") or b"Jad Ghazi" not in license_text:
        raise SystemExit("Unexpected AutoClip license text: abort packaging")
    (target / "AUTOCLIP-LICENSE.txt").write_bytes(license_text)
    (target / "AUTOCLIP-SOURCE.txt").write_text(
        f"{AUTOCLIP_REPO}\nCommit: {AUTOCLIP_COMMIT}\nLicense: MIT\n",
        encoding="utf-8"
    )
    # AutoClip renders animated captions with libass and encodes H.264 with
    # libx264. An ffmpeg build missing either MUST NOT ship as "AutoClip ready".
    ffmpeg = project / "dist" / "GTA6Clips" / "_internal" / "clipforge" / "bin" / "ffmpeg.exe"
    if not ffmpeg.is_file():
        raise SystemExit("Nexus bundled FFmpeg binary is missing")
    filters = subprocess.run([str(ffmpeg), "-hide_banner", "-filters"],
                             capture_output=True, text=True, check=True, timeout=20).stdout
    encoders = subprocess.run([str(ffmpeg), "-hide_banner", "-encoders"],
                              capture_output=True, text=True, check=True, timeout=20).stdout
    if not any(line.split()[-1] == "ass" for line in filters.splitlines()
               if len(line.split()) >= 2):
        # Output usually includes "T.. ass V->V ..." rather than ending in ass.
        if " ass " not in filters:
            raise SystemExit("Bundled FFmpeg has no libass subtitle renderer")
    if "libx264" not in encoders:
        raise SystemExit("Bundled FFmpeg has no libx264 H.264 encoder")
    # Force relocated interpreter to import from its own directory, not CI's.
    env = dict(os.environ)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    validate = (
        "import sys, pathlib, autoclip.cli, faster_whisper, mediapipe, scenedetect, yt_dlp;"
        f"assert pathlib.Path(sys.prefix).resolve() == pathlib.Path(r'{target}').resolve();"
        "print('BUNDLED AUTOCLIP PYTHON + WHISPER + MEDIAPIPE + SCENEDETECT + YT-DLP OK')"
    )
    subprocess.run([str(target / "python.exe"), "-c", validate],
                   check=True, env=env, timeout=100)
    subprocess.run([str(target / "python.exe"),
                    str(target / "nexus_autoclip_runner.py"), "styles"],
                   check=True, env=env, timeout=100)
    count = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
    if count < 50_000_000:
        raise SystemExit("Bundled AutoClip runtime unexpectedly small")
    print(f"AUTOCLIP BUNDLE PASS: {count // 1_000_000} MB in {target}")


if __name__ == "__main__":
    main()

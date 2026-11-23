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
# YouTube exige runtime JavaScript para o yt-dlp (EJS). Deno oficial, fixado por
# versão e SHA-256 (conferido contra o .sha256sum publicado na release).
DENO_VERSION = "v2.9.8"
DENO_ZIP_SHA256 = "cba84b26e0df5ae7f74fc66b86a95b866872a86292ebd84fa1e959927edd93bf"
DENO_URL = (f"https://github.com/denoland/deno/releases/download/{DENO_VERSION}/"
            "deno-x86_64-pc-windows-msvc.zip")


def bundle_deno(target: Path) -> Path:
    import hashlib
    import io
    import zipfile
    with urllib.request.urlopen(DENO_URL, timeout=120) as response:
        data = response.read(200_000_000)
    if hashlib.sha256(data).hexdigest() != DENO_ZIP_SHA256:
        raise SystemExit("Deno ZIP SHA-256 mismatch: abort packaging")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        if names != ["deno.exe"]:
            raise SystemExit(f"Unexpected Deno archive layout: {names[:5]}")
        exe = target / "deno.exe"
        exe.write_bytes(archive.read("deno.exe"))
    (target / "DENO-SOURCE.txt").write_text(
        f"{DENO_URL}\nSHA-256: {DENO_ZIP_SHA256}\nLicense: MIT (https://github.com/denoland/deno)\n",
        encoding="utf-8")
    return exe


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
        # [default] traz o yt-dlp-ejs na versão casada com o yt-dlp (YouTube).
        "yt-dlp[default]",
    ], check=True, timeout=1800)
    deno = bundle_deno(target)

    # Runner registra a legenda personalizada do painel como preset "nexus_custom".
    sys.path.insert(0, str(project))
    from clipforge.autoclip_settings import RUNNER_SOURCE
    (target / "nexus_autoclip_runner.py").write_text(RUNNER_SOURCE, encoding="utf-8")
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
        "import sys, pathlib, autoclip.cli, faster_whisper, mediapipe, scenedetect, yt_dlp, yt_dlp_ejs;"
        f"assert pathlib.Path(sys.prefix).resolve() == pathlib.Path(r'{target}').resolve();"
        "print('BUNDLED AUTOCLIP PYTHON + WHISPER + MEDIAPIPE + SCENEDETECT + YT-DLP + EJS OK')"
    )
    subprocess.run([str(target / "python.exe"), "-c", validate],
                   check=True, env=env, timeout=100)
    version = subprocess.run([str(deno), "--version"], capture_output=True, text=True,
                             check=True, env=env, timeout=60).stdout
    if not version.startswith("deno " + DENO_VERSION.lstrip("v")):
        raise SystemExit("Bundled Deno did not report the pinned version")
    print("BUNDLED DENO OK: " + version.splitlines()[0])
    subprocess.run([str(target / "python.exe"),
                    str(target / "nexus_autoclip_runner.py"), "styles"],
                   check=True, env=env, timeout=100)
    # Legenda personalizada do painel precisa virar preset real do AutoClip.
    from clipforge.autoclip_settings import DEFAULTS, caption_style_spec
    import json as _json
    custom_env = {**env, "NEXUS_CAPTION_STYLE": _json.dumps(caption_style_spec(DEFAULTS))}
    listing = subprocess.run([str(target / "python.exe"),
                              str(target / "nexus_autoclip_runner.py"), "styles"],
                             check=True, env=custom_env, timeout=100,
                             capture_output=True, text=True).stdout
    if "nexus_custom" not in listing:
        raise SystemExit("Runner did not register the custom caption preset")
    print("CUSTOM CAPTION PRESET OK")
    count = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
    if count < 50_000_000:
        raise SystemExit("Bundled AutoClip runtime unexpectedly small")
    print(f"AUTOCLIP BUNDLE PASS: {count // 1_000_000} MB in {target}")


if __name__ == "__main__":
    main()

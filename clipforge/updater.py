"""GitHub Releases update discovery and secure staging for the Windows app.

Only published, non-prerelease official repository releases are considered.
The user must click Update in the desktop UI. Download is SHA-256 verified,
unpacked to the user profile, and verified using the frozen EXE self-test.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from .version import VERSION

REPO = "lulualcides-sys/GTA-6-clips"
LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET_NAME = "GTA6Clips-Windows-portable.zip"
MAX_DOWNLOAD = 600 * 1024 * 1024
MAX_UNPACKED = 1200 * 1024 * 1024
TAG = re.compile(r"^v(\d{1,4})\.(\d{1,4})\.(\d{1,4})$")
DIGEST = re.compile(r"^sha256:([a-fA-F0-9]{64})$")


class UpdateError(RuntimeError):
    pass


def parse_version(value: str) -> tuple[int,int,int] | None:
    m = TAG.fullmatch(value if value.startswith("v") else "v" + value)
    return tuple(map(int, m.groups())) if m else None


def validate_release(data: dict, current: str = VERSION) -> dict:
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        raise UpdateError("Nenhuma versão estável disponível")
    version = str(data.get("tag_name", ""))
    new, installed = parse_version(version), parse_version(current)
    if not new or not installed:
        raise UpdateError("Versão inválida no manifesto de atualização")
    if new <= installed:
        return {"available": False, "installed": current, "latest": version}
    matching = [
        a for a in data.get("assets", [])
        if isinstance(a, dict) and a.get("name") == ASSET_NAME
    ]
    if len(matching) != 1:
        raise UpdateError("Release sem o pacote Windows esperado")
    asset = matching[0]
    url = str(asset.get("browser_download_url", ""))
    prefix = f"https://github.com/{REPO}/releases/download/{version}/"
    if url != prefix + ASSET_NAME:
        raise UpdateError("Endereço do pacote não corresponde ao repositório oficial")
    digest = DIGEST.fullmatch(str(asset.get("digest", "")))
    if not digest:
        raise UpdateError("Release sem digest SHA-256 publicado")
    size = int(asset.get("size", 0))
    if not 2_000_000 <= size <= MAX_DOWNLOAD:
        raise UpdateError("Tamanho do pacote Windows fora dos limites")
    return {
        "available": True, "installed": current, "latest": version,
        "url": url, "sha256": digest.group(1).lower(), "size": size,
        "notes": str(data.get("body", ""))[:600],
    }


def check_latest(timeout: int = 12, current: str = VERSION) -> dict:
    req = urllib.request.Request(LATEST, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "GTA6Clips-Desktop-Updater",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            # Never accept enormous JSON documents.
            raw = response.read(384 * 1024 + 1)
        if len(raw) > 384 * 1024:
            raise UpdateError("Manifesto remoto excedeu o limite")
        return validate_release(json.loads(raw), current)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"available": False, "installed": current,
                    "latest": None, "reason": "Ainda não há uma release estável"}
        raise UpdateError(f"GitHub indisponível (HTTP {exc.code})") from exc
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        raise UpdateError("Não foi possível consultar o GitHub") from exc


def _download(info: dict, output: Path) -> None:
    request = urllib.request.Request(info["url"], headers={
        "User-Agent": "GTA6Clips-Desktop-Updater",
    })
    current = 0
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=30) as response:
        with output.open("xb") as dest:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                current += len(block)
                if current > MAX_DOWNLOAD or current > info["size"]:
                    raise UpdateError("Download maior do que o tamanho verificado")
                digest.update(block)
                dest.write(block)
    if current != info["size"] or digest.hexdigest() != info["sha256"]:
        raise UpdateError("A assinatura SHA-256 do arquivo não confere")


def _extract_verified(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=False)
    total = 0
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) > 2000:
            raise UpdateError("Pacote contém arquivos demais")
        for item in members:
            name = item.filename.replace("\\", "/")
            parts = name.rstrip("/").split("/")
            if (not name or name.startswith("/") or
                    any(p in {"", ".", ".."} for p in parts) or
                    ":" in parts[0]):
                raise UpdateError("Pacote contém caminho inseguro")
            mode = (item.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise UpdateError("Links simbólicos não são aceitos")
            total += item.file_size
            if total > MAX_UNPACKED:
                raise UpdateError("Pacote descompactado excede o limite")
            target = destination.joinpath(*parts)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(item) as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst)
    if not (destination / "GTA6Clips.exe").is_file():
        raise UpdateError("Pacote não contém GTA6Clips.exe")
    if not (destination / "GTA6ClipsUpdater.exe").is_file():
        raise UpdateError("Pacote não contém o atualizador de segurança")
    return destination


class UpdateService:
    def __init__(self, home: Path):
        self.home = home
        self._latest: dict | None = None

    def check(self) -> dict:
        data = check_latest()
        self._latest = data if data.get("available") else None
        return {k: v for k, v in data.items() if k not in {"url", "sha256", "size"}}

    def stage(self) -> tuple[dict, Path]:
        # Re-query just before downloading to avoid stale release assumptions.
        release = check_latest()
        if not release.get("available"):
            raise UpdateError("Não existe atualização disponível")
        root = self.home / "updates"
        if root.is_symlink():
            raise UpdateError("Pasta de atualização não confiável")
        root.mkdir(parents=True, exist_ok=True)
        version = release["latest"]
        with tempfile.TemporaryDirectory(prefix="gta6-", dir=root) as tmp:
            tmp_path = Path(tmp)
            archive = tmp_path / ASSET_NAME
            _download(release, archive)
            extracted = _extract_verified(archive, tmp_path / "extracted")
            # Check new binaries before replacing the working version.
            report = tmp_path / "test.json"
            environment = dict(os.environ, GTA6_SELFTEST_PATH=str(report))
            try:
                result = subprocess.run(
                    [str(extracted / "GTA6Clips.exe"), "--self-test"],
                    env=environment, check=False, timeout=100,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise UpdateError("O novo executável falhou no autoteste") from exc
            try:
                outcome = json.loads(report.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise UpdateError("O novo programa não concluiu o autoteste") from exc
            if (result.returncode or outcome.get("status") != "pass"
                    or outcome.get("phase") != "complete"):
                raise UpdateError("A nova versão falhou na validação; instalação preservada")
            final = root / ("ready-" + version)
            if final.exists():
                if final.is_symlink():
                    raise UpdateError("Diretório de atualização inseguro")
                shutil.rmtree(final)
            os.replace(extracted, final)
            return release, final

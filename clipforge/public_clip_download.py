"""Download de clipe PÚBLICO da Twitch via yt-dlp, somente de fonte autorizada.

Usado quando o streamer liberou cortes (bio/permissão registrada) mas a conta do
usuário não é editora do canal, caso em que a API oficial Get Clips Download não
entrega o arquivo. Não é API oficial da Twitch: pode violar os Termos da Twitch e
quebrar com mudanças do site. O proprietário ativa explicitamente com
TWITCH_PUBLIC_DOWNLOAD=1 e assume esse risco. Nunca baixa de streamer fora de
twitch_sources.json, nunca contorna DRM, login ou conteúdo pago.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .core import duration_of, probe
from .twitch_download import MAX_BYTES, DownloadError


def enabled() -> bool:
    return os.getenv("TWITCH_PUBLIC_DOWNLOAD", "0").strip() == "1"


def yt_dlp_command() -> list[str] | None:
    """yt-dlp do runtime AutoClip empacotado (Windows) ou do sistema."""
    if getattr(sys, "frozen", False):
        python = Path(sys.executable).resolve().parent / "autoclip_runtime" / "python.exe"
        if python.is_file():
            return [str(python), "-m", "yt_dlp"]
    found = shutil.which("yt-dlp")
    if found:
        return [found]
    if importlib.util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]
    return None


def download_public_clip(clip_id: str, broadcaster_id: str, manifest: dict, incoming: Path,
                         *, run=subprocess.run, command: list[str] | None = None) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,180}", clip_id or "") or not str(broadcaster_id).isdigit():
        raise DownloadError("IDs Twitch inválidos")
    if not isinstance(manifest, dict):
        raise DownloadError("Manifesto de direitos obrigatório")
    creator = str(manifest.get("creator", "")).strip()
    rights = manifest.get("rights_status")
    evidence = str(manifest.get("evidence", "")).strip()
    if (not creator or rights not in {"owned", "permission_granted"}
            or str(manifest.get("broadcaster_id", "")) != str(broadcaster_id)
            or (rights == "permission_granted" and len(evidence) < 8)):
        raise DownloadError("Streamer sem autorização registrada; download público bloqueado")
    command = command or yt_dlp_command()
    if not command:
        raise DownloadError("yt-dlp indisponível neste computador")
    incoming = Path(incoming).resolve()
    incoming.mkdir(parents=True, exist_ok=True)
    target = incoming / f"twitch-{clip_id}.mp4"
    sidecar = Path(str(target) + ".rights.json")
    if target.exists() or target.is_symlink() or sidecar.exists() or sidecar.is_symlink():
        raise DownloadError("Fonte ou manifesto já existe; download duplicado bloqueado")
    url = f"https://clips.twitch.tv/{clip_id}"
    work_root = incoming.parent / "tmp"
    work_root.mkdir(parents=True, exist_ok=True)
    installed = sidecar_installed = False
    temp_sidecar = None
    with tempfile.TemporaryDirectory(prefix="public-clip-", dir=work_root) as tmp:
        out = Path(tmp)
        try:
            result = run([*command, "--no-playlist", "--no-warnings", "--quiet", "--no-progress",
                          "--no-mtime", "--max-filesize", "512M", "-f", "best[ext=mp4]/best",
                          "-o", str(out / "clip.%(ext)s"), url],
                         stdin=subprocess.DEVNULL, capture_output=True, text=True,
                         errors="replace", timeout=240, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            raise DownloadError("yt-dlp não executou ou excedeu o tempo") from exc
        if result.returncode != 0:
            tail = (result.stderr or "").strip().splitlines()[-1:] or [""]
            raise DownloadError("yt-dlp falhou: " + tail[0][:150])
        files = [p for p in out.iterdir() if p.is_file() and not p.is_symlink()
                 and not p.name.endswith((".part", ".ytdl"))]
        if len(files) != 1:
            raise DownloadError("yt-dlp não produziu exatamente um arquivo")
        media = files[0]
        size = media.stat().st_size
        if not 0 < size <= MAX_BYTES:
            raise DownloadError("Mídia vazia ou acima de 512 MiB")
        info = probe(media)
        if duration_of(info) <= 0 or not any(s.get("codec_type") == "video" for s in info.get("streams", [])):
            raise DownloadError("Arquivo recebido não é vídeo válido")
        digest = hashlib.sha256()
        with media.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        try:
            # Link atômico: falha se outro processo já instalou o mesmo clipe.
            os.link(media, target)
            installed = True
            metadata = dict(manifest)
            metadata.update({"source_url": url, "twitch_clip_id": clip_id,
                             "broadcaster_id": str(broadcaster_id),
                             "download_method": "public_clip_page_yt_dlp",
                             "download_note": "Não oficial: Termos da Twitch aceitos pelo proprietário",
                             "source_sha256": digest.hexdigest()})
            with tempfile.NamedTemporaryFile(dir=incoming, prefix=".twitch-rights-", suffix=".part",
                                             mode="w", encoding="utf-8", delete=False) as output:
                temp_sidecar = Path(output.name)
                json.dump(metadata, output, ensure_ascii=False, indent=2)
            os.link(temp_sidecar, sidecar)
            sidecar_installed = True
            return target
        except OSError as exc:
            raise DownloadError("Falha ao gravar o clipe baixado") from exc
        finally:
            if temp_sidecar is not None:
                temp_sidecar.unlink(missing_ok=True)
            if installed and not sidecar_installed:
                target.unlink(missing_ok=True)

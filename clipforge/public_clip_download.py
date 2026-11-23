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


_FRIENDLY = (
    (("subscriber", "sub-only", "inscritos"), "Conteúdo só para inscritos do canal; não dá para baixar."),
    (("does not pass filter", "does not match filter", "skipping"), "Ignorado: mais longo que o limite configurado ou ainda ao vivo."),
    (("is offline", "not currently live"), "O streamer não está ao vivo."),
    (("does not exist", "not available", "has been deleted", "unavailable", "removed"),
     "O vídeo/VOD não existe mais ou foi removido pelo streamer."),
    (("private",), "O vídeo é privado."),
    (("geo", "country"), "Bloqueado para o seu país."),
    (("http error 403", "forbidden"), "A Twitch bloqueou o acesso agora (403); o app tenta de novo mais tarde."),
    (("http error 429", "too many requests"), "Muitas requisições; o app espera e tenta de novo mais tarde."),
    (("timed out", "connection", "network", "temporary failure"), "Falha de rede; o app tenta de novo mais tarde."),
)


def humanize_ytdlp_error(stderr: str) -> str:
    """Traduz o erro técnico do yt-dlp para uma explicação curta em português."""
    text = (stderr or "").lower()
    for needles, message in _FRIENDLY:
        if any(n in text for n in needles):
            return message
    tail = (stderr or "").strip().splitlines()[-1:] or [""]
    return "Download falhou: " + (tail[0][:150] or "erro desconhecido do yt-dlp")


def download_public_clip(clip_id: str, broadcaster_id: str, manifest: dict, incoming: Path,
                         *, run=subprocess.run, command: list[str] | None = None) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,180}", clip_id or ""):
        raise DownloadError("IDs Twitch inválidos")
    return _download(f"https://clips.twitch.tv/{clip_id}", f"twitch-{clip_id}", clip_id,
                     broadcaster_id, manifest, incoming, method="public_clip_page_yt_dlp",
                     max_filesize="512M", max_bytes=MAX_BYTES, timeout=240,
                     fmt="best[ext=mp4]/best", run=run, command=command)


VOD_MAX_BYTES = 8 * 1024 ** 3


def download_public_vod(vod_id: str, broadcaster_id: str, manifest: dict, incoming: Path,
                        *, max_minutes: int = 180, run=subprocess.run,
                        command: list[str] | None = None) -> Path:
    """VOD público (gravação da live) de streamer autorizado; até 1080p e max_minutes."""
    if not re.fullmatch(r"[0-9]{1,20}", str(vod_id or "")):
        raise DownloadError("ID de VOD inválido")
    max_minutes = max(5, min(600, int(max_minutes)))
    return _download(f"https://www.twitch.tv/videos/{vod_id}", f"twitch-vod-{vod_id}", str(vod_id),
                     broadcaster_id, manifest, incoming, method="public_vod_yt_dlp",
                     max_filesize="8G", max_bytes=VOD_MAX_BYTES, timeout=4 * 3600,
                     fmt="best[height<=1080][ext=mp4]/best[height<=1080]/best",
                     extra=["--match-filter", f"duration <= {max_minutes * 60} & !is_live"],
                     run=run, command=command)


def _download(url: str, stem: str, item_id: str, broadcaster_id: str, manifest: dict,
              incoming: Path, *, method: str, max_filesize: str, max_bytes: int, timeout: int,
              fmt: str, extra: list[str] | None = None, run=subprocess.run,
              command: list[str] | None = None) -> Path:
    if not str(broadcaster_id).isdigit():
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
    target = incoming / f"{stem}.mp4"
    sidecar = Path(str(target) + ".rights.json")
    if target.exists() or target.is_symlink() or sidecar.exists() or sidecar.is_symlink():
        raise DownloadError("Fonte ou manifesto já existe; download duplicado bloqueado")
    work_root = incoming.parent / "tmp"
    work_root.mkdir(parents=True, exist_ok=True)
    installed = sidecar_installed = False
    temp_sidecar = None
    with tempfile.TemporaryDirectory(prefix="public-clip-", dir=work_root,
                                     ignore_cleanup_errors=True) as tmp:
        out = Path(tmp)
        try:
            result = run([*command, "--no-playlist", "--no-warnings", "--quiet", "--no-progress",
                          "--no-mtime", "--max-filesize", max_filesize, "-f", fmt,
                          "--merge-output-format", "mp4", *(extra or []),
                          "-o", str(out / "clip.%(ext)s"), url],
                         stdin=subprocess.DEVNULL, capture_output=True, text=True,
                         errors="replace", timeout=timeout, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            raise DownloadError("yt-dlp não executou ou excedeu o tempo") from exc
        if result.returncode != 0:
            raise DownloadError(humanize_ytdlp_error(result.stderr or ""))
        files = [p for p in out.iterdir() if p.is_file() and not p.is_symlink()
                 and not p.name.endswith((".part", ".ytdl"))]
        if len(files) != 1:
            raise DownloadError("yt-dlp não produziu exatamente um arquivo "
                                "(VOD longa demais, ao vivo ou indisponível?)")
        media = files[0]
        size = media.stat().st_size
        if not 0 < size <= max_bytes:
            raise DownloadError("Mídia vazia ou acima do limite")
        info = probe(media)
        seconds = duration_of(info)
        if seconds <= 0 or not any(s.get("codec_type") == "video" for s in info.get("streams", [])):
            raise DownloadError("Arquivo recebido não é vídeo válido")
        digest = hashlib.sha256()
        with media.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        try:
            # Link atômico: falha se outro processo já instalou o mesmo item.
            os.link(media, target)
            installed = True
            metadata = dict(manifest)
            metadata.update({"source_url": url, "twitch_clip_id" if method.startswith("public_clip")
                             else "twitch_vod_id": item_id,
                             "broadcaster_id": str(broadcaster_id),
                             "download_method": method,
                             "download_note": "Não oficial: Termos da Twitch aceitos pelo proprietário",
                             "source_sha256": digest.hexdigest(),
                             "source_duration_sec": round(seconds, 2)})
            with tempfile.NamedTemporaryFile(dir=incoming, prefix=".twitch-rights-", suffix=".part",
                                             mode="w", encoding="utf-8", delete=False) as output:
                temp_sidecar = Path(output.name)
                json.dump(metadata, output, ensure_ascii=False, indent=2)
            os.link(temp_sidecar, sidecar)
            sidecar_installed = True
            return target
        except OSError as exc:
            raise DownloadError("Falha ao gravar o arquivo baixado") from exc
        finally:
            if temp_sidecar is not None:
                temp_sidecar.unlink(missing_ok=True)
            if installed and not sidecar_installed:
                target.unlink(missing_ok=True)

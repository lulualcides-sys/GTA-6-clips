"""Download de vídeo PÚBLICO do YouTube via yt-dlp, somente de canal autorizado.

Não existe API oficial do YouTube para baixar vídeos de terceiros. Este caminho
usa o yt-dlp do runtime AutoClip e pode violar os Termos do YouTube; o
proprietário ativa explicitamente com YOUTUBE_PUBLIC_DOWNLOAD=1 e assume esse
risco. Travas: só canais em youtube_sources.json com evidência, o canal real do
vídeo (lido pelo yt-dlp) precisa bater com o autorizado, sem lives, sem DRM,
sem conteúdo pago ou para membros, limite de duração e tamanho.

Em 2026 o YouTube bloqueia a maioria dos downloads anônimos: o yt-dlp precisa
de um runtime JavaScript (Deno, incluído no app Windows) e, muitas vezes, dos
cookies de um navegador logado (YOUTUBE_COOKIES_BROWSER). Use uma conta Google
secundária, nunca a do canal onde você publica.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .core import duration_of, probe
from .public_clip_download import yt_dlp_command
from .twitch_download import DownloadError
from .youtube_radar import CHANNEL_RE, VIDEO_RE, max_seconds

MAX_BYTES = 4 * 1024 ** 3
BROWSERS = {"", "firefox", "chrome", "edge", "brave", "opera", "vivaldi", "chromium"}


def enabled() -> bool:
    return os.getenv("YOUTUBE_PUBLIC_DOWNLOAD", "0").strip() == "1"


def cookies_browser() -> str:
    value = os.getenv("YOUTUBE_COOKIES_BROWSER", "").strip().lower()
    return value if value in BROWSERS else ""


def deno_path() -> str | None:
    """Runtime JS exigido pelo yt-dlp para o YouTube (EJS)."""
    if getattr(sys, "frozen", False):
        bundled = Path(sys.executable).resolve().parent / "autoclip_runtime" / "deno.exe"
        if bundled.is_file():
            return str(bundled)
    return shutil.which("deno")


def build_command(command: list[str], video_id: str, out: Path) -> list[str]:
    limit = max_seconds()
    args = [*command, "--no-playlist", "--no-warnings", "--quiet", "--no-progress", "--no-mtime",
            "--no-live-from-start", "--match-filter", f"!is_live & duration <= {limit}",
            "--max-filesize", "4G", "--write-info-json", "--no-write-comments",
            "-f", ("bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/"
                   "bv*[height<=1080]+ba/b[height<=1080]/b"),
            "--merge-output-format", "mp4", "-o", str(out / "video.%(ext)s")]
    deno = deno_path()
    if deno:
        args += ["--js-runtimes", "deno:" + deno]
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        args += ["--ffmpeg-location", str(Path(ffmpeg).parent)]
    browser = cookies_browser()
    if browser:
        args += ["--cookies-from-browser", browser]
    return args + ["https://www.youtube.com/watch?v=" + video_id]


def _explain(stderr: str) -> str:
    text = (stderr or "").strip()
    low = text.lower()
    if "sign in to confirm" in low or "not a bot" in low:
        return ("YouTube pediu login (checagem anti-robô). Escolha um navegador logado em "
                "'Cookies do navegador' (use uma conta Google secundária).")
    if "could not copy" in low and "cookie" in low:
        return "Feche o navegador escolhido para cookies e tente de novo (ele trava o arquivo de cookies)."
    if "members" in low or "join this channel" in low or "premium" in low:
        return "Vídeo exclusivo para membros/pagos: bloqueado."
    if "drm" in low:
        return "Vídeo com DRM: bloqueado."
    tail = text.splitlines()[-1:] or [""]
    return "yt-dlp falhou: " + tail[0][:150]


def download_youtube_video(video_id: str, channel_id: str, manifest: dict, incoming: Path, *,
                           title: str = "", run=subprocess.run,
                           command: list[str] | None = None) -> Path:
    if not VIDEO_RE.fullmatch(video_id or "") or not CHANNEL_RE.fullmatch(channel_id or ""):
        raise DownloadError("IDs do YouTube inválidos")
    if not isinstance(manifest, dict):
        raise DownloadError("Manifesto de direitos obrigatório")
    creator = str(manifest.get("creator", "")).strip()
    rights = manifest.get("rights_status")
    evidence = str(manifest.get("evidence", "")).strip()
    if (not creator or rights not in {"owned", "permission_granted"}
            or str(manifest.get("channel_id", "")) != channel_id
            or (rights == "permission_granted" and len(evidence) < 8)):
        raise DownloadError("Canal sem autorização registrada; download bloqueado")
    command = command or yt_dlp_command()
    if not command:
        raise DownloadError("yt-dlp indisponível neste computador")
    incoming = Path(incoming).resolve()
    incoming.mkdir(parents=True, exist_ok=True)
    target = incoming / f"youtube-{video_id}.mp4"
    sidecar = Path(str(target) + ".rights.json")
    if target.exists() or target.is_symlink() or sidecar.exists() or sidecar.is_symlink():
        raise DownloadError("Fonte ou manifesto já existe; download duplicado bloqueado")
    work_root = incoming.parent / "tmp"
    work_root.mkdir(parents=True, exist_ok=True)
    installed = sidecar_installed = False
    temp_sidecar = None
    with tempfile.TemporaryDirectory(prefix="youtube-", dir=work_root) as tmp:
        out = Path(tmp)
        try:
            result = run(build_command(command, video_id, out), stdin=subprocess.DEVNULL,
                         capture_output=True, text=True, errors="replace", timeout=2400, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            raise DownloadError("yt-dlp não executou ou excedeu o tempo") from exc
        if result.returncode != 0:
            raise DownloadError(_explain(result.stderr))
        infos = [p for p in out.glob("*.info.json") if p.is_file() and not p.is_symlink()]
        media = [p for p in out.iterdir() if p.is_file() and not p.is_symlink()
                 and p.suffix.lower() == ".mp4"]
        if not media:
            raise DownloadError("Vídeo fora do filtro (live, longo demais) ou não baixado")
        if len(media) != 1 or len(infos) != 1:
            raise DownloadError("yt-dlp não produziu exatamente um vídeo")
        try:
            info = json.loads(infos[0].read_text(encoding="utf-8")[:5_000_000])
        except (OSError, ValueError) as exc:
            raise DownloadError("Metadados do yt-dlp ilegíveis") from exc
        # O vídeo baixado precisa ser do canal autorizado (não basta o ID pedido).
        if str(info.get("channel_id", "")) != channel_id or str(info.get("id", "")) != video_id:
            raise DownloadError("Vídeo não pertence ao canal autorizado; descartado")
        if info.get("is_live") or info.get("availability") in {"premium_only", "subscriber_only",
                                                                 "needs_auth"}:
            raise DownloadError("Live ou vídeo restrito: bloqueado")
        clip = media[0]
        size = clip.stat().st_size
        if not 0 < size <= MAX_BYTES:
            raise DownloadError("Vídeo vazio ou acima de 4 GiB")
        probed = probe(clip)
        seconds = duration_of(probed)
        streams = probed.get("streams", [])
        if (not 10 <= seconds <= max_seconds() + 5
                or not any(s.get("codec_type") == "video" for s in streams)
                or not any(s.get("codec_type") == "audio" for s in streams)):
            raise DownloadError("Arquivo recebido não é vídeo válido com áudio dentro do limite")
        digest = hashlib.sha256()
        with clip.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        url = "https://www.youtube.com/watch?v=" + video_id
        try:
            os.link(clip, target)  # atômico: falha se outro processo já instalou
            installed = True
            metadata = dict(manifest)
            metadata.update({
                "source_url": url, "youtube_video_id": video_id, "youtube_channel_id": channel_id,
                "title": str(title or info.get("title", ""))[:200],
                "download_method": "youtube_public_yt_dlp",
                "download_note": "Não oficial: Termos do YouTube aceitos pelo proprietário",
                "source_sha256": digest.hexdigest(), "source_duration_sec": round(seconds, 2),
            })
            with tempfile.NamedTemporaryFile(dir=incoming, prefix=".youtube-rights-", suffix=".part",
                                             mode="w", encoding="utf-8", delete=False) as output:
                temp_sidecar = Path(output.name)
                json.dump(metadata, output, ensure_ascii=False, indent=2)
            os.link(temp_sidecar, sidecar)
            sidecar_installed = True
            return target
        except OSError as exc:
            raise DownloadError("Falha ao gravar o vídeo baixado") from exc
        finally:
            if temp_sidecar is not None:
                temp_sidecar.unlink(missing_ok=True)
            if installed and not sidecar_installed:
                target.unlink(missing_ok=True)

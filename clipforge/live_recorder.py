"""Gravação de live da Twitch em tempo real (só streamers AUTORIZADOS, opt-in).

Quando o monitor vê um streamer autorizado ao vivo e TWITCH_LIVE_RECORD=1 (com
TWITCH_PUBLIC_DOWNLOAD=1), inicia o yt-dlp gravando a live pública desde aquele
momento. Quando a live acaba (ou chega a TWITCH_RECORD_MAX_MINUTES), a gravação
é finalizada: remux sem reencode para MP4, manifesto de direitos e entrega à
ingestão -> AutoClip. Não é API oficial (risco perante os Termos da Twitch,
assumido pelo proprietário). Nunca grava streamer não autorizado.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

from .core import duration_of, probe
from .public_clip_download import yt_dlp_command
from .twitch_download import DownloadError

LOGIN = re.compile(r"[a-z0-9_]{2,40}")


def enabled() -> bool:
    return (os.getenv("TWITCH_LIVE_RECORD", "0") == "1"
            and os.getenv("TWITCH_PUBLIC_DOWNLOAD", "0") == "1")


def max_seconds() -> int:
    try:
        return max(10, min(720, int(os.getenv("TWITCH_RECORD_MAX_MINUTES", "240")))) * 60
    except ValueError:
        return 240 * 60


class LiveRecorder:
    def __init__(self, data_root: Path, incoming: Path, *, popen=subprocess.Popen,
                 run=subprocess.run, command=None):
        self.folder = Path(data_root) / "recordings"
        self.incoming = Path(incoming)
        self._popen = popen
        self._run = run
        self._command = command
        self.active: dict[str, dict] = {}  # stream_id -> {process, path, started, ...}

    def is_recording(self, stream_id: str) -> bool:
        return stream_id in self.active

    def start(self, stream_id: str, login: str, manifest: dict) -> None:
        login = str(login or "").lower()
        if not LOGIN.fullmatch(login) or not re.fullmatch(r"[0-9]{1,30}", str(stream_id)):
            raise DownloadError("Live com login/ID inválido")
        if (str(manifest.get("broadcaster_id", "")) == "" or
                manifest.get("rights_status") not in {"owned", "permission_granted"}):
            raise DownloadError("Streamer sem autorização registrada; gravação bloqueada")
        if stream_id in self.active:
            return
        command = self._command or yt_dlp_command()
        if not command:
            raise DownloadError("yt-dlp indisponível neste computador")
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f"live-{stream_id}.ts"
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = self._popen(
            [*command, "--no-part", "--no-warnings", "--quiet", "--no-progress",
             "-f", "best[height<=1080]/best", "--hls-use-mpegts", "-o", str(path),
             f"https://www.twitch.tv/{login}"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            creationflags=flags)
        self.active[stream_id] = {"process": process, "path": path, "login": login,
                                  "manifest": dict(manifest), "started": time.monotonic()}

    def poll(self, stream_id: str, still_live: bool) -> str | None:
        """Retorna 'recording', 'finished' (pronto para finalizar) ou None."""
        info = self.active.get(stream_id)
        if not info:
            return None
        process = info["process"]
        too_long = time.monotonic() - info["started"] > max_seconds()
        if process.poll() is None and (still_live and not too_long):
            return "recording"
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
        return "finished"

    def finalize(self, stream_id: str, title: str = "") -> Path:
        """Remux .ts -> .mp4 (sem reencode), manifesto e entrega à pasta de entrada."""
        info = self.active.pop(stream_id, None)
        if not info:
            raise DownloadError("Gravação não encontrada")
        src: Path = info["path"]
        if not src.is_file() or src.stat().st_size < 100_000:
            src.unlink(missing_ok=True)
            raise DownloadError("Gravação vazia (live protegida, encerrada cedo ou bloqueada)")
        self.incoming.mkdir(parents=True, exist_ok=True)
        target = self.incoming / f"twitch-live-{stream_id}.mp4"
        sidecar = Path(str(target) + ".rights.json")
        if target.exists() or sidecar.exists():
            raise DownloadError("Gravação já entregue")
        with tempfile.TemporaryDirectory(dir=self.folder, ignore_cleanup_errors=True) as tmp:
            mp4 = Path(tmp) / "live.mp4"
            result = self._run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-map", "0:v:0",
                                "-map", "0:a?", "-c", "copy", "-movflags", "+faststart", str(mp4)],
                               stdin=subprocess.DEVNULL, capture_output=True, text=True,
                               errors="replace", timeout=3600, check=False)
            if result.returncode != 0 or not mp4.is_file():
                raise DownloadError("Falha ao finalizar a gravação (remux)")
            seconds = duration_of(probe(mp4))
            if seconds <= 0:
                raise DownloadError("Gravação sem vídeo válido")
            digest = hashlib.sha256()
            with mp4.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            os.replace(mp4, target)
        metadata = {**info["manifest"], "source_url": f"https://www.twitch.tv/{info['login']}",
                    "twitch_stream_id": stream_id, "title": str(title)[:200],
                    "download_method": "live_recording_yt_dlp",
                    "download_note": "Não oficial: Termos da Twitch aceitos pelo proprietário",
                    "source_sha256": digest.hexdigest(), "source_duration_sec": round(seconds, 2)}
        sidecar.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        src.unlink(missing_ok=True)
        return target

    def stop_all(self) -> None:
        for info in self.active.values():
            if info["process"].poll() is None:
                info["process"].terminate()

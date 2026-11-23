"""Entrada automática YouTube -> AutoClip, somente de canais autorizados.

A cada rodada: uploads recentes dos canais em youtube_sources.json (Data API
oficial, ~3 unidades por canal) -> filtro (sem live, 2 min a YOUTUBE_MAX_MINUTES,
GTA VI depois da virada) -> melhores por views/hora -> download yt-dlp opt-in
-> ingestão com manifesto -> fila exclusiva do AutoClip. Nunca aprova nem publica.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta, timezone

from .ingest_log import record
from .twitch_download import DownloadError
from .youtube_radar import (YouTubeAPI, YouTubeError, api_key, authorized_sources,
                            eligible_for_autoclip, video_row)
from . import youtube_download as ytd


def _int_env(name, default, low, high):
    try:
        return max(low, min(high, int(os.getenv(name, str(default)))))
    except ValueError:
        return default


class YouTubeAutoIngest:
    def __init__(self, runtime, *, client_factory=YouTubeAPI, downloader=None):
        self.runtime = runtime
        self.client_factory = client_factory
        self.downloader = downloader or ytd.download_youtube_video
        self.lock = threading.RLock()
        self.running = False
        self.next_retry: dict[str, float] = {}
        self.last_error = None
        self.last_run = None
        self.processed = 0
        self.attempted = 0
        self.last_checked = 0
        self.last_eligible = 0
        self._thread = None
        self.trigger = "automatico"  # "manual" quando o proprietário clica em Verificar agora

    def _gta6_only(self) -> bool:
        value = os.getenv("YOUTUBE_AUTO_GTA6_ONLY", "1").strip().lower()
        if value == "force":
            return True
        if value == "0":
            return False
        try:
            return self.runtime.twitch.profile()["profile"] == "gta6_only"
        except (AttributeError, ValueError, TypeError, KeyError, RuntimeError):
            return True

    def status(self) -> dict:
        allowed = authorized_sources(self.runtime.store.root)
        command = ytd.yt_dlp_command()
        bridge = self.runtime.autoclip_bridge
        enabled = ytd.enabled()
        return {
            "enabled": enabled, "api_key_present": bool(api_key()),
            "authorized_channels": len(allowed), "yt_dlp": bool(command),
            "js_runtime": bool(ytd.deno_path()), "cookies_browser": ytd.cookies_browser(),
            "gta6_only": self._gta6_only(), "running": self.running,
            "last_error": self.last_error, "last_run": self.last_run,
            "downloaded": self.processed, "attempted": self.attempted,
            "last_checked": self.last_checked, "last_eligible": self.last_eligible,
            "batch": _int_env("YOUTUBE_AUTO_BATCH", 2, 1, 6),
            "ready": (enabled and bool(api_key()) and bool(allowed) and bool(command)
                      and bridge.available()),
        }

    def _blocked(self) -> str | None:
        if not ytd.enabled():
            return "Download do YouTube desligado (ative em Conectar YouTube)."
        if not api_key():
            return "Chave da YouTube Data API ausente."
        if not authorized_sources(self.runtime.store.root):
            return "Nenhum canal do YouTube autorizado; marque quem liberou cortes."
        if not ytd.yt_dlp_command():
            return "yt-dlp indisponível neste computador."
        bridge = self.runtime.autoclip_bridge
        if not bridge.available():
            return "Motor AutoClip indisponível."
        if hasattr(bridge, "model_ready") and not bridge.model_ready():
            return "Modelo de IA do AutoClip indisponível. Use 'Preparar IA do AutoClip'."
        return None

    def kick(self) -> bool:
        reason = self._blocked()
        if reason:
            self.last_error = reason
            return False
        with self.lock:
            if self.running:
                return False
            self.running = True
        self._thread = threading.Thread(target=self._work, name="youtube-authorized-auto-intake",
                                        daemon=True)
        self._thread.start()
        return True

    def start_polling(self) -> None:
        seconds = _int_env("YOUTUBE_POLL_SECONDS", 1800, 600, 86400)

        def loop():
            time.sleep(20)
            while True:
                try:
                    self.kick()
                except Exception as exc:  # noqa: BLE001 - laço de fundo não pode morrer
                    self.last_error = "YouTube: " + str(exc)[:150]
                time.sleep(seconds)
        threading.Thread(target=loop, name="youtube-poll", daemon=True).start()

    def candidates(self, client, sources: dict, now: datetime) -> list[dict]:
        window = timedelta(days=_int_env("YOUTUBE_WINDOW_DAYS", 3, 1, 30))
        gta6_only = self._gta6_only()
        channels = client.channels(list(sources))
        ids = []
        for info in channels:
            uploads = str(((info.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads", ""))
            ids += client.recent_upload_ids(uploads, limit=10)
        rows = [r for r in (video_row(x, now) for x in client.videos(ids)) if r]
        self.last_checked = len(rows)
        fresh = [r for r in rows if r["channel_id"] in sources
                 and now - datetime.fromisoformat(r["published_at"]) <= window
                 and eligible_for_autoclip(r, gta6_only=gta6_only)]
        per_channel = _int_env("YOUTUBE_AUTO_PER_CHANNEL", 1, 1, 4)
        fresh.sort(key=lambda r: (r["views_per_hour"], r["score"]), reverse=True)
        picked, count = [], {}
        for row in fresh:
            if count.get(row["channel_id"], 0) >= per_channel:
                continue
            count[row["channel_id"]] = count.get(row["channel_id"], 0) + 1
            picked.append(row)
        self.last_eligible = len(picked)
        return picked

    def _work(self, now: datetime | None = None):
        try:
            now = now or datetime.now(timezone.utc)
            self.last_run = now.isoformat(timespec="seconds")
            sources = authorized_sources(self.runtime.store.root)
            client = self.client_factory(api_key())
            quota = _int_env("YOUTUBE_AUTO_BATCH", 2, 1, 6)
            incoming = self.runtime.store.incoming
            self.last_error = None
            for row in self.candidates(client, sources, now):
                if quota <= 0:
                    break
                vid = row["id"]
                target = incoming / f"youtube-{vid}.mp4"
                if target.exists() or target.with_name(target.name + ".rights.json").exists():
                    continue
                if self.next_retry.get(vid, 0) > time.monotonic():
                    continue
                record(self.runtime, "start", "youtube", "video", row["channel_id"], vid,
                       source_name=str(sources[row["channel_id"]].get("creator", "")),
                       title=row["title"], trigger=self.trigger)
                try:
                    self.attempted += 1
                    self.downloader(vid, row["channel_id"], sources[row["channel_id"]], incoming,
                                    title=row["title"])
                    result = self.runtime.scan()  # única autoridade que enfileira o AutoClip
                    if not result["added"]:
                        self.last_error = "Download recebido, mas a ingestão rejeitou a mídia."
                        record(self.runtime, "finish", "youtube", vid, "failed", self.last_error)
                    else:
                        self.processed += 1
                        quota -= 1
                        record(self.runtime, "finish", "youtube", vid, "done")
                except (DownloadError, OSError, ValueError) as exc:
                    self.last_error = str(exc)[:190]
                    self.next_retry[vid] = time.monotonic() + 6 * 3600
                    record(self.runtime, "finish", "youtube", vid, "failed", self.last_error)
        except YouTubeError as exc:
            self.last_error = "YouTube: " + str(exc)[:160]
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.last_error = "Busca automática YouTube: " + str(exc)[:150]
        finally:
            with self.lock:
                self.running = False
                self.trigger = "automatico"

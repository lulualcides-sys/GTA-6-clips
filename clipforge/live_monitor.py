"""Monitor de lives da Twitch para streamers AUTORIZADOS.

A cada rodada consulta a API oficial Get Streams só para os IDs em
twitch_sources.json. Guarda o histórico de cada live (início, fim, título).
Quando uma live termina, busca a gravação (Get Videos type=archive) e, se o
proprietário ligou TWITCH_PUBLIC_DOWNLOAD=1 e TWITCH_LIVE_VOD_DOWNLOAD=1, baixa a
VOD pública via yt-dlp e a entrega à ingestão -> AutoClip. Não grava a live
enquanto ela acontece (exigiria capturar o stream continuamente); a VOD final é
a alternativa permitida e estável. Nunca aprova nem publica.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
import threading
import time
from datetime import datetime, timezone

from .ingest_log import record
from .twitch_download import DownloadError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _int_env(name: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(os.getenv(name, str(default)))))
    except ValueError:
        return default


class TwitchLiveMonitor:
    def __init__(self, runtime, *, downloader=None):
        self.runtime = runtime
        self.lock = threading.RLock()
        self.running = False
        self.last_run = None
        self.last_error = None
        self.live_now: list[dict] = []
        self._started = False
        if downloader is None:
            from .public_clip_download import download_public_vod as downloader
        self.downloader = downloader
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS live_sessions (
                stream_id TEXT PRIMARY KEY, broadcaster_id TEXT NOT NULL,
                broadcaster_name TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '',
                game_name TEXT NOT NULL DEFAULT '', started_at TEXT, ended_at TEXT,
                vod_id TEXT, status TEXT NOT NULL, error TEXT NOT NULL DEFAULT '')""")

    @contextmanager
    def _db(self):
        # Fecha a conexão de verdade: no Windows, SQLite aberto trava arquivos.
        conn = sqlite3.connect(self.runtime.store.database, timeout=20)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def enabled() -> bool:
        return os.getenv("TWITCH_LIVE_MONITOR", "1") == "1"

    @staticmethod
    def vod_download_enabled() -> bool:
        return (os.getenv("TWITCH_LIVE_VOD_DOWNLOAD", "0") == "1"
                and os.getenv("TWITCH_PUBLIC_DOWNLOAD", "0") == "1")

    def _sources(self) -> dict:
        return {s["broadcaster_id"]: s for s in self.runtime.twitch_auto._allowed_sources()}

    def _client(self):
        twitch = self.runtime.twitch
        if twitch.client is None and twitch.client_id and twitch.secret:
            from .twitch import TwitchClient
            twitch.client = TwitchClient(twitch.client_id, twitch.secret)
        return twitch.client

    def status(self) -> dict:
        with self._db() as db:
            rows = db.execute("SELECT * FROM live_sessions ORDER BY COALESCE(ended_at, started_at) DESC "
                              "LIMIT 30").fetchall()
        return {"enabled": self.enabled(), "vod_download": self.vod_download_enabled(),
                "running": self.running, "last_run": self.last_run, "last_error": self.last_error,
                "live_now": list(self.live_now), "sessions": [dict(r) for r in rows],
                "poll_seconds": _int_env("TWITCH_LIVE_POLL_SECONDS", 120, 60, 3600)}

    def check(self, trigger: str = "automatico") -> dict:
        """Uma rodada: atualiza lives, fecha as que terminaram e baixa a VOD."""
        with self.lock:
            if self.running:
                return {"started": False, "reason": "Rodada já em andamento"}
            self.running = True
        try:
            self.last_run = _now()
            sources = self._sources()
            client = self._client()
            if not sources:
                self.last_error = "Nenhum streamer autorizado para monitorar."
                return {"started": True, "live": 0}
            if client is None:
                self.last_error = "Conecte a Twitch (Client ID/Secret) para monitorar lives."
                return {"started": True, "live": 0}
            streams = client.get_streams(list(sources))
            live_ids = set()
            now = _now()
            with self.lock, self._db() as db:
                for stream in streams:
                    sid, uid = str(stream.get("id", "")), str(stream.get("user_id", ""))
                    if not sid or uid not in sources:
                        continue
                    live_ids.add(sid)
                    db.execute("""INSERT INTO live_sessions
                        (stream_id,broadcaster_id,broadcaster_name,title,game_name,started_at,status)
                        VALUES (?,?,?,?,?,?,'live') ON CONFLICT(stream_id) DO UPDATE SET
                        title=excluded.title, game_name=excluded.game_name, status='live'""",
                               (sid, uid, str(stream.get("user_name", ""))[:80],
                                str(stream.get("title", ""))[:200], str(stream.get("game_name", ""))[:80],
                                str(stream.get("started_at") or now)))
                ended = [dict(r) for r in db.execute("SELECT * FROM live_sessions WHERE status='live'")
                         if r["stream_id"] not in live_ids]
                for row in ended:
                    db.execute("UPDATE live_sessions SET status='ended', ended_at=? WHERE stream_id=?",
                               (now, row["stream_id"]))
            self.live_now = [{"broadcaster_id": str(s.get("user_id")), "name": s.get("user_name", ""),
                              "title": s.get("title", ""), "game": s.get("game_name", ""),
                              "viewers": s.get("viewer_count", 0)}
                             for s in streams if str(s.get("user_id")) in sources]
            for row in ended:
                self._handle_ended(client, row, sources, trigger)
            self.last_error = None
            return {"started": True, "live": len(self.live_now), "ended": len(ended)}
        except Exception as exc:  # noqa: BLE001 - laço de fundo não pode morrer
            self.last_error = "Monitor de lives: " + str(exc)[:160]
            return {"started": True, "error": self.last_error}
        finally:
            with self.lock:
                self.running = False

    def _set(self, stream_id: str, **fields) -> None:
        keys = ", ".join(f"{k}=?" for k in fields)
        with self.lock, self._db() as db:
            db.execute(f"UPDATE live_sessions SET {keys} WHERE stream_id=?", (*fields.values(), stream_id))

    def _handle_ended(self, client, row: dict, sources: dict, trigger: str) -> None:
        sid, uid = row["stream_id"], row["broadcaster_id"]
        try:
            vod = client.get_latest_vod(uid)
        except Exception as exc:  # noqa: BLE001
            self._set(sid, status="vod_error", error=str(exc)[:200])
            return
        if not vod or str(vod.get("stream_id", sid)) not in {sid, ""}:
            self._set(sid, status="no_vod", error="A Twitch não publicou a gravação desta live.")
            return
        vod_id = str(vod.get("id", ""))
        self._set(sid, vod_id=vod_id)
        if not self.vod_download_enabled():
            self._set(sid, status="vod_found",
                      error="VOD encontrada; ative o download de VODs para cortar automaticamente.")
            return
        source = sources[uid]
        manifest = {**source, "broadcaster_id": uid}
        record(self.runtime, "start", "twitch", "vod", uid, vod_id,
               source_name=source.get("creator", ""), title=row.get("title", ""), trigger=trigger)
        try:
            self.downloader(vod_id, uid, manifest, self.runtime.store.incoming,
                            max_minutes=_int_env("TWITCH_VOD_MAX_MINUTES", 180, 5, 600))
            result = self.runtime.scan()
            if not result["added"]:
                raise DownloadError("VOD recebida, mas a ingestão rejeitou a mídia.")
            self._set(sid, status="vod_downloaded", error="")
            record(self.runtime, "finish", "twitch", vod_id, "done")
        except (DownloadError, OSError, ValueError) as exc:
            self._set(sid, status="vod_failed", error=str(exc)[:200])
            record(self.runtime, "finish", "twitch", vod_id, "failed", str(exc))

    def start_polling(self) -> None:
        if not self.enabled() or self._started:
            return
        self._started = True
        seconds = _int_env("TWITCH_LIVE_POLL_SECONDS", 120, 60, 3600)

        def loop():
            time.sleep(30)
            while True:
                self.check()
                time.sleep(seconds)
        threading.Thread(target=loop, name="twitch-live-monitor", daemon=True).start()

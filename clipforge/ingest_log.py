"""Histórico e fila de entradas (downloads) de Twitch/YouTube, persistido em SQLite.

Cada item baixado (ou tentado) pelo radar vira uma linha com plataforma, origem,
status, se foi automático ou manual e o erro real. Nada é inventado: só os
módulos de download escrevem aqui.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

PLATFORMS = {"twitch", "youtube"}
KINDS = {"clip", "video", "vod"}
STATUSES = {"queued", "downloading", "done", "failed", "skipped"}
TRIGGERS = {"automatico", "manual"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class IngestLog:
    def __init__(self, database: Path, lock: threading.RLock):
        self.database = Path(database)
        self.lock = lock
        with self.lock, self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS ingest_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL, kind TEXT NOT NULL,
                source_id TEXT NOT NULL, source_name TEXT NOT NULL DEFAULT '',
                item_id TEXT NOT NULL, title TEXT NOT NULL DEFAULT '',
                trigger TEXT NOT NULL, status TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                UNIQUE(platform, item_id))""")

    @contextmanager
    def _db(self):
        # Fecha a conexão de verdade: no Windows, SQLite aberto trava arquivos.
        conn = sqlite3.connect(self.database, timeout=20)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def start(self, platform: str, kind: str, source_id: str, item_id: str, *,
              source_name: str = "", title: str = "", trigger: str = "automatico") -> None:
        """Marca o item como em download (cria ou reabre a linha)."""
        if platform not in PLATFORMS or kind not in KINDS or trigger not in TRIGGERS:
            raise ValueError("Entrada de histórico inválida")
        now = _now()
        with self.lock, self._db() as db:
            db.execute("""INSERT INTO ingest_jobs
                (platform,kind,source_id,source_name,item_id,title,trigger,status,error,attempts,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,'downloading','',1,?,?)
                ON CONFLICT(platform,item_id) DO UPDATE SET
                  status='downloading', error='', trigger=excluded.trigger,
                  attempts=ingest_jobs.attempts+1, updated_at=excluded.updated_at""",
                       (platform, kind, str(source_id)[:64], str(source_name)[:120],
                        str(item_id)[:180], str(title)[:200], trigger, now, now))

    def finish(self, platform: str, item_id: str, status: str, error: str = "") -> None:
        if status not in STATUSES:
            raise ValueError("Status inválido")
        with self.lock, self._db() as db:
            db.execute("UPDATE ingest_jobs SET status=?, error=?, updated_at=? WHERE platform=? AND item_id=?",
                       (status, " ".join(str(error).split())[:300], _now(), platform, str(item_id)[:180]))

    def list(self, limit: int = 100, status: str | None = None) -> list[dict]:
        limit = max(1, min(500, int(limit)))
        with self.lock, self._db() as db:
            if status in STATUSES:
                rows = db.execute("SELECT * FROM ingest_jobs WHERE status=? ORDER BY updated_at DESC LIMIT ?",
                                  (status, limit)).fetchall()
            else:
                rows = db.execute("SELECT * FROM ingest_jobs ORDER BY updated_at DESC LIMIT ?",
                                  (limit,)).fetchall()
        return [dict(r) for r in rows]

    def counts(self) -> dict:
        with self.lock, self._db() as db:
            rows = db.execute("SELECT status, COUNT(*) n FROM ingest_jobs GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}

    def failures_since(self, hours: float = 24) -> list[dict]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
        with self.lock, self._db() as db:
            rows = db.execute("SELECT * FROM ingest_jobs WHERE status='failed' AND updated_at>=? "
                              "ORDER BY updated_at DESC LIMIT 50", (since,)).fetchall()
        return [dict(r) for r in rows]


def record(runtime, action: str, *args, **kwargs) -> None:
    """Grava no histórico se o runtime tiver um (testes usam runtimes simplificados)."""
    log = getattr(runtime, "ingest_log", None)
    if log is None:
        return
    try:
        getattr(log, action)(*args, **kwargs)
    except (ValueError, sqlite3.Error):
        pass  # histórico nunca derruba um download

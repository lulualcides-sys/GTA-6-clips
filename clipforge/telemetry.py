"""Persistent, truthful telemetry for the GTA-6 Clips control room.

This is a visual representation of existing pipeline modules, NOT independent
AI agents. Every activity item comes from a real state transition or action.
Never seed demo/fake activity in a production database.
"""
from __future__ import annotations

import re
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

AGENTS = (
    ("radar", "RADAR", "Twitch · descoberta"),
    ("ingestao", "INGESTÃO", "Arquivo local autorizado"),
    ("direitos", "DIREITOS", "Manifesto e permissão"),
    ("curadoria", "CURADORIA", "Áudio e cenas"),
    ("edicao", "EDIÇÃO", "FFmpeg · vídeo 9:16"),
    ("legendas", "LEGENDAS", "Whisper · transcrição"),
    ("motion", "MOTION", "HyperFrames · composição"),
    ("revisao", "REVISÃO", "Aprovação editorial"),
    ("publicacao", "PUBLICAÇÃO", "Redes · ainda não conectadas"),
)
KNOWN = {entry[0] for entry in AGENTS}
STATES = {"queued", "running", "complete", "failed", "waiting", "blocked", "idle"}
CLIP_ID = re.compile(r"^[a-zA-Z0-9]{12}$")


class ActivityLog:
    """A minimal append-only audit trail in the SAME persistent SQLite volume."""

    def __init__(self, database: Path, lock: threading.RLock):
        self.database = database
        self.lock = lock
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS agent_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clip_id TEXT,
                agent TEXT NOT NULL,
                state TEXT NOT NULL,
                message TEXT NOT NULL,
                at TEXT NOT NULL
            )""")
            db.execute("""CREATE INDEX IF NOT EXISTS idx_agent_activity_clip
                          ON agent_activity(clip_id, id DESC)""")
            db.commit()

    def _db(self):
        db = sqlite3.connect(self.database, timeout=20)
        db.row_factory = sqlite3.Row
        return closing(db)

    def append(self, clip_id: str | None, agent: str,
               state: str, message: str) -> int:
        if agent not in KNOWN or state not in STATES:
            raise ValueError("Invalid telemetry agent or state")
        if clip_id is not None and not CLIP_ID.fullmatch(clip_id):
            raise ValueError("Invalid telemetry clip ID")
        # Fixed messages from backend only. Never log paths, secrets, chat or transcripts.
        detail = " ".join(str(message).split())[:220]
        if not detail:
            raise ValueError("Empty telemetry message")
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        with self.lock, self._db() as db:
            cursor = db.execute(
                "INSERT INTO agent_activity (clip_id,agent,state,message,at) "
                "VALUES (?,?,?,?,?)", (clip_id, agent, state, detail, now)
            )
            event_id = cursor.lastrowid
            # Hard cap history: keeps SQLite small on a continuously running worker.
            if event_id % 100 == 0:
                db.execute(
                    "DELETE FROM agent_activity WHERE id < ?",
                    (max(0, event_id - 3000),)
                )
            db.commit()
        return int(event_id)

    def recent(self, clip_id: str | None = None, limit: int = 60) -> list[dict]:
        limit = min(120, max(1, int(limit)))
        with self._db() as db:
            if clip_id:
                rows = db.execute(
                    "SELECT id,clip_id,agent,state,message,at FROM agent_activity "
                    "WHERE clip_id=? ORDER BY id DESC LIMIT ?",
                    (clip_id, limit),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT id,clip_id,agent,state,message,at FROM agent_activity "
                    "ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
        return [dict(row) for row in rows]

    def snapshot(self, runtime, clip_id: str | None = None) -> dict:
        """Return operational truth for a single selected clip or global overview."""
        if clip_id is not None and not CLIP_ID.fullmatch(clip_id):
            raise ValueError("Invalid clip ID")
        clip = runtime.store.get(clip_id) if clip_id else None
        if clip_id and not clip:
            raise LookupError("Clip not found")
        clips = runtime.store.all()
        caption_jobs = runtime.captions.all_statuses()

        activity = self.recent(clip_id, 80)
        latest: dict[str, dict] = {}
        for item in activity:
            if item["agent"] not in latest:
                latest[item["agent"]] = item

        twitch = runtime.twitch.status()
        captions = runtime.captions.status(clip_id) if clip else {}
        caption_state = captions.get("status", "not_started")
        stages = []
        for key, name, description in AGENTS:
            event = latest.get(key)
            stage = {
                "id": key,
                "name": name,
                "description": description,
                "state": event["state"] if event else "idle",
                "message": event["message"] if event else "",
                "updated_at": event["at"] if event else None,
            }
            if key == "radar":
                # Being configured/monitoring is different from processing right now.
                stage["state"] = ("blocked" if not twitch["configured"]
                                  else "waiting")
                stage["message"] = ("OAuth da Twitch não configurado" if not twitch["configured"]
                                    else "Monitor de metadados configurado"
                                    if twitch["auto_monitoring"]
                                    else "Busca de metadados manual")
                if twitch.get("last_error"):
                    stage["state"] = "failed"
                    stage["message"] = "Última consulta Twitch apresentou erro"
            elif key == "legendas" and clip:
                if caption_state in {"queued", "processing"}:
                    stage["state"] = "queued" if caption_state == "queued" else "running"
                    stage["message"] = ("Na fila de transcrição" if caption_state == "queued"
                                        else "Modelo processando áudio")
                elif caption_state == "ready":
                    stage["state"] = "complete"
                    stage["message"] = ("Legenda salva com timestamps reais"
                                        if captions.get("cues", 0) else
                                        "Transcrição terminada sem falas detectadas")
                elif caption_state in {"failed", "stale"}:
                    stage["state"] = "failed"
                    stage["message"] = ("Legendas desatualizadas" if caption_state == "stale"
                                        else "Falha na transcrição")
                elif not runtime.captions.available():
                    stage["state"] = "blocked"
                    stage["message"] = "Instale o módulo opcional faster-whisper"
                else:
                    stage["state"] = "waiting"
                    stage["message"] = "Aguardando solicitação de transcrição"
            elif key == "revisao" and clip:
                if clip["status"] == "ready":
                    stage["state"] = "waiting"
                    stage["message"] = "Clipe pronto para aprovação manual"
                elif clip["status"] == "approved":
                    stage["state"] = "complete"
                    stage["message"] = "Aprovação editorial registrada"
                elif clip["status"] == "rejected":
                    stage["state"] = "failed"
                    stage["message"] = "Rejeitado na revisão manual"
            elif key == "edicao" and not clip:
                running = sum(c["status"] == "rendering" for c in clips)
                queued = sum(c["status"] == "queued" for c in clips)
                stage["state"] = "running" if running else "queued" if queued else "idle"
                stage["message"] = (
                    f"{running} clipe(s) renderizando" if running
                    else f"{queued} clipe(s) aguardando render" if queued
                    else "Nenhum render em execução"
                )
            elif key == "legendas" and not clip:
                processing = sum(j["status"] == "processing" for j in caption_jobs.values())
                queued = sum(j["status"] == "queued" for j in caption_jobs.values())
                stage["state"] = ("running" if processing else
                                  "queued" if queued else
                                  "idle" if runtime.captions.available() else "blocked")
                stage["message"] = (
                    f"{processing} transcrição(ões) executando" if processing
                    else f"{queued} transcrição(ões) aguardando" if queued
                    else "Nenhuma transcrição ativa" if runtime.captions.available()
                    else "Módulo faster-whisper não instalado"
                )
            elif key == "revisao" and not clip:
                pending = sum(c["status"] == "ready" for c in clips)
                stage["state"] = "waiting" if pending else "idle"
                stage["message"] = (f"{pending} clipe(s) aguardando revisão" if pending
                                    else "Nenhum clipe aguardando aprovação")
            elif key == "motion" and clip and not event:
                if clip["status"] in {"ready", "approved"}:
                    stage["state"] = "waiting"
                    stage["message"] = "Exportação HyperFrames disponível"
            elif key == "publicacao":
                stage["state"] = "blocked"
                stage["message"] = "Nenhuma integração de postagem GTA habilitada"
            stages.append(stage)

        counts = {
            "total": len(clips),
            "in_progress": sum(i["status"] in {"queued", "rendering"} for i in clips),
            "review": sum(i["status"] == "ready" for i in clips),
            "approved": sum(i["status"] == "approved" for i in clips),
            "failed": sum(i["status"] == "failed" for i in clips),
        }
        return {
            "selected_clip": clip_id,
            "clip_status": clip["status"] if clip else None,
            "stages": stages,
            "activity": activity,
            "counts": counts,
            "twitch_configured": twitch["configured"],
            "auto_scan": runtime.auto_scan,
            "auto_render": runtime.auto_render,
            "auto_transcribe": runtime.auto_transcribe,
            "transcription_available": runtime.captions.available(),
            "publishing_connected": False,
            "mode": "real_activity_only",
        }

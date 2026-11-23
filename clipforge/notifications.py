"""Notificações de falha reunidas de fontes reais (sem eventos inventados).

Junta: downloads que falharam (histórico), edições AutoClip com erro,
publicações que falharam e o último erro de cada automação em segundo plano.
Cada item diz se veio de uma ação automática ou manual.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def collect(runtime, publishing=None, hours: float = 24) -> dict:
    items = []
    log = getattr(runtime, "ingest_log", None)
    if log is not None:
        for row in log.failures_since(hours):
            items.append({"area": "download", "platform": row["platform"],
                          "automatic": row["trigger"] == "automatico",
                          "title": row["title"] or row["item_id"], "message": row["error"],
                          "at": row["updated_at"]})
    bridge = getattr(runtime, "autoclip_bridge", None)
    if bridge is not None:
        for clip_id, job in bridge.status().get("jobs", {}).items():
            if job.get("status") == "failed":
                items.append({"area": "autoclip", "platform": "", "automatic": True,
                              "title": clip_id, "message": job.get("error", "Falha no AutoClip"),
                              "at": job.get("finished_at", "")})
    if publishing is not None:
        cutoff = time.time() - hours * 3600
        for job in publishing.all():
            if job.get("status") == "failed" and float(job.get("updated_at") or 0) >= cutoff:
                items.append({"area": "publicacao", "platform": job.get("platform", ""),
                              "automatic": bool(job.get("automatic")),
                              "title": job.get("title", ""), "message": job.get("error") or "Falha",
                              "at": _iso(float(job["updated_at"]))})
    for area, attr in (("twitch", "twitch_auto"), ("youtube", "youtube_auto"), ("lives", "live_monitor")):
        worker = getattr(runtime, attr, None)
        error = getattr(worker, "last_error", None) if worker is not None else None
        if error:
            items.append({"area": "automacao", "platform": area, "automatic": True,
                          "title": f"Automação {area}", "message": str(error), "at": ""})
    items.sort(key=lambda x: x.get("at") or "", reverse=True)
    return {"count": len(items), "items": items[:100]}

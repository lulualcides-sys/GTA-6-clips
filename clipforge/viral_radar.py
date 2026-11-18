"""Radar viral BR: clipes com potencial viral e streamers para pedir permissão.

Somente METADADOS da Twitch (views, idade, duração, idioma, título). Não baixa
mídia. O potencial viral é uma estimativa por métricas públicas, não garante
viralização nem entende o conteúdo do vídeo. Download/edição só acontecem para
streamers marcados como autorizados (twitch_sources.json), pelo pipeline oficial.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .curation import qualifies, ranked_shortlist

MAX_SOURCES = 100


def _is_pt(item: dict) -> bool:
    lang = str(item.get("language", "") or "").lower().replace("_", "-")
    return lang == "pt" or lang.startswith("pt-")


def _sources_file(root: Path) -> Path:
    return Path(root) / "twitch_sources.json"


def read_sources(root: Path) -> list[dict]:
    path = _sources_file(root)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 64_000:
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = data.get("broadcasters") if isinstance(data, dict) else None
    return [r for r in rows[:MAX_SOURCES] if isinstance(r, dict)] if isinstance(rows, list) else []


def authorized_ids(root: Path) -> set[str]:
    result = set()
    for row in read_sources(root):
        ident = str(row.get("id", "")).strip()
        rights = row.get("rights_status")
        evidence = str(row.get("evidence", "")).strip()
        if ident.isdigit() and rights in {"owned", "permission_granted"} and (
                rights == "owned" or len(evidence) >= 8):
            result.add(ident)
    return result


def add_source(root: Path, broadcaster_id: str, creator: str,
               rights_status: str, evidence: str) -> dict:
    """Registra autorização declarada pelo proprietário (com evidência)."""
    broadcaster_id = str(broadcaster_id or "").strip()
    creator = " ".join(str(creator or "").split())[:80]
    evidence = " ".join(str(evidence or "").split())[:500]
    if not broadcaster_id.isdigit() or len(broadcaster_id) > 20:
        raise ValueError("ID do streamer inválido.")
    if not creator:
        raise ValueError("Nome do streamer obrigatório.")
    if rights_status not in {"owned", "permission_granted"}:
        raise ValueError("Tipo de direito inválido.")
    if rights_status == "permission_granted" and len(evidence) < 8:
        raise ValueError("Descreva a permissão (onde e quando o streamer autorizou).")
    path = _sources_file(root)
    if path.is_symlink():
        raise ValueError("Arquivo de fontes inválido.")
    rows = [r for r in read_sources(root) if str(r.get("id", "")) != broadcaster_id]
    if len(rows) >= MAX_SOURCES:
        raise ValueError("Limite de 100 streamers autorizados.")
    rows.append({"id": broadcaster_id, "creator": creator, "rights_status": rights_status,
                 "evidence": evidence,
                 "added_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"broadcasters": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return {"id": broadcaster_id, "creator": creator, "rights_status": rights_status}


def remove_source(root: Path, broadcaster_id: str) -> bool:
    rows = read_sources(root)
    kept = [r for r in rows if str(r.get("id", "")) != str(broadcaster_id)]
    if len(kept) == len(rows):
        return False
    path = _sources_file(root)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"broadcasters": kept}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return True


def radar(runtime, *, pt_only: bool = True, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    profile = runtime.twitch.profile(now)
    gta6 = profile["profile"] == "gta6_only"
    try:
        min_score = max(0, min(100, int(os.getenv("TWITCH_AUTO_MIN_SCORE", "78"))))
    except ValueError:
        min_score = 78
    items = runtime.twitch.list_candidates(limit=1000)
    if pt_only:
        items = [i for i in items if _is_pt(i)]
    allowed = authorized_ids(runtime.store.root)
    viral = ranked_shortlist(items, min_score=min_score, per_creator=3,
                             gta6_only=gta6, now=now)[:40]
    clips = [{
        "id": str(c.get("id", "")), "title": str(c.get("title", ""))[:140],
        "creator_name": str(c.get("creator_name", ""))[:80],
        "broadcaster_id": str(c.get("broadcaster_id", "")),
        "url": str(c.get("url", "")), "view_count": int(c.get("view_count", 0) or 0),
        "duration": float(c.get("duration", 0) or 0), "score": int(c.get("score", 0) or 0),
        "created_at": str(c.get("created_at", "")), "language": str(c.get("language", "")),
        "authorized": str(c.get("broadcaster_id", "")) in allowed,
    } for c in viral]
    streamers: dict[str, dict] = {}
    for item in items:
        ident = str(item.get("broadcaster_id", ""))
        if not ident.isdigit():
            continue
        row = streamers.setdefault(ident, {
            "broadcaster_id": ident, "name": str(item.get("creator_name", ""))[:80],
            "clips": 0, "viral_clips": 0, "total_views": 0, "best_score": 0,
            "authorized": ident in allowed})
        row["clips"] += 1
        row["total_views"] += int(item.get("view_count", 0) or 0)
        row["best_score"] = max(row["best_score"], int(item.get("score", 0) or 0))
        if qualifies(item, min_score=min_score, now=now, gta6_only=gta6):
            row["viral_clips"] += 1
    ranking = sorted(streamers.values(),
                     key=lambda r: (r["viral_clips"], r["total_views"]), reverse=True)[:25]
    for row in ranking:
        row["twitch_url"] = "https://www.twitch.tv/" + "".join(
            ch for ch in row["name"].lower() if ch.isalnum() or ch == "_")
    return {"profile": profile["profile"], "focus_game": profile["focus_game"],
            "pt_only": pt_only, "min_score": min_score, "clips": clips,
            "streamers": ranking, "authorized_count": len(allowed),
            "scanned": len(items)}

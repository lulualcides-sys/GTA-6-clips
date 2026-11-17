"""Cheap GTA VI clip preselection BEFORE downloading expensive media.

Scores use Twitch metadata, not visual/semantic judgment. Only the real
AutoClip engine analyzes footage; an editorial approval is still required.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

GTA6_NAMES = {"grand theft auto vi", "grand theft auto 6"}
GENERIC_TITLES = {
    "clip", "clipe", "clips", "highlights", "highlight", "untitled",
    "sem titulo", "gta6", "gta 6", "gta vi", "grand theft auto vi",
    "grand theft auto 6", "gameplay", "video", "stream", "live",
    "clip 1", "clip 2", "clipe 1", "clipe 2",
}


def normalized_title(value: str) -> str:
    title = unicodedata.normalize("NFKD", str(value or ""))
    title = "".join(c for c in title if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", title.casefold()).strip()


def qualifies(item: dict, *, min_score: int = 78,
              now: datetime | None = None, gta6_only: bool = True) -> bool:
    """Preselect likely worthwhile candidates; quality is never guaranteed."""
    if gta6_only and str(item.get("game_name", "")).casefold() not in GTA6_NAMES:
        return False
    try:
        score = int(item.get("score", 0) or 0)
        duration = float(item.get("duration", 0) or 0)
        views = int(item.get("view_count", 0) or 0)
    except (ValueError, TypeError, OverflowError):
        return False
    if score < min_score or not 14 <= duration <= 70:
        return False
    title = normalized_title(str(item.get("title", "")))
    if not title or title in GENERIC_TITLES:
        return False
    now = now or datetime.now(timezone.utc)
    try:
        created = datetime.fromisoformat(str(item.get("created_at", "")).replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_hours = max(0, (now - created).total_seconds() / 3600)
    except (ValueError, TypeError, OverflowError):
        return False
    # Early clips need less accumulated engagement than 1-2 day-old clips.
    min_views = 30 if age_hours <= 2 else 100 if age_hours <= 18 else 250
    if views < min_views:
        return False
    return True


def ranked_shortlist(items: list[dict], *, min_score: int = 78, 
                     per_creator: int = 2, gta6_only: bool = True,
                     now: datetime | None = None) -> list[dict]:
    """Deduplicate by official clip ID and near-equal titles per creator."""
    now = now or datetime.now(timezone.utc)
    per_creator = max(1, min(4, per_creator))
    picked = []
    clip_ids = set()
    seen_titles = set()
    creator_counts = {}
    def sort_key(item):
        return (int(item.get("score", 0) or 0),
                int(item.get("view_count", 0) or 0))
    for item in sorted(items, key=sort_key, reverse=True):
        if not qualifies(item, min_score=min_score, now=now, gta6_only=gta6_only):
            continue
        clip_id = str(item.get("id", ""))
        creator = str(item.get("broadcaster_id", ""))
        key = (creator, normalized_title(item.get("title", "")))
        if not clip_id or clip_id in clip_ids or key in seen_titles:
            continue
        if creator_counts.get(creator, 0) >= per_creator:
            continue
        picked.append(item)
        clip_ids.add(clip_id)
        seen_titles.add(key)
        creator_counts[creator] = creator_counts.get(creator, 0) + 1
    return picked

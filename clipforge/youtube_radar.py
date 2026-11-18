"""Radar YouTube BR: vídeos em alta de YouTubers grandes e canais para pedir permissão.

Somente METADADOS pela YouTube Data API v3 oficial (chave de API do próprio
usuário; cota gratuita de 10.000 unidades/dia). Não baixa mídia. A nota é uma
estimativa por métricas públicas (views por hora, engajamento, idioma, duração),
não entende o conteúdo nem garante viralização. Download/edição só acontecem
para canais marcados como autorizados (youtube_sources.json), pelo
`youtube_auto`, e somente com YOUTUBE_PUBLIC_DOWNLOAD=1.
"""
from __future__ import annotations

import json
import math
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .viral_radar import policy_hint

API = "https://www.googleapis.com/youtube/v3/"
CHANNEL_RE = re.compile(r"UC[A-Za-z0-9_-]{22}")
VIDEO_RE = re.compile(r"[A-Za-z0-9_-]{11}")
GTA6_RE = re.compile(r"\bgta\s*(?:6|vi)\b|grand\s+theft\s+auto\s+(?:6|vi)\b", re.IGNORECASE)
MAX_SOURCES = 100
CACHE_TTL = 1800          # 30 min: ~48 atualizações/dia cabem na cota gratuita
MIN_MANUAL_REFRESH = 300  # botão "Atualizar" não gasta cota em rajadas
_cache_lock = threading.Lock()


class YouTubeError(RuntimeError):
    pass


def api_key() -> str:
    return os.getenv("YOUTUBE_API_KEY", "").strip()


def _int_env(name: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(os.getenv(name, str(default)))))
    except ValueError:
        return default


def min_subscribers() -> int:
    return _int_env("YOUTUBE_MIN_SUBSCRIBERS", 100_000, 0, 1_000_000_000)


def max_seconds() -> int:
    return _int_env("YOUTUBE_MAX_MINUTES", 60, 2, 120) * 60


class YouTubeAPI:
    """Cliente mínimo e somente leitura. A chave nunca aparece em erros ou logs."""

    def __init__(self, key: str, *, opener=urlopen):
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,60}", key or ""):
            raise YouTubeError("Chave da YouTube Data API inválida.")
        self.key, self.opener = key, opener

    def get(self, path: str, **params) -> dict:
        query = urlencode({**{k: v for k, v in params.items() if v not in (None, "")}, "key": self.key})
        request = Request(API + path + "?" + query, headers={"Accept": "application/json"})
        try:
            with self.opener(request, timeout=20) as response:
                data = json.loads(response.read(4_000_000))
        except HTTPError as exc:
            reason = ""
            try:
                body = json.loads(exc.read(200_000))
                reason = str(((body.get("error") or {}).get("errors") or [{}])[0].get("reason", ""))
            except (ValueError, AttributeError, IndexError, TypeError, OSError):
                pass
            if reason == "quotaExceeded":
                raise YouTubeError("Cota diária da YouTube Data API esgotada; volta amanhã.") from None
            if exc.code in (400, 403) and reason in {"keyInvalid", "badRequest", "forbidden",
                                                       "accessNotConfigured", "ipRefererBlocked"}:
                raise YouTubeError(f"Chave recusada pelo YouTube ({reason}). Ative a YouTube Data API v3 "
                                   "no Google Cloud e confira a chave.") from None
            raise YouTubeError(f"YouTube respondeu HTTP {exc.code}.") from None
        except (URLError, OSError, ValueError) as exc:
            raise YouTubeError("Falha de rede ao consultar o YouTube.") from exc
        if not isinstance(data, dict):
            raise YouTubeError("Resposta inválida do YouTube.")
        return data

    def most_popular_gaming(self, region="BR", limit=50) -> list[dict]:
        """chart=mostPopular na categoria Jogos (1 unidade de cota)."""
        data = self.get("videos", part="snippet,statistics,contentDetails", chart="mostPopular",
                        regionCode=region, videoCategoryId="20", maxResults=min(50, limit))
        return [x for x in data.get("items", []) if isinstance(x, dict)]

    def search_ids(self, query: str, published_after: str, region="BR", limit=25) -> list[str]:
        """search.list custa 100 unidades: usar com parcimônia (cache)."""
        data = self.get("search", part="id", type="video", q=query, order="viewCount",
                        regionCode=region, relevanceLanguage="pt", publishedAfter=published_after,
                        maxResults=min(50, limit), safeSearch="none")
        ids = []
        for item in data.get("items", []):
            vid = str(((item or {}).get("id") or {}).get("videoId", ""))
            if VIDEO_RE.fullmatch(vid):
                ids.append(vid)
        return ids

    def videos(self, ids: list[str]) -> list[dict]:
        out = []
        ids = [i for i in dict.fromkeys(ids) if VIDEO_RE.fullmatch(i)]
        for start in range(0, len(ids), 50):
            data = self.get("videos", part="snippet,statistics,contentDetails",
                            id=",".join(ids[start:start + 50]), maxResults=50)
            out += [x for x in data.get("items", []) if isinstance(x, dict)]
        return out

    def channels(self, ids: list[str]) -> list[dict]:
        out = []
        ids = [i for i in dict.fromkeys(ids) if CHANNEL_RE.fullmatch(i)]
        for start in range(0, len(ids), 50):
            data = self.get("channels", part="snippet,statistics,contentDetails",
                            id=",".join(ids[start:start + 50]), maxResults=50)
            out += [x for x in data.get("items", []) if isinstance(x, dict)]
        return out

    def recent_upload_ids(self, uploads_playlist: str, limit=10) -> list[str]:
        if not re.fullmatch(r"UU[A-Za-z0-9_-]{22}", uploads_playlist or ""):
            return []
        data = self.get("playlistItems", part="contentDetails", playlistId=uploads_playlist,
                        maxResults=min(50, limit))
        ids = [str(((x or {}).get("contentDetails") or {}).get("videoId", ""))
               for x in data.get("items", [])]
        return [i for i in ids if VIDEO_RE.fullmatch(i)]


# --------------------------------------------------------------------------
# Métricas a partir de metadados públicos.

def iso_duration(value: str) -> int:
    match = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", str(value or ""))
    if not match:
        return 0
    d, h, m, s = (int(x or 0) for x in match.groups())
    return d * 86400 + h * 3600 + m * 60 + s


def _parse_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def is_portuguese(item: dict) -> bool:
    snippet = item.get("snippet") or {}
    langs = [str(snippet.get(k, "") or "").lower() for k in ("defaultAudioLanguage", "defaultLanguage")]
    return any(lang == "pt" or lang.startswith("pt-") for lang in langs)


def is_gta6(item: dict) -> bool:
    snippet = item.get("snippet") or {}
    text = " ".join([str(snippet.get("title", "")), " ".join(map(str, snippet.get("tags") or []))])
    return bool(GTA6_RE.search(text))


def video_row(item: dict, now: datetime) -> dict | None:
    vid = str(item.get("id", ""))
    snippet = item.get("snippet") or {}
    stats = item.get("statistics") or {}
    channel = str(snippet.get("channelId", ""))
    if not VIDEO_RE.fullmatch(vid) or not CHANNEL_RE.fullmatch(channel):
        return None
    published = _parse_time(snippet.get("publishedAt", ""))
    if published is None:
        return None
    hours = max(1.0, (now - published).total_seconds() / 3600)
    views = int(stats.get("viewCount", 0) or 0)
    likes = int(stats.get("likeCount", 0) or 0)
    comments = int(stats.get("commentCount", 0) or 0)
    duration = iso_duration((item.get("contentDetails") or {}).get("duration", ""))
    live = str(snippet.get("liveBroadcastContent", "none") or "none")
    velocity = views / hours
    engagement = (likes + 2 * comments) / views if views else 0.0
    # 0–100: velocidade em escala log (1 mil/h ≈ 50, 100 mil/h ≈ 90) + engajamento.
    score = min(70.0, 14.0 * math.log10(1 + velocity)) + min(20.0, engagement * 400)
    if is_portuguese(item):
        score += 6
    if 120 <= duration <= max_seconds():
        score += 4
    return {
        "id": vid, "title": str(snippet.get("title", ""))[:160],
        "channel_id": channel, "channel_title": str(snippet.get("channelTitle", ""))[:80],
        "url": "https://www.youtube.com/watch?v=" + vid,
        "published_at": published.isoformat(timespec="seconds"),
        "views": views, "likes": likes, "comments": comments,
        "views_per_hour": int(velocity), "duration": duration, "live": live,
        "portuguese": is_portuguese(item), "gta6": is_gta6(item),
        "score": int(min(100, round(score))),
        "description": str(snippet.get("description", ""))[:1500],
    }


def eligible_for_autoclip(row: dict, *, gta6_only: bool) -> bool:
    """Vídeo longo o bastante para o AutoClip achar momentos e curto o bastante p/ a máquina."""
    return (row.get("live") == "none" and 120 <= int(row.get("duration", 0)) <= max_seconds()
            and (row.get("gta6") or not gta6_only))


# --------------------------------------------------------------------------
# Autorizações (youtube_sources.json) — mesmas regras de evidência da Twitch.

def _sources_file(root: Path) -> Path:
    return Path(root) / "youtube_sources.json"


def read_sources(root: Path) -> list[dict]:
    path = _sources_file(root)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 64_000:
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = data.get("channels") if isinstance(data, dict) else None
    return [r for r in rows[:MAX_SOURCES] if isinstance(r, dict)] if isinstance(rows, list) else []


def authorized_sources(root: Path) -> dict[str, dict]:
    result = {}
    for row in read_sources(root):
        ident = str(row.get("id", "")).strip()
        rights = row.get("rights_status")
        evidence = str(row.get("evidence", "")).strip()
        creator = str(row.get("creator", "")).strip()
        if (CHANNEL_RE.fullmatch(ident) and creator and rights in {"owned", "permission_granted"}
                and (rights == "owned" or len(evidence) >= 8)):
            result[ident] = {"channel_id": ident, "creator": creator,
                             "rights_status": rights, "evidence": evidence}
    return result


def _write_sources(root: Path, rows: list[dict]) -> None:
    path = _sources_file(root)
    if path.is_symlink():
        raise ValueError("Arquivo de fontes inválido.")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"channels": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def add_source(root: Path, channel_id: str, creator: str, rights_status: str, evidence: str) -> dict:
    channel_id = str(channel_id or "").strip()
    creator = " ".join(str(creator or "").split())[:80]
    evidence = " ".join(str(evidence or "").split())[:500]
    if not CHANNEL_RE.fullmatch(channel_id):
        raise ValueError("ID do canal YouTube inválido.")
    if not creator:
        raise ValueError("Nome do canal obrigatório.")
    if rights_status not in {"owned", "permission_granted"}:
        raise ValueError("Tipo de direito inválido.")
    if rights_status == "permission_granted" and len(evidence) < 8:
        raise ValueError("Descreva a permissão (onde e quando o YouTuber autorizou).")
    rows = [r for r in read_sources(root) if str(r.get("id", "")) != channel_id]
    if len(rows) >= MAX_SOURCES:
        raise ValueError("Limite de 100 canais autorizados.")
    rows.append({"id": channel_id, "creator": creator, "rights_status": rights_status,
                 "evidence": evidence,
                 "added_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    _write_sources(root, rows)
    return {"id": channel_id, "creator": creator, "rights_status": rights_status}


def remove_source(root: Path, channel_id: str) -> bool:
    rows = read_sources(root)
    kept = [r for r in rows if str(r.get("id", "")) != str(channel_id)]
    if len(kept) == len(rows):
        return False
    _write_sources(root, kept)
    return True


# --------------------------------------------------------------------------
# Radar com cache em disco (a cota é limitada).

def _cache_file(root: Path) -> Path:
    return Path(root) / "youtube_radar.json"


def _read_cache(root: Path) -> dict:
    path = _cache_file(root)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 2_000_000:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _channel_policy(channel: dict, videos: list[dict]) -> dict:
    """Restrição em qualquer descrição vence; liberação vale da descrição do canal ou vídeo."""
    texts = [("canal", str((channel.get("snippet") or {}).get("description", "")))]
    texts += [("vídeo", v.get("description", "")) for v in videos]
    hints = [(where, policy_hint(text)) for where, text in texts if text]
    for where, hint in hints:
        if hint["status"] == "restricted":
            return {**hint, "where": where}
    for where, hint in hints:
        if hint["status"] == "allowed":
            return {**hint, "where": where}
    return {"status": "unknown", "snippet": "", "where": ""}


def build_radar(client: YouTubeAPI, *, gta6_mode: bool, now: datetime) -> dict:
    items = client.most_popular_gaming()
    query = os.getenv("YOUTUBE_SEARCH_QUERY", "").strip()[:120] or ("GTA 6|GTA VI" if gta6_mode else "")
    searched = 0
    if query:
        after = (now - timedelta(days=_int_env("YOUTUBE_SEARCH_DAYS", 3, 1, 30))).strftime("%Y-%m-%dT%H:%M:%SZ")
        ids = client.search_ids(query, after)
        searched = len(ids)
        known = {str(x.get("id")) for x in items}
        items += client.videos([i for i in ids if i not in known])
    rows = [r for r in (video_row(x, now) for x in items) if r]
    by_channel: dict[str, list[dict]] = {}
    for row in rows:
        by_channel.setdefault(row["channel_id"], []).append(row)
    channels = {str(c.get("id")): c for c in client.channels(list(by_channel))}
    floor = min_subscribers()
    out_channels = []
    for ident, videos in by_channel.items():
        info = channels.get(ident) or {}
        stats = info.get("statistics") or {}
        hidden = bool(stats.get("hiddenSubscriberCount"))
        subs = int(stats.get("subscriberCount", 0) or 0)
        if not hidden and subs < floor:
            continue
        snippet = info.get("snippet") or {}
        handle = str(snippet.get("customUrl", "") or "")
        out_channels.append({
            "channel_id": ident,
            "name": str(snippet.get("title") or videos[0]["channel_title"])[:80],
            "url": ("https://www.youtube.com/" + handle) if handle.startswith("@")
                   else "https://www.youtube.com/channel/" + ident,
            "subscribers": None if hidden else subs,
            "country": str(snippet.get("country", "") or ""),
            "trending_videos": len(videos),
            "best_score": max(v["score"] for v in videos),
            "total_views": sum(v["views"] for v in videos),
            "uploads": str((info.get("contentDetails") or {}).get("relatedPlaylists", {}).get("uploads", "")),
            "policy": _channel_policy(info, videos),
        })
    famous = {c["channel_id"] for c in out_channels}
    out_channels.sort(key=lambda c: (c["best_score"], c["total_views"]), reverse=True)
    videos = sorted((r for r in rows if r["channel_id"] in famous),
                    key=lambda r: (r["score"], r["views_per_hour"]), reverse=True)
    for v in videos:
        v.pop("description", None)
    return {"updated_at": now.isoformat(timespec="seconds"), "query": query,
            "searched": searched, "videos": videos[:60], "channels": out_channels[:40],
            "quota_estimate": 1 + (100 if query else 0) + 1 + math.ceil(len(by_channel) / 50)}


def radar(runtime, *, force: bool = False, pt_only: bool = False, now: datetime | None = None,
          client: YouTubeAPI | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    root = runtime.store.root
    try:
        profile = runtime.twitch.profile(now)
    except (AttributeError, ValueError, TypeError, RuntimeError):
        profile = {"profile": "", "focus_game": ""}
    gta6_mode = profile.get("profile") == "gta6_only"
    allowed = authorized_sources(root)
    key = api_key()
    base = {"configured": bool(key), "gta6_mode": gta6_mode, "focus_game": profile.get("focus_game", ""),
            "authorized_count": len(allowed), "min_subscribers": min_subscribers(),
            "pt_only": pt_only, "error": None}
    with _cache_lock:
        cache = _read_cache(root)
        age = None
        stamp = _parse_time(cache.get("updated_at", "")) if cache else None
        if stamp:
            age = (now - stamp).total_seconds()
        stale = age is None or age >= CACHE_TTL or cache.get("gta6_mode") != gta6_mode
        if key and (stale or (force and age >= MIN_MANUAL_REFRESH)):
            try:
                client = client or YouTubeAPI(key)
                cache = {**build_radar(client, gta6_mode=gta6_mode, now=now), "gta6_mode": gta6_mode}
                path = _cache_file(root)
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".tmp")
                tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
                tmp.replace(path)
            except YouTubeError as exc:
                base["error"] = str(exc)
        elif not key:
            base["error"] = "Conecte o YouTube (chave da YouTube Data API) para ver o radar."
    videos = list(cache.get("videos", [])) if cache else []
    channels = list(cache.get("channels", [])) if cache else []
    if pt_only:
        videos = [v for v in videos if v.get("portuguese")]
        keep = {v["channel_id"] for v in videos}
        channels = [c for c in channels if c["channel_id"] in keep or c.get("country") == "BR"]
    for v in videos:
        v["authorized"] = v.get("channel_id") in allowed
        v["autoclip_ok"] = eligible_for_autoclip(v, gta6_only=gta6_mode)
    for c in channels:
        c["authorized"] = c.get("channel_id") in allowed
    return {**base, "updated_at": cache.get("updated_at") if cache else None,
            "query": cache.get("query", "") if cache else "",
            "quota_estimate": cache.get("quota_estimate", 0) if cache else 0,
            "videos": videos, "channels": channels}

"""Read-only Twitch Helix discovery: metadata, ranking and consent flags.

No download, no clip creation, no publication. A Twitch clip is NOT a license
to use another creator's video outside Twitch.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

# GTA V discovery until the planned GTA VI switch, 19 Nov at midnight Sao Paulo.
DEFAULT_GTA6_LAUNCH = "2026-11-19T03:00:00+00:00"
ALLOWED_CATEGORY_NAMES = {"grand theft auto vi", "grand theft auto 6"}
GTA5_CATEGORY_NAMES = {"grand theft auto v", "grand theft auto 5"}
# Bounds protect Twitch API quotas; not editorial exclusions.
DEFAULT_CATEGORY_LIMIT = 12
DEFAULT_CLIPS_PER_CATEGORY = 15
TWITCH_BASE = "https://api.twitch.tv/helix"
OAUTH_URL = "https://id.twitch.tv/oauth2/token"


class TwitchError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def configured_ids(name: str, limit: int) -> list[str]:
    """IDs explícitos, sem silenciosamente ignorar configurações inválidas."""
    values = list(dict.fromkeys(x.strip() for x in os.getenv(name, "").split(",") if x.strip()))
    if len(values) > limit or any(not x.isdigit() for x in values):
        raise TwitchError(f"{name}: informe até {limit} IDs numéricos separados por vírgula")
    return values


def clip_score(item: dict, now: datetime | None = None) -> int:
    """Rank metadata only; does not understand gameplay, emotion or humor."""
    now = now or datetime.now(timezone.utc)
    views = max(0, int(item.get("view_count", 0) or 0))
    duration = max(0.0, float(item.get("duration", 0) or 0))
    raw_date = str(item.get("created_at", "")).replace("Z", "+00:00")
    try:
        created = datetime.fromisoformat(raw_date)
        created = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
        age_hours = max(0.0, (now - created).total_seconds() / 3600)
    except ValueError:
        age_hours = 120.0
    popularity = min(62.0, 12 * math.log10(views + 1))
    freshness = max(0.0, 28.0 - age_hours * 0.3)
    usable = 10.0 if 18 <= duration <= 60 else (4.0 if 10 <= duration <= 90 else 0.0)
    # Prefer Portuguese clips for Brazilian audiences; other languages remain eligible.
    lang = str(item.get("language", "") or "").lower().replace("_", "-")
    language_bonus = 7.0 if lang == "pt" or lang.startswith("pt-") else 0.0
    return max(0, min(100, round(popularity + freshness + usable + language_bonus)))


def twitch_clip_url(url: str) -> bool:
    parsed = urlparse(str(url))
    return parsed.scheme == "https" and parsed.hostname in {
        "clips.twitch.tv", "www.twitch.tv", "twitch.tv"
    }


class TwitchClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._token = ""
        self._expires_at = 0.0

    def _token_value(self) -> str:
        if self._token and time.monotonic() < self._expires_at:
            return self._token
        data = urlencode({
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }).encode("ascii")
        req = Request(OAUTH_URL, data=data, method="POST",
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
        payload = self._send(req)
        token = payload.get("access_token")
        if not token:
            raise TwitchError("Twitch OAuth did not issue a token")
        self._token = str(token)
        self._expires_at = time.monotonic() + max(0, int(payload.get("expires_in", 3600)) - 30)
        return self._token

    def _send(self, request: Request) -> dict:
        try:
            with urlopen(request, timeout=12) as response:
                payload = response.read(1024 * 1024)
            result = json.loads(payload.decode("utf-8"))
            if not isinstance(result, dict):
                raise TwitchError("Invalid Twitch response")
            return result
        except HTTPError as exc:
            # Never put access tokens or response bodies into logs.
            raise TwitchError(f"Twitch API HTTP {exc.code}", status_code=exc.code) from exc
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            raise TwitchError("Twitch API request unavailable or invalid") from exc

    def _get(self, endpoint: str, params: dict) -> dict:
        query = urlencode(params, doseq=True)
        for attempt in range(2):
            req = Request(f"{TWITCH_BASE}/{endpoint}?{query}", headers={
                "Client-Id": self.client_id,
                "Authorization": f"Bearer {self._token_value()}",
                "Accept": "application/json",
            })
            try:
                return self._send(req)
            except TwitchError as exc:
                if exc.status_code != 401 or attempt:
                    raise
                self._token = ""
                self._expires_at = 0
        raise TwitchError("Twitch authentication unavailable")

    def get_categories(self, ids: list[str]) -> list[dict]:
        """Resolve IDs configurados pela API oficial, incluindo categorias IRL."""
        return list(self._get("games", {"id": ids[:12]}).get("data", []))

    def get_streams(self, broadcaster_ids: list[str]) -> list[dict]:
        """Polling leve; ausência na resposta indica offline, não falha de rede."""
        return list(self._get("streams", {"user_id": broadcaster_ids[:100], "first": 100}).get("data", []))

    def find_gta5_game(self) -> str:
        """Resolve the exact GTA V Twitch game category, not a similar title."""
        result = self._get("search/categories", {"query": "Grand Theft Auto V", "first": 30})
        for game in result.get("data", []):
            if str(game.get("name", "")).strip().lower() in GTA5_CATEGORY_NAMES:
                game_id = str(game.get("id", "")).strip()
                if game_id.isdigit():
                    return game_id
        raise TwitchError("GTA V category unavailable on Twitch; configure TWITCH_GTA5_GAME_ID")

    def find_gta6_game(self) -> str:
        result = self._get("search/categories", {"query": "Grand Theft Auto VI", "first": 30})
        for game in result.get("data", []):
            if str(game.get("name", "")).strip().lower() in ALLOWED_CATEGORY_NAMES:
                return str(game["id"])
        raise TwitchError("GTA VI category not yet available on Twitch; configure TWITCH_GAME_ID")

    def get_top_categories(self, limit: int = DEFAULT_CATEGORY_LIMIT) -> list[dict]:
        """The official Twitch top games/categories endpoint (includes IRL)."""
        records = self._get("games/top", {"first": max(1, min(100, limit))}).get("data", [])
        return [
            {"id": str(item["id"]), "name": str(item["name"])[:100]}
            for item in records if str(item.get("id", "")).isdigit()
            and str(item.get("name", "")).strip()
        ][:limit]

    def get_clips(self, game_id: str, lookback_hours: int = 72,
                  first: int = 100) -> list[dict]:
        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=lookback_hours)
        params = {
            "game_id": game_id, "first": max(1, min(100, first)),
            "started_at": since.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "ended_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
        # One page is intentional: predictable quotas and bounded dashboard processing.
        return list(self._get("clips", params).get("data", []))[:first]


class TwitchDiscovery:
    """Persist top public clip METADATA. Permission file stays private on disk."""
    def __init__(self, database: Path, lock: threading.RLock, data_root: Path,
                 client: TwitchClient | None = None, activity=None):
        self.database = database
        self.lock = lock
        self.data_root = data_root
        self.client_id = os.getenv("TWITCH_CLIENT_ID", "").strip()
        self.secret = os.getenv("TWITCH_CLIENT_SECRET", "").strip()
        self.enabled = os.getenv("TWITCH_ENABLED", "0") == "1"
        self.client = client
        self.activity = activity
        self.on_refreshed = None
        self._polling_started = False
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS twitch_candidates (
                id TEXT PRIMARY KEY, broadcaster_id TEXT NOT NULL,
                creator_name TEXT, title TEXT, url TEXT,
                view_count INTEGER NOT NULL, duration REAL NOT NULL,
                created_at TEXT, score INTEGER NOT NULL,
                consent_flag TEXT NOT NULL, seen_at TEXT NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS twitch_sync (
                id INTEGER PRIMARY KEY CHECK(id = 1), last_at TEXT,
                last_error TEXT, game_id TEXT
            )""")
            # Safe additive migrations preserve existing GTA-only clip history.
            for table, name, declaration in (
                ("twitch_candidates", "game_id", "TEXT NOT NULL DEFAULT ''"),
                ("twitch_candidates", "game_name", "TEXT NOT NULL DEFAULT ''"),
                ("twitch_sync", "profile", "TEXT NOT NULL DEFAULT ''"),
                ("twitch_sync", "categories_json", "TEXT NOT NULL DEFAULT '[]'"),
                ("twitch_candidates", "language", "TEXT NOT NULL DEFAULT ''"),
            ):
                columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
                if name not in columns:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
            db.execute("""CREATE TABLE IF NOT EXISTS twitch_streamers (
                broadcaster_id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '',
                is_live INTEGER NOT NULL DEFAULT 0, stream_id TEXT,
                game_id TEXT, title TEXT, viewer_count INTEGER NOT NULL DEFAULT 0,
                started_at TEXT, checked_at TEXT NOT NULL
            )""")
            db.commit()

    def _db(self):
        conn = sqlite3.connect(self.database, timeout=20)
        conn.row_factory = sqlite3.Row
        return closing(conn)

    def sources(self) -> dict:
        path = self.data_root / "twitch_sources.json"
        if not path.exists():
            return {}
        if path.is_symlink() or path.stat().st_size > 64_000:
            raise TwitchError("Invalid Twitch sources configuration")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or not isinstance(raw.get("broadcasters", []), list):
                raise ValueError("Expected broadcasters list")
            entries = raw.get("broadcasters", [])
            result = {}
            for entry in entries[:100]:
                if not isinstance(entry, dict):
                    raise ValueError("Invalid broadcaster")
                broadcaster_id = str(entry.get("id", "")).strip()
                rights = entry.get("rights_status")
                evidence = str(entry.get("evidence", "")).strip()
                if broadcaster_id.isdigit() and rights in {"owned", "permission_granted"}:
                    if rights == "owned" or len(evidence) >= 8:
                        result[broadcaster_id] = "declared_permission"
            return result
        except (ValueError, TypeError, KeyError) as exc:
            raise TwitchError("Invalid Twitch sources JSON") from exc

    def profile(self, now: datetime | None = None) -> dict:
        """Até 12 categorias antes do lançamento; foco GTA VI ou override manual."""
        now = now or datetime.now(timezone.utc)
        # Guard against malformed overrides without silently dropping the GTA VI switch.
        launch_raw = os.getenv("TWITCH_GTA6_LAUNCH_AT", DEFAULT_GTA6_LAUNCH).strip()
        try:
            launch = datetime.fromisoformat(launch_raw.replace("Z", "+00:00"))
            if launch.tzinfo is None:
                raise ValueError("Timezone required")
            launch = launch.astimezone(timezone.utc)
        except ValueError:
            launch = datetime.fromisoformat(DEFAULT_GTA6_LAUNCH)

        def bounded(name: str, default: int, max_value: int) -> int:
            try:
                return max(1, min(max_value, int(os.getenv(name, str(default)))))
            except ValueError:
                return default

        mode = os.getenv("TWITCH_DISCOVERY_MODE", "auto").strip()
        if mode not in {"auto", "trending", "gta5_only", "gta6_only"}:
            raise TwitchError("TWITCH_DISCOVERY_MODE inválido")
        active = ("gta6_only" if now >= launch else "trending") if mode == "auto" else mode
        return {
            "profile": active,
            "manual_override": mode != "auto",
            "focus_game": {"gta6_only": "Grand Theft Auto VI", "gta5_only": "Grand Theft Auto V"}.get(active, "Categorias populares/configuradas"),
            "launch_at": launch.isoformat(timespec="seconds"),
            "category_limit": bounded("TWITCH_TRENDING_CATEGORIES", DEFAULT_CATEGORY_LIMIT, 12),
            "clips_per_category": bounded("TWITCH_CLIPS_PER_CATEGORY", DEFAULT_CLIPS_PER_CATEGORY, 30),
            "lookback_hours": bounded("TWITCH_LOOKBACK_HOURS", 72, 168),
        }

    def status(self) -> dict:
        profile = self.profile()
        with self._db() as db:
            sync = db.execute(
                "SELECT last_at,last_error,game_id,profile,categories_json "
                "FROM twitch_sync WHERE id=1"
            ).fetchone()
            where, params = self._candidate_filter(profile["profile"])
            count = db.execute("SELECT COUNT(*) FROM twitch_candidates WHERE " + where, params).fetchone()[0]
        streamers = self.list_streamers()
        raw_categories = sync["categories_json"] if sync else "[]"
        try:
            categories = json.loads(raw_categories or "[]")
        except ValueError:
            categories = []
        return {
            "configured": bool(self.client or (self.client_id and self.secret)),
            "auto_monitoring": self.enabled and bool(self.client or (self.client_id and self.secret)),
            "last_sync": sync["last_at"] if sync else None,
            "last_error": sync["last_error"] if sync else None,
            "game_id": sync["game_id"] if sync and sync["profile"] == profile["profile"] else None,
            "count": count,
            "monitored_streamers": len(streamers),
            "live_streams": sum(row["is_live"] for row in streamers),
            "mode": "metadata_only",
            **profile,
            "last_profile": sync["profile"] if sync else None,
            "categories": categories if sync and sync["profile"] == profile["profile"] else [],
        }

    def _candidate_filter(self, mode: str) -> tuple[str, tuple]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds")
        if mode == "trending":
            ids = configured_ids("TWITCH_CATEGORY_IDS", 12)
            if ids:
                return "seen_at>=? AND game_id IN (" + ",".join("?" for _ in ids) + ")", (cutoff, *ids)
            return "seen_at>=? AND game_id<>''", (cutoff,)
        names = ("grand theft auto vi", "grand theft auto 6") if mode == "gta6_only" else ("grand theft auto v", "grand theft auto 5")
        return "seen_at>=? AND lower(game_name) IN (?,?)", (cutoff, *names)

    def list_candidates(self) -> list[dict]:
        where, params = self._candidate_filter(self.profile()["profile"])
        with self._db() as db:
            rows = db.execute("SELECT * FROM twitch_candidates WHERE " + where +
                              " ORDER BY score DESC, view_count DESC LIMIT 100", params).fetchall()
        return [dict(r) for r in rows]

    def list_streamers(self) -> list[dict]:
        ids = configured_ids("TWITCH_BROADCASTER_IDS", 100)
        if not ids:
            return []
        with self._db() as db:
            rows = db.execute("SELECT * FROM twitch_streamers WHERE broadcaster_id IN (" +
                              ",".join("?" for _ in ids) + ") ORDER BY is_live DESC,name", ids).fetchall()
        return [dict(r) for r in rows]

    def refresh(self) -> dict:
        if not self.client and not (self.client_id and self.secret):
            raise TwitchError("Configure TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET first")
        client = self.client or TwitchClient(self.client_id, self.secret)
        self.client = client
        profile = self.profile()
        mode = profile["profile"]
        if self.activity:
            self.activity.append(None, "radar", "running",
                                 "Consultando metadados oficiais da Twitch")
        try:
            if mode == "trending":
                ids = configured_ids("TWITCH_CATEGORY_IDS", 12)
                categories = client.get_categories(ids) if ids else client.get_top_categories(profile["category_limit"])
                categories = categories[:profile["category_limit"]]
                game_id = ""
            else:
                game_id = (os.getenv("TWITCH_GAME_ID", "").strip() or client.find_gta6_game()) if mode == "gta6_only" else (os.getenv("TWITCH_GTA5_GAME_ID", "").strip() or client.find_gta5_game())
                categories = [{"id": game_id, "name": "Grand Theft Auto VI" if mode == "gta6_only" else "Grand Theft Auto V"}]
            if any(not str(c.get("id", "")).isdigit() for c in categories):
                raise TwitchError("Invalid Twitch game ID")
            records_by_category = [(category, client.get_clips(category["id"],
                lookback_hours=profile["lookback_hours"], first=profile["clips_per_category"])) for category in categories]
            broadcaster_ids = configured_ids("TWITCH_BROADCASTER_IDS", 100)
            streams = {str(row.get("user_id")): row for row in client.get_streams(broadcaster_ids)} if broadcaster_ids else {}
            allowlist = self.sources()
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            inserted = 0
            received = sum(len(records) for _, records in records_by_category)
            with self.lock, self._db() as db:
                for broadcaster_id in broadcaster_ids:
                    stream = streams.get(broadcaster_id, {})
                    db.execute("""INSERT INTO twitch_streamers
                        (broadcaster_id,name,is_live,stream_id,game_id,title,viewer_count,started_at,checked_at)
                        VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(broadcaster_id) DO UPDATE SET
                        name=CASE WHEN excluded.name='' THEN twitch_streamers.name ELSE excluded.name END,
                        is_live=excluded.is_live,stream_id=excluded.stream_id,game_id=excluded.game_id,
                        title=excluded.title,viewer_count=excluded.viewer_count,
                        started_at=excluded.started_at,checked_at=excluded.checked_at""",
                        (broadcaster_id,str(stream.get("user_name", ""))[:180],int(bool(stream)),
                         str(stream.get("id", ""))[:100],str(stream.get("game_id", ""))[:100],
                         str(stream.get("title", ""))[:300],max(0,int(stream.get("viewer_count",0))),
                         str(stream.get("started_at", ""))[:80],now))
                for category, records in records_by_category:
                    for item in records:
                        clip_id = str(item.get("id", "")).strip()[:180]
                        url = str(item.get("url", ""))[:1024]
                        if not clip_id or not twitch_clip_url(url):
                            continue
                        broadcaster_id = str(item.get("broadcaster_id", ""))[:100]
                        flag = allowlist.get(broadcaster_id, "unverified")
                        row = (
                            clip_id, broadcaster_id,
                            str(item.get("broadcaster_name", ""))[:180],
                            str(item.get("title", ""))[:300], url,
                            max(0, int(item.get("view_count", 0) or 0)),
                            max(0.0, float(item.get("duration", 0) or 0)),
                            str(item.get("created_at", ""))[:80], clip_score(item),
                            flag, now, category["id"], category["name"],
                            str(item.get("language", "") or "")[:16],
                        )
                        db.execute("""INSERT INTO twitch_candidates
                            (id,broadcaster_id,creator_name,title,url,view_count,
                             duration,created_at,score,consent_flag,seen_at,
                             game_id,game_name,language)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                            ON CONFLICT(id) DO UPDATE SET
                            view_count=excluded.view_count,
                            score=excluded.score, title=excluded.title,
                            consent_flag=excluded.consent_flag,
                            seen_at=excluded.seen_at,
                            game_id=excluded.game_id,
                            game_name=excluded.game_name,
                            language=excluded.language
                        """, row)
                        inserted += 1
                db.execute("""INSERT INTO twitch_sync
                    (id,last_at,last_error,game_id,profile,categories_json)
                    VALUES (1,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET
                    last_at=excluded.last_at,last_error=NULL,
                    game_id=excluded.game_id,profile=excluded.profile,
                    categories_json=excluded.categories_json""",
                    (now, None, game_id, mode,
                     json.dumps([c["name"] for c in categories], ensure_ascii=False)))
                # Preserve historical rows but display only the active target game.
                db.execute("""DELETE FROM twitch_candidates WHERE id NOT IN
                    (SELECT id FROM twitch_candidates ORDER BY seen_at DESC LIMIT 5000)""")
                db.commit()
            if self.activity:
                self.activity.append(None, "radar", "complete",
                                     f"Consulta Twitch concluída: {inserted} registros de metadados")
            if self.on_refreshed:
                try:
                    self.on_refreshed()
                except (OSError, RuntimeError, ValueError):
                    # Public metadata search remains usable even when editing is
                    # blocked by missing permissions or local AI dependencies.
                    pass
            return {
                "ok": True, "received": received, "processed": inserted,
                "game_id": game_id, "profile": mode,
                "categories": [c["name"] for c in categories],
            }
        except (TwitchError, TypeError, ValueError, KeyError, sqlite3.Error) as exc:
            message = str(exc)[:240]
            with self.lock, self._db() as db:
                db.execute("""INSERT INTO twitch_sync (id,last_error) VALUES (1,?)
                              ON CONFLICT(id) DO UPDATE SET last_error=excluded.last_error""",
                           (message,))
                db.commit()
            if self.activity:
                self.activity.append(None, "radar", "failed",
                                     "Consulta de metadados Twitch falhou")
            raise TwitchError(message) from exc

    def start_polling(self):
        if not self.enabled or not (self.client or (self.client_id and self.secret)):
            return
        # Credentials can be updated from the Windows UI; never spawn
        # duplicate refresh workers on repeated saves.
        with self.lock:
            if self._polling_started:
                return
            self._polling_started = True
        try:
            seconds = max(300, int(os.getenv("TWITCH_POLL_SECONDS", "900")))
        except ValueError:
            seconds = 900
        def loop():
            while True:
                try:
                    self.refresh()
                except TwitchError as exc:
                    print(f"Twitch metadata sync failed: {exc}", flush=True)
                time.sleep(seconds)
        threading.Thread(target=loop, name="twitch-metadata", daemon=True).start()

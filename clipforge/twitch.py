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

ALLOWED_CATEGORY_NAMES = {"grand theft auto vi", "grand theft auto 6"}
TWITCH_BASE = "https://api.twitch.tv/helix"
OAUTH_URL = "https://id.twitch.tv/oauth2/token"


class TwitchError(RuntimeError):
    pass


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
    return max(0, min(100, round(popularity + freshness + usable)))


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
        self._expires_at = time.monotonic() + max(60, int(payload.get("expires_in", 3600)) - 120)
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
            raise TwitchError(f"Twitch API HTTP {exc.code}") from exc
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            raise TwitchError("Twitch API request unavailable or invalid") from exc

    def _get(self, endpoint: str, params: dict) -> dict:
        query = urlencode(params)
        req = Request(f"{TWITCH_BASE}/{endpoint}?{query}", headers={
            "Client-Id": self.client_id,
            "Authorization": f"Bearer {self._token_value()}",
            "Accept": "application/json",
        })
        return self._send(req)

    def find_gta6_game(self) -> str:
        result = self._get("search/categories", {"query": "Grand Theft Auto VI", "first": 30})
        for game in result.get("data", []):
            if str(game.get("name", "")).strip().lower() in ALLOWED_CATEGORY_NAMES:
                return str(game["id"])
        raise TwitchError("GTA VI category not yet available on Twitch; configure TWITCH_GAME_ID")

    def get_clips(self, game_id: str, lookback_hours: int = 72) -> list[dict]:
        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=lookback_hours)
        params = {
            "game_id": game_id, "first": 100,
            "started_at": since.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "ended_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
        # One page is intentional: predictable quotas and bounded dashboard processing.
        return list(self._get("clips", params).get("data", []))[:100]


class TwitchDiscovery:
    """Persist top public clip METADATA. Permission file stays private on disk."""
    def __init__(self, database: Path, lock: threading.RLock, data_root: Path,
                 client: TwitchClient | None = None):
        self.database = database
        self.lock = lock
        self.data_root = data_root
        self.client_id = os.getenv("TWITCH_CLIENT_ID", "").strip()
        self.secret = os.getenv("TWITCH_CLIENT_SECRET", "").strip()
        self.enabled = os.getenv("TWITCH_ENABLED", "0") == "1"
        self.client = client
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
            entries = raw.get("broadcasters", [])
            result = {}
            for entry in entries[:100]:
                broadcaster_id = str(entry.get("id", "")).strip()
                rights = entry.get("rights_status")
                evidence = str(entry.get("evidence", "")).strip()
                if broadcaster_id.isdigit() and rights in {"owned", "permission_granted"}:
                    if rights == "owned" or len(evidence) >= 8:
                        result[broadcaster_id] = "declared_permission"
            return result
        except (ValueError, TypeError, KeyError) as exc:
            raise TwitchError("Invalid Twitch sources JSON") from exc

    def status(self) -> dict:
        with self._db() as db:
            sync = db.execute("SELECT last_at,last_error,game_id FROM twitch_sync WHERE id=1").fetchone()
            count = db.execute("SELECT COUNT(*) FROM twitch_candidates").fetchone()[0]
        return {
            "configured": bool(self.client or (self.client_id and self.secret)),
            "auto_monitoring": self.enabled,
            "last_sync": sync["last_at"] if sync else None,
            "last_error": sync["last_error"] if sync else None,
            "game_id": sync["game_id"] if sync else None,
            "count": count,
            "mode": "metadata_only",
        }

    def list_candidates(self) -> list[dict]:
        with self._db() as db:
            rows = db.execute(
                "SELECT * FROM twitch_candidates ORDER BY score DESC, view_count DESC LIMIT 100"
            ).fetchall()
        return [dict(r) for r in rows]

    def refresh(self) -> dict:
        if not self.client and not (self.client_id and self.secret):
            raise TwitchError("Configure TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET first")
        client = self.client or TwitchClient(self.client_id, self.secret)
        self.client = client
        try:
            game_id = os.getenv("TWITCH_GAME_ID", "").strip() or client.find_gta6_game()
            if not game_id.isdigit():
                raise TwitchError("Invalid Twitch game ID")
            records = client.get_clips(game_id)
            allowlist = self.sources()
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            inserted = 0
            with self.lock, self._db() as db:
                for item in records:
                    clip_id = str(item.get("id", "")).strip()[:180]
                    url = str(item.get("url", ""))[:1024]
                    if not clip_id or not twitch_clip_url(url):
                        continue
                    broadcaster_id = str(item.get("broadcaster_id", ""))[:100]
                    flag = allowlist.get(broadcaster_id, "unverified")
                    row = (
                        clip_id, broadcaster_id, str(item.get("broadcaster_name", ""))[:180],
                        str(item.get("title", ""))[:300], url,
                        max(0, int(item.get("view_count", 0) or 0)),
                        max(0.0, float(item.get("duration", 0) or 0)),
                        str(item.get("created_at", ""))[:80], clip_score(item),
                        flag, now,
                    )
                    db.execute("""INSERT INTO twitch_candidates
                        (id,broadcaster_id,creator_name,title,url,view_count,
                        duration,created_at,score,consent_flag,seen_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(id) DO UPDATE SET
                        view_count=excluded.view_count,
                        score=excluded.score,
                        title=excluded.title,
                        consent_flag=excluded.consent_flag,
                        seen_at=excluded.seen_at
                    """, row)
                    inserted += 1
                db.execute("""INSERT INTO twitch_sync (id,last_at,last_error,game_id)
                              VALUES (1,?,?,?)
                              ON CONFLICT(id) DO UPDATE SET
                              last_at=excluded.last_at,last_error=NULL,
                              game_id=excluded.game_id""", (now, None, game_id))
                db.commit()
            return {"ok": True, "received": len(records), "processed": inserted, "game_id": game_id}
        except (TwitchError, TypeError, ValueError, sqlite3.Error) as exc:
            message = str(exc)[:240]
            with self.lock, self._db() as db:
                db.execute("""INSERT INTO twitch_sync (id,last_error) VALUES (1,?)
                              ON CONFLICT(id) DO UPDATE SET last_error=excluded.last_error""",
                           (message,))
                db.commit()
            raise TwitchError(message) from exc

    def start_polling(self):
        if not self.enabled or not (self.client or (self.client_id and self.secret)):
            return
        seconds = max(300, int(os.getenv("TWITCH_POLL_SECONDS", "900")))
        def loop():
            while True:
                try:
                    self.refresh()
                except TwitchError as exc:
                    print(f"Twitch metadata sync failed: {exc}", flush=True)
                time.sleep(seconds)
        threading.Thread(target=loop, name="twitch-metadata", daemon=True).start()

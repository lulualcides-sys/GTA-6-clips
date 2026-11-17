"""Platform-sourced publication metrics; never infer views or retention.

YouTube Data API videos.list statistics and TikTok Display API video/query
are read-only calls. OAuth scopes/availability and private status are reported.
No engagement metric is attributed to an unverified remote video ID.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class PerformanceMetrics:
    def __init__(self, store):
        self.store = store
        with store.lock, store._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS social_metrics (
                job_id TEXT PRIMARY KEY, platform TEXT NOT NULL,
                remote_id TEXT NOT NULL, source TEXT NOT NULL,
                metrics TEXT, fetched_at REAL, error TEXT
            )""")
            db.commit()

    @staticmethod
    def _get_json(url, token, body=None, timeout=14):
        if not token:
            raise ValueError("OAuth da plataforma não conectado")
        raw = json.dumps(body).encode("utf-8") if body is not None else None
        req = Request(url, data=raw,
                      headers={"Authorization": "Bearer " + token,
                               "Content-Type": "application/json"},
                      method="POST" if body is not None else "GET")
        try:
            with urlopen(req, timeout=timeout) as response:
                if response.status != 200:
                    raise ValueError("A plataforma não confirmou a consulta")
                data = json.loads(response.read(400_000))
                if not isinstance(data, dict):
                    raise ValueError("Resposta inválida da plataforma")
                return data
        except HTTPError as exc:
            # Do not echo response body: may include private client details.
            raise ValueError("Plataforma recusou consulta HTTP " + str(exc.code)) from None
        except URLError:
            raise ValueError("Plataforma indisponível ou sem conexão") from None

    @staticmethod
    def _numbers(record):
        clean = {}
        for original, name in (("viewCount", "views"), ("likeCount", "likes"),
                               ("commentCount", "comments"), ("shareCount", "shares"),
                               ("view_count", "views"), ("like_count", "likes"),
                               ("comment_count", "comments"), ("share_count", "shares")):
            if original in record:
                try:
                    number = int(record[original])
                    if number >= 0:
                        clean[name] = number
                except (ValueError, TypeError):
                    pass
        return clean

    def _youtube_retention(self, remote):
        """Optional OAuth-only YouTube Analytics v2; no inferred retention."""
        token = os.getenv("YOUTUBE_ANALYTICS_ACCESS_TOKEN", "").strip()
        if not token:
            return None
        end = datetime.now(timezone.utc).date() - timedelta(days=2)
        start = end - timedelta(days=28)
        query = urlencode({
            "ids": "channel==MINE", "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "metrics": "averageViewDuration,averageViewPercentage",
            "filters": "video==" + remote,
        })
        try:
            report = self._get_json("https://youtubeanalytics.googleapis.com/v2/reports?"
                                    + query, token)
            rows = report.get("rows") or []
            columns = [x.get("name") for x in report.get("columnHeaders", [])
                       if isinstance(x, dict)]
            if not rows or len(columns) != len(rows[0]):
                return None
            data = dict(zip(columns, rows[0]))
            duration = float(data["averageViewDuration"])
            pct = float(data["averageViewPercentage"])
            if not (math.isfinite(duration) and math.isfinite(pct) and
                    0 <= duration < 1_000_000 and 0 <= pct < 100_000):
                return None
            return {"average_view_duration_sec": round(duration, 2),
                    "average_view_percentage": round(pct, 2)}
        except (ValueError, OSError, TypeError, KeyError):
            return None  # Data API counters remain authentic even if Analytics lacks scope.

    def _fetch(self, job):
        remote = str(job.get("remote_id") or "").strip()
        platform = job["platform"]
        if platform == "youtube":
            if not re.fullmatch(r"[A-Za-z0-9_-]{11}", remote):
                raise ValueError("ID de vídeo YouTube não confirmado")
            token = os.getenv("YOUTUBE_ACCESS_TOKEN", "")
            url = ("https://www.googleapis.com/youtube/v3/videos?"
                   + urlencode({"part": "statistics", "id": remote}))
            payload = self._get_json(url, token)
            entries = payload.get("items", [])
            if len(entries) != 1 or entries[0].get("id") != remote:
                raise ValueError("Vídeo não retornado pela conta YouTube")
            metrics = self._numbers(entries[0].get("statistics", {}))
            retention = self._youtube_retention(remote)
            if retention:
                metrics.update(retention)
                return metrics, "youtube_data_v3+youtube_analytics_v2"
            return metrics, "youtube_data_v3"
        if platform == "tiktok":
            if not re.fullmatch(r"[0-9]{8,30}", remote):
                raise ValueError("ID real do vídeo TikTok indisponível")
            token = os.getenv("TIKTOK_ACCESS_TOKEN", "")
            url = ("https://open.tiktokapis.com/v2/video/query/?fields="
                   "id,view_count,like_count,comment_count,share_count")
            data = self._get_json(url, token, {"filters": {"video_ids": [remote]}})
            error = data.get("error") or {}
            if error.get("code") not in {None, "ok", 0}:
                raise ValueError("TikTok exige escopo video.list/autorização")
            entries = (data.get("data") or {}).get("videos", [])
            if len(entries) != 1 or str(entries[0].get("id")) != remote:
                raise ValueError("ID de vídeo não encontrado para esta conta TikTok")
            return self._numbers(entries[0]), "tiktok_video_query"
        raise ValueError("Esta plataforma não fornece métricas por API neste conector")

    def refresh(self, limit=10):
        limit = max(1, min(20, int(limit)))
        with self.store._db() as db:
            # A post being approved is NOT a published video. Metrics require
            # a confirmed publication job with the real platform video ID.
            try:
                rows = db.execute("""SELECT id,platform,remote_id,visibility
                    FROM publication_jobs WHERE status='confirmed'
                    AND remote_id IS NOT NULL AND platform IN ('youtube','tiktok')
                    ORDER BY updated_at DESC LIMIT ?""", (limit,)).fetchall()
            except Exception as exc:
                if "no such table" in str(exc).casefold():
                    return {"attempted": 0, "updated": 0, "errors": 0,
                            "message": "Nenhuma publicação vinculada."}
                raise
        updated = errors = 0
        for job in rows:
            try:
                metrics, source = self._fetch(dict(job))
                if not metrics:
                    raise ValueError("Plataforma não forneceu contadores")
                error = None
                updated += 1
            except (ValueError, OSError, TypeError) as exc:
                metrics, source = None, "official_api"
                error = str(exc)[:180]
                errors += 1
            with self.store.lock, self.store._db() as db:
                # Preserve last successful metrics if transient OAuth/network
                # error occurs. Always update error and attempted time.
                if metrics is None:
                    db.execute("""INSERT INTO social_metrics
                        (job_id,platform,remote_id,source,metrics,fetched_at,error)
                        VALUES(?,?,?,?,NULL,?,?)
                        ON CONFLICT(job_id) DO UPDATE SET error=excluded.error,
                        fetched_at=excluded.fetched_at""",
                        (job["id"], job["platform"], job["remote_id"],
                         source, time.time(), error))
                else:
                    db.execute("""INSERT INTO social_metrics
                        (job_id,platform,remote_id,source,metrics,fetched_at,error)
                        VALUES(?,?,?,?,?,?,NULL) ON CONFLICT(job_id) DO UPDATE SET
                        metrics=excluded.metrics,source=excluded.source,
                        fetched_at=excluded.fetched_at,error=NULL""",
                        (job["id"], job["platform"], job["remote_id"],
                         source, json.dumps(metrics), time.time()))
                db.commit()
        return {"attempted": len(rows), "updated": updated, "errors": errors,
                "message": "Dados de APIs oficiais; retenção opcional somente quando Analytics OAuth permitir."}

    def summary(self):
        with self.store._db() as db:
            try:
                rows = db.execute("""SELECT m.job_id,m.platform,m.remote_id,
                    m.source,m.metrics,m.fetched_at,m.error,j.clip_id,j.visibility
                    FROM social_metrics m LEFT JOIN publication_jobs j ON m.job_id=j.id
                    ORDER BY m.fetched_at DESC LIMIT 100""").fetchall()
                jobs = db.execute("SELECT count(*) FROM publication_jobs WHERE status='confirmed'").fetchone()[0]
            except Exception as exc:
                if "no such table" in str(exc).casefold():
                    rows, jobs = [], 0
                else:
                    raise
        items, totals = [], {"views": 0, "likes": 0, "comments": 0, "shares": 0}
        coverage = {k: 0 for k in totals}
        measured = 0
        retained = 0
        for row in rows:
            stats = json.loads(row["metrics"]) if row["metrics"] else None
            if stats:
                measured += 1
                for key in totals:
                    if key in stats:
                        totals[key] += stats[key]
                        coverage[key] += 1
                if "average_view_percentage" in stats:
                    retained += 1
            items.append({"job_id": row["job_id"], "clip_id": row["clip_id"],
                          "remote_id": row["remote_id"],
                          "platform": row["platform"], "visibility": row["visibility"],
                          "source": row["source"], "metrics": stats, "error": row["error"],
                          "fetched_at": row["fetched_at"]})
        return {
            "confirmed_publications": jobs, "measured_publications": measured,
            "totals": {k: (value if coverage[k] == measured else None)
                       for k, value in totals.items()} if measured else None,
            "metric_coverage": coverage, "items": items,
            "retention": {"measured_videos": retained} if retained else None,
            "retention_status": ("YouTube Analytics v2 consultado" if retained
                                else "Sem OAuth Analytics ou dados de retenção disponíveis"),
            "disclaimer": "Somente dados retornados por APIs oficiais para IDs confirmados; campos não disponíveis ficam nulos."
        }

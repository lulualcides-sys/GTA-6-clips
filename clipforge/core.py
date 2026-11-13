"""Rights-gated ingestion, audio-assisted highlight selection and FFmpeg rendering."""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import subprocess
import threading
import time
import uuid
from array import array
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

SUPPORTED = {".mp4", ".mov", ".mkv", ".webm"}
RIGHTS = {"owned", "permission_granted"}
STATUSES = {"detected", "queued", "rendering", "ready", "approved", "rejected", "failed"}


def probe(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height", "-of", "json", str(path)],
        check=True, capture_output=True, text=True, timeout=45,
    )
    return json.loads(result.stdout)


def duration_of(info: dict) -> float:
    return float(info.get("format", {}).get("duration", 0) or 0)


def choose_highlight(path: Path, total: float, length: float = 35.0) -> float:
    """Heuristic: find a lively AUDIO window. This is NOT semantic AI highlight detection."""
    if total <= length + 1:
        return 0.0
    analysis_seconds = min(total, 900.0)
    try:
        audio = subprocess.run(
            ["ffmpeg", "-v", "error", "-nostdin", "-i", str(path),
             "-t", str(analysis_seconds), "-vn", "-ac", "1", "-ar", "8000",
             "-f", "s16le", "pipe:1"],
            capture_output=True, check=True, timeout=180,
        ).stdout
        samples = array("h")
        samples.frombytes(audio[: len(audio) - len(audio) % 2])
        samples_per_sec = 8000
        powers = []
        for offset in range(0, len(samples), samples_per_sec):
            chunk = samples[offset:offset + samples_per_sec]
            if len(chunk) < samples_per_sec // 2:
                continue
            powers.append(math.sqrt(sum(v * v for v in chunk) / len(chunk)))
        window = max(1, min(int(length), len(powers)))
        if len(powers) < window:
            return 0.0
        baseline = sum(powers) / len(powers)
        best_score, best_start = -1.0, 0
        # Favor sustained activity AND a burst, not the loudest single second.
        for start in range(len(powers) - window + 1):
            section = powers[start:start + window]
            score = sum(section) / window + 0.5 * max(section) - 0.2 * baseline
            if score > best_score:
                best_score, best_start = score, start
        return float(min(best_start, max(0, total - length)))
    except (OSError, subprocess.SubprocessError, ValueError):
        return 0.0


class ClipStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.incoming = self.root / "incoming"
        self.output = self.root / "rendered"
        for folder in (self.root, self.incoming, self.output):
            folder.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "clips.sqlite3"
        self.lock = threading.RLock()
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS clips (
                id TEXT PRIMARY KEY, sha256 TEXT NOT NULL UNIQUE,
                filename TEXT NOT NULL, creator TEXT NOT NULL,
                source_url TEXT, evidence TEXT, rights_status TEXT NOT NULL,
                input_path TEXT NOT NULL, output_path TEXT,
                start_sec REAL, duration_sec REAL NOT NULL, score REAL,
                status TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL
            )""")
            db.commit()

    def _db(self):
        conn = sqlite3.connect(self.database, timeout=20)
        conn.row_factory = sqlite3.Row
        return closing(conn)

    def all(self) -> list[dict]:
        with self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM clips ORDER BY created_at DESC")]

    def get(self, clip_id: str) -> dict | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM clips WHERE id=?", (clip_id,)).fetchone()
        return dict(row) if row else None

    def update(self, clip_id: str, **fields) -> None:
        allowed = {"status", "error", "output_path", "start_sec", "score"}
        if not fields or any(name not in allowed for name in fields):
            raise ValueError("Invalid update")
        with self.lock, self._db() as db:
            sql = ", ".join(f"{name}=?" for name in fields)
            db.execute(f"UPDATE clips SET {sql} WHERE id=?", (*fields.values(), clip_id))
            db.commit()

    def ingest(self, sidecar: Path) -> dict | None:
        """Import only explicit rights manifests. Existence of a Twitch clip is not permission."""
        if sidecar.is_symlink() or sidecar.parent.resolve() != self.incoming:
            raise ValueError("Sidecar outside incoming directory")
        if not sidecar.name.endswith(".rights.json"):
            raise ValueError("Expected .rights.json")
        media = self.incoming / sidecar.name.removesuffix(".rights.json")
        if media.suffix.lower() not in SUPPORTED or not media.is_file() or media.is_symlink():
            raise ValueError("Missing or unsupported video")
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        rights = str(meta.get("rights_status", ""))
        creator = str(meta.get("creator", "")).strip()
        evidence = str(meta.get("evidence", "")).strip()
        if rights not in RIGHTS or not creator:
            raise ValueError("Explicit rights_status and creator required")
        if rights == "permission_granted" and len(evidence) < 8:
            raise ValueError("Permission requires traceable evidence")
        info = probe(media)
        total = duration_of(info)
        if not 10 <= total <= float(os.getenv("MAX_SOURCE_SECONDS", "7200")):
            raise ValueError("Source duration outside 10s–MAX_SOURCE_SECONDS")
        start = meta.get("start_sec")
        start = None if start is None else float(start)
        length = float(meta.get("duration_sec", 35))
        if not 10 <= length <= 60:
            raise ValueError("Output duration must be 10–60 seconds")
        if start is not None and (start < 0 or start + length > total + 0.1):
            raise ValueError("Timestamp outside source duration")
        length = min(length, total)
        sha = hashlib.sha256()
        with media.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                sha.update(chunk)
        item = {
            "id": uuid.uuid4().hex[:12], "sha256": sha.hexdigest(),
            "filename": media.name, "creator": creator,
            "source_url": str(meta.get("source_url", ""))[:2048],
            "evidence": evidence[:2048], "rights_status": rights,
            "input_path": str(media.resolve()), "output_path": None,
            "start_sec": start, "duration_sec": length, "score": None,
            "status": "detected", "error": None,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        with self.lock, self._db() as db:
            db.execute(
                "INSERT OR IGNORE INTO clips VALUES (" + ",".join("?" for _ in item) + ")",
                tuple(item.values()),
            )
            inserted = db.execute("SELECT changes()").fetchone()[0]
            db.commit()
        return item if inserted else None

    def scan(self) -> dict:
        added, errors = [], []
        for sidecar in sorted(self.incoming.glob("*.rights.json")):
            try:
                clip = self.ingest(sidecar)
                if clip:
                    added.append(clip["id"])
            except (ValueError, json.JSONDecodeError, OSError, subprocess.SubprocessError) as exc:
                errors.append({"file": sidecar.name, "error": str(exc)[:400]})
        return {"added": added, "errors": errors}


def render_clip(store: ClipStore, clip_id: str) -> None:
    item = store.get(clip_id)
    if not item or item["status"] != "queued":
        return
    store.update(clip_id, status="rendering", error=None)
    target = store.output / f"{clip_id}.mp4"
    try:
        source = Path(item["input_path"])
        if not source.is_file() or source.is_symlink():
            raise ValueError("Source no longer available")
        total = duration_of(probe(source))
        length = min(float(item["duration_sec"]), total)
        start = item["start_sec"]
        if start is None:
            start = choose_highlight(source, total, length)
            store.update(clip_id, start_sec=start, score=None)
        if start + length > total + 0.2:
            raise ValueError("Segment exceeds media duration")
        # Blur background, keep full landscape gameplay centered (no destructive crop).
        filt = (
            "[0:v]split=2[bg][fg];"
            "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,boxblur=24:2[blur];"
            "[fg]scale=1080:1920:force_original_aspect_ratio=decrease[sharp];"
            "[blur][sharp]overlay=(W-w)/2:(H-h)/2:shortest=1,"
            "fps=30,format=yuv420p[out]"
        )
        cmd = [
            "ffmpeg", "-y", "-nostdin", "-v", "error",
            "-ss", str(start), "-i", str(source), "-t", str(length),
            "-filter_complex", filt,
            "-map", "[out]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "25",
            "-threads", "2", "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", str(target)
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=900)
        info = probe(target)
        video = next((s for s in info.get("streams", []) if s["codec_type"] == "video"), None)
        if not video or (video.get("width"), video.get("height")) != (1080, 1920):
            raise ValueError("QA failed: invalid portrait dimensions")
        if duration_of(info) < 9:
            raise ValueError("QA failed: output too short")
        store.update(clip_id, status="ready", output_path=str(target.resolve()))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        target.unlink(missing_ok=True)
        store.update(clip_id, status="failed", error=str(exc)[-600:])


class Runtime:
    """One rendering worker; database persists results, not an external cloud queue."""
    def __init__(self, root: Path):
        self.store = ClipStore(root)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clip-render")
        self.auto_render = os.getenv("AUTO_RENDER", "1") == "1"
        self.auto_scan = os.getenv("AUTO_SCAN", "1") == "1"
        self.poll_seconds = max(10, int(os.getenv("POLL_SECONDS", "30")))
        with self.store._db() as db:
            db.execute("UPDATE clips SET status='failed', error='Interrupted by restart' "
                       "WHERE status IN ('queued','rendering')")
            db.commit()

    def queue(self, clip_id: str) -> bool:
        with self.store.lock:
            item = self.store.get(clip_id)
            if not item or item["status"] not in {"detected", "failed", "rejected"}:
                return False
            self.store.update(clip_id, status="queued", error=None)
            self.executor.submit(render_clip, self.store, clip_id)
            return True

    def scan(self) -> dict:
        result = self.store.scan()
        if self.auto_render:
            for clip_id in result["added"]:
                self.queue(clip_id)
        return result

    def start_polling(self) -> None:
        if not self.auto_scan:
            return
        def loop():
            while True:
                try:
                    self.scan()
                except Exception as exc:
                    print(f"Background scan failed: {exc}", flush=True)
                time.sleep(self.poll_seconds)
        threading.Thread(target=loop, name="clip-scanner", daemon=True).start()

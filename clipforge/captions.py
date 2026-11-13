"""Opt-in local faster-whisper transcription, rights-gated and revision-safe.

No AI model is downloaded unless a person triggers transcription or enables
AUTO_TRANSCRIBE=1 and installs the optional ai dependencies.
Raw SRT and media remain under private data/, never committed to Git.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

MAX_BYTES = 320 * 1024 * 1024
MODELS = {"tiny", "base", "small", "medium", "large-v3"}
STATUS = {"queued", "processing", "ready", "failed"}


def timestamp(sec: float) -> str:
    milli = max(0, round(float(sec) * 1000))
    hours, rem = divmod(milli, 3600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def cues_from_segments(segments, max_words: int = 8, max_span: float = 3.0):
    """Use real speech timing only; favor short captions when words are available."""
    output = []
    for seg in segments:
        words = getattr(seg, "words", None) or []
        clean = [
            (float(w.start), float(w.end), str(w.word).strip())
            for w in words
            if getattr(w, "start", None) is not None
            and getattr(w, "end", None) is not None
            and str(getattr(w, "word", "")).strip()
        ]
        if clean:
            group = []
            for word in clean:
                if group and (len(group) >= max_words or
                              word[1] - group[0][0] >= max_span):
                    output.append((group[0][0], group[-1][1],
                                   " ".join(v[2] for v in group)))
                    group = []
                group.append(word)
            if group:
                output.append((group[0][0], group[-1][1],
                               " ".join(v[2] for v in group)))
        else:
            text = str(getattr(seg, "text", "")).strip()
            if text:
                output.append((float(seg.start), float(seg.end), text))
    return [(max(0.0, a), b, t[:220]) for a, b, t in output
            if b > a + 0.06 and t.strip()][:150]


def to_srt(cues: list[tuple[float, float, str]]) -> str:
    result = []
    for index, (start, end, text) in enumerate(cues, 1):
        clean = " ".join(str(text).replace("\x00", " ").split())[:220]
        if end <= start or not clean:
            continue
        result.append(f"{index}\n{timestamp(start)} --> {timestamp(end)}\n{clean}\n")
    return "\n".join(result)


@lru_cache(maxsize=2)
def whisper_model(name: str):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed. Install requirements-ai.txt on a separate worker."
        ) from exc
    return WhisperModel(name, device="cpu", compute_type="int8")


def fingerprint(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


class CaptionService:
    def __init__(self, store):
        self.store = store
        self.folder = store.root / "captions"
        if self.folder.is_symlink():
            raise ValueError("Unsafe captions folder")
        self.folder.mkdir(parents=True, exist_ok=True)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisper")
        self._queued = set()
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS clip_captions (
                clip_id TEXT PRIMARY KEY, video_sha TEXT NOT NULL,
                status TEXT NOT NULL, language TEXT, model TEXT,
                cues INTEGER NOT NULL DEFAULT 0, error TEXT,
                updated_at TEXT NOT NULL
            )""")
            db.execute("""UPDATE clip_captions SET status='failed',
                error='Interrupted by restart'
                WHERE status IN ('queued','processing')""")
            db.commit()

    def _db(self):
        db = sqlite3.connect(self.store.database, timeout=20)
        db.row_factory = sqlite3.Row
        return closing(db)

    def _video(self, clip_id: str) -> tuple[dict, Path]:
        item = self.store.get(clip_id)
        if not item or item["status"] not in {"ready", "approved"}:
            raise ValueError("Clip is not ready or approved")
        path = self.store.output / f"{clip_id}.mp4"
        if (not path.is_file() or path.is_symlink() or
                path.stat().st_size > MAX_BYTES or
                not item.get("output_path") or
                Path(item["output_path"]).resolve() != path.resolve()):
            raise ValueError("Missing, invalid or oversized rendered clip")
        return item, path

    def status(self, clip_id: str) -> dict:
        with self._db() as db:
            row = db.execute(
                "SELECT clip_id,video_sha,status,language,model,cues,error,updated_at "
                "FROM clip_captions WHERE clip_id=?", (clip_id,)
            ).fetchone()
        if row is None:
            return {"status": "not_started", "cues": 0, "language": None,
                    "model": None, "error": None}
        result = dict(row)
        result.pop("video_sha", None)
        if result["status"] == "ready":
            try:
                _, path = self._video(clip_id)
                if fingerprint(path) != row["video_sha"]:
                    result["status"] = "stale"
                    result["error"] = "Video changed; regenerate subtitles"
            except ValueError:
                result["status"] = "stale"
        return result

    @staticmethod
    def available() -> bool:
        """Whether the optional Python package is installed, not model weights readiness."""
        return importlib.util.find_spec("faster_whisper") is not None

    def all_statuses(self) -> dict:
        with self._db() as db:
            rows = db.execute(
                "SELECT clip_id,status,language,model,cues,error,updated_at FROM clip_captions"
            ).fetchall()
        return {r["clip_id"]: dict(r) for r in rows}

    def _set(self, clip_id: str, sha: str, status: str, *,
             language: str | None = None, model: str | None = None,
             cues: int = 0, error: str | None = None) -> None:
        if status not in STATUS:
            raise ValueError("Invalid caption status")
        with self.store.lock, self._db() as db:
            db.execute("""INSERT INTO clip_captions
                (clip_id,video_sha,status,language,model,cues,error,updated_at)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(clip_id) DO UPDATE SET
                    video_sha=excluded.video_sha,status=excluded.status,
                    language=excluded.language,model=excluded.model,
                    cues=excluded.cues,error=excluded.error,
                    updated_at=excluded.updated_at""",
                (clip_id, sha, status, language, model, cues, error,
                 time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
            db.commit()

    def queue(self, clip_id: str) -> bool:
        item, path = self._video(clip_id)
        model = os.getenv("WHISPER_MODEL", "base").strip().lower()
        if model not in MODELS:
            raise ValueError("Unsupported WHISPER_MODEL; choose tiny/base/small/medium/large-v3")
        sha = fingerprint(path)
        with self.store.lock:
            if clip_id in self._queued:
                return False
            current = self.status(clip_id)
            if current["status"] in {"queued", "processing"}:
                return False
            if current["status"] == "ready" and (
                current.get("model") == model and
                (self.folder / f"{clip_id}.srt").is_file()
            ):
                return False
            self._queued.add(clip_id)
            self._set(clip_id, sha, "queued", model=model)
            try:
                self.executor.submit(self._run, clip_id, sha, model)
            except RuntimeError:
                self._queued.discard(clip_id)
                self._set(clip_id, sha, "failed", model=model, error="Worker unavailable")
                return False
        return True

    def _run(self, clip_id: str, sha: str, model_name: str):
        try:
            _, path = self._video(clip_id)
            if fingerprint(path) != sha:
                raise ValueError("Clip changed before transcription")
            self._set(clip_id, sha, "processing", model=model_name)
            language = os.getenv("WHISPER_LANGUAGE", "").strip().lower()
            if language and language not in {"pt", "en", "es"}:
                raise ValueError("WHISPER_LANGUAGE must be pt, en or es")
            segments, info = whisper_model(model_name).transcribe(
                str(path), language=language or None, beam_size=5,
                vad_filter=True, word_timestamps=True,
                condition_on_previous_text=False,
            )
            cues = cues_from_segments(segments)
            if fingerprint(path) != sha:
                raise ValueError("Clip changed during transcription")
            dest = self.folder / f"{clip_id}.srt"
            if dest.is_symlink():
                raise ValueError("Unsafe captions output")
            temp = self.folder / f"{clip_id}.srt.tmp"
            temp.write_text(to_srt(cues), encoding="utf-8")
            temp.replace(dest)
            detected = str(getattr(info, "language", language or "unknown"))[:10]
            self._set(clip_id, sha, "ready", model=model_name,
                      language=detected, cues=len(cues))
        except Exception as exc:
            # No absolute paths or private source values in public response.
            self._set(clip_id, sha, "failed", model=model_name,
                      error=f"{type(exc).__name__}: {str(exc)[:180]}")
        finally:
            with self.store.lock:
                self._queued.discard(clip_id)

    def captions_file(self, clip_id: str) -> Path | None:
        item = self.status(clip_id)
        path = self.folder / f"{clip_id}.srt"
        if (item["status"] == "ready" and item["cues"] > 0 and
                path.is_file() and not path.is_symlink()):
            return path
        return None

    def stop(self):
        self.executor.shutdown(wait=False, cancel_futures=True)

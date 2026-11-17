"""Rights-gated ingestion, audio-assisted highlight selection and FFmpeg rendering."""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import subprocess
import threading
import tempfile
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
         "format=duration:stream=codec_type,width,height,avg_frame_rate,codec_name,sample_aspect_ratio", "-of", "json", str(path)],
        check=True, capture_output=True, text=True, timeout=45,
    )
    return json.loads(result.stdout)


def duration_of(info: dict) -> float:
    return float(info.get("format", {}).get("duration", 0) or 0)


def analyze_highlight(path: Path, total: float, length: float = 35.0) -> tuple[float, dict]:
    """Extrai sinais acústicos e conserva pontuações auditáveis, sem semântica."""
    analysis = {"method": "audio-heuristic", "semantic_understanding": False, "candidates": []}
    if total <= length + 1:
        return 0.0, {**analysis, "reason": "source_fits_single_window"}
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
        from .editing import rank_audio_windows
        ranked = rank_audio_windows(powers, length)
        analysis["candidates"] = ranked
        start = float(min(ranked[0]["start_sec"], max(0, total - length))) if ranked else 0.0
        return start, analysis
    except (OSError, subprocess.SubprocessError, ValueError):
        return 0.0, {**analysis, "reason": "audio_unavailable"}


def choose_highlight(path: Path, total: float, length: float = 35.0) -> float:
    """Interface compatível para consumidores que precisam apenas do timestamp."""
    return analyze_highlight(path, total, length)[0]


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
            db.execute("""CREATE TABLE IF NOT EXISTS clip_edits (
                clip_id TEXT PRIMARY KEY, settings TEXT NOT NULL,
                analysis TEXT, qa TEXT
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS render_recovery (
                clip_id TEXT PRIMARY KEY, attempts INTEGER NOT NULL DEFAULT 0
            )""")
            db.commit()
        from .telemetry import ActivityLog
        self.activity = ActivityLog(self.database, self.lock)

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

    def get_edit(self, clip_id: str) -> dict:
        """Ajustes persistidos separados do vídeo original e de sua proveniência."""
        from .editing import DEFAULT_EDIT
        item = self.get(clip_id)
        if not item:
            raise ValueError("Clipe não encontrado")
        with self._db() as db:
            row = db.execute("SELECT * FROM clip_edits WHERE clip_id=?", (clip_id,)).fetchone()
        result = {**DEFAULT_EDIT, "start_sec": item["start_sec"], "duration_sec": item["duration_sec"]}
        if row:
            result.update(json.loads(row["settings"]))
            result["analysis"] = json.loads(row["analysis"]) if row["analysis"] else None
            result["qa"] = json.loads(row["qa"]) if row["qa"] else None
        # A seleção automática atualiza clips; settings pode conter o None original.
        result.update(start_sec=item["start_sec"], duration_sec=item["duration_sec"])
        return result

    def edit(self, clip_id: str, **fields) -> dict:
        """Salva revisão manual; versões prontas ficam em disco, aprovadas são imutáveis."""
        from .editing import DEFAULT_EDIT, validate_edit
        allowed = set(DEFAULT_EDIT) | {"start_sec", "duration_sec"}
        if not fields or any(name not in allowed for name in fields):
            raise ValueError("Ajuste editorial desconhecido")
        with self.lock:
            item = self.get(clip_id)
            if not item or item["status"] not in {"detected", "failed", "rejected", "ready"}:
                raise ValueError("Clipe aprovado ou em estado que não permite edição")
            current = self.get_edit(clip_id)
            settings = {key: value for key, value in current.items() if key in allowed}
            # Alterar título exige nova conferência, não herda a de uma frase anterior.
            if "title" in fields and fields["title"] != settings["title"]:
                settings["title_verified"] = False
            settings.update(fields)
            if settings.get("title") and settings.get("title_verified") is not True:
                raise ValueError("Título exige conferência editorial do acontecimento real")
            settings = validate_edit(settings, item, probe(Path(item["input_path"])))
            with self._db() as db:
                db.execute("INSERT INTO clip_edits (clip_id,settings) VALUES (?,?) "
                           "ON CONFLICT(clip_id) DO UPDATE SET settings=excluded.settings,qa=NULL,analysis=NULL",
                           (clip_id, json.dumps(settings, ensure_ascii=False, allow_nan=False)))
                db.execute("UPDATE clips SET start_sec=?,duration_sec=?,status='detected',error=NULL,output_path=NULL WHERE id=?",
                           (settings["start_sec"], settings["duration_sec"], clip_id))
                db.commit()
            self.activity.append(clip_id, "revisao", "complete", "Ajustes salvos; nova renderização necessária")
            return self.get_edit(clip_id)

    def save_analysis(self, clip_id: str, *, analysis=None, qa=None) -> None:
        """Persiste evidências técnicas sem confundi-las com aprovação editorial."""
        settings = self.get_edit(clip_id)
        settings.pop("analysis", None)
        settings.pop("qa", None)
        with self.lock, self._db() as db:
            db.execute("INSERT OR IGNORE INTO clip_edits (clip_id, settings) VALUES (?,?)",
                       (clip_id, json.dumps(settings, ensure_ascii=False)))
            if analysis is not None:
                db.execute("UPDATE clip_edits SET analysis=? WHERE clip_id=?", (json.dumps(analysis), clip_id))
            if qa is not None:
                db.execute("UPDATE clip_edits SET qa=? WHERE clip_id=?", (json.dumps(qa), clip_id))
            db.commit()

    def update(self, clip_id: str, **fields) -> None:
        allowed = {"status", "error", "output_path", "start_sec", "score"}
        if not fields or any(name not in allowed for name in fields):
            raise ValueError("Invalid update")
        with self.lock, self._db() as db:
            old = db.execute("SELECT status FROM clips WHERE id=?", (clip_id,)).fetchone()
            sql = ", ".join(f"{name}=?" for name in fields)
            db.execute(f"UPDATE clips SET {sql} WHERE id=?", (*fields.values(), clip_id))
            db.commit()
            current = fields.get("status")
            if old and current and current != old["status"]:
                transitions = {
                    "queued": ("edicao", "queued", "Clipe aguardando FFmpeg"),
                    "rendering": ("edicao", "running", "Renderização vertical em execução"),
                    "ready": ("edicao", "complete", "MP4 vertical validado por ffprobe"),
                    "failed": ("edicao", "failed", "Renderização falhou; verifique o erro do clipe"),
                    "approved": ("revisao", "complete", "Aprovação editorial registrada"),
                    "rejected": ("revisao", "failed", "Clipe rejeitado na revisão"),
                }
                if current in transitions:
                    self.activity.append(clip_id, *transitions[current])

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
        if start is not None and (not math.isfinite(start) or start < 0 or start + length > total + 0.1):
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
        from .editing import DEFAULT_EDIT, validate_edit
        settings = {**DEFAULT_EDIT, "start_sec": start, "duration_sec": length}
        settings.update({key: meta[key] for key in DEFAULT_EDIT if key in meta})
        settings = validate_edit(settings, item, info)
        with self.lock, self._db() as db:
            db.execute(
                "INSERT OR IGNORE INTO clips VALUES (" + ",".join("?" for _ in item) + ")",
                tuple(item.values()),
            )
            inserted = db.execute("SELECT changes()").fetchone()[0]
            if inserted:
                db.execute("INSERT INTO clip_edits (clip_id,settings) VALUES (?,?)",
                           (item["id"], json.dumps(settings, ensure_ascii=False)))
            db.commit()
        if inserted:
            self.activity.append(item["id"], "ingestao", "complete",
                                 "Arquivo local importado e deduplicado")
            self.activity.append(item["id"], "direitos", "complete",
                                 "Manifesto de direitos válido; autorização externa requer revisão")
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
    # Retido apenas para smoke/regressão sintéticos, nunca no pipeline Nexus.
    if os.getenv("NEXUS_LEGACY_TEST_RENDER", "0") != "1":
        raise RuntimeError("Renderizador legado bloqueado: somente AutoClip pode editar vídeos.")
    item = store.get(clip_id)
    if not item or item["status"] != "queued":
        return
    store.update(clip_id, status="rendering", error=None)
    target = store.output / f"{clip_id}-{uuid.uuid4().hex[:8]}.mp4"
    try:
        source = Path(item["input_path"])
        if not source.is_file() or source.is_symlink():
            raise ValueError("Source no longer available")
        # Não renderizar bytes substituídos depois da autorização/ingestão.
        digest = hashlib.sha256()
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != item["sha256"]:
            raise ValueError("Source changed after rights verification")
        if item["rights_status"] not in RIGHTS:
            raise ValueError("Source lacks rights authorization")
        source_info = probe(source)
        total = duration_of(source_info)
        from .editing import validate_edit, source_fps, video_filter
        settings = validate_edit(store.get_edit(clip_id), item, source_info)
        length = min(float(item["duration_sec"]), total)
        start = item["start_sec"]
        if start is None:
            store.activity.append(clip_id, "curadoria", "running",
                                  "Analisando atividade de áudio e cenas opcionais")
            start, analysis = analyze_highlight(source, total, length)
            if os.getenv("SMART_SCENES", "0") == "1":
                from .smart import find_cuts, scene_aware_start, MAX_SCAN_SECONDS
                cuts = find_cuts(source, limit_seconds=min(total, MAX_SCAN_SECONDS))
                start = scene_aware_start(start, total, length, cuts)
                analysis.update(method="audio+scene-boundaries" if cuts else "audio-fallback",
                                visual_analysis=bool(cuts), cuts=cuts)
            candidates = analysis.get("candidates", [])
            score = candidates[0]["score"] if candidates else None
            store.update(clip_id, start_sec=start, score=score)
            store.save_analysis(clip_id, analysis={**analysis, "selected_start": start})
            store.activity.append(clip_id, "curadoria", "complete",
                                  "Trecho sugerido por heurística técnica, sem análise semântica")
        else:
            store.activity.append(clip_id, "curadoria", "complete",
                                  "Trecho marcado explicitamente no manifesto")
        if start + length > total + 0.2:
            raise ValueError("Segment exceeds media duration")
        fps = source_fps(source_info)
        has_audio = any(s.get("codec_type") == "audio" for s in source_info.get("streams", []))
        with tempfile.TemporaryDirectory(prefix="clipforge-text-") as text_dir:
            text_path = Path(text_dir)
            title = settings.get("title") or ("" if settings["layout"] == "shorts" else "DESTAQUE DO STREAMER")
            # Limites tipográficos evitam transbordamento e nunca executam expressões.
            lines = []
            for word in title.split():
                if not lines or len(lines[-1]) + len(word) + 1 > 34:
                    lines.append(word)
                else:
                    lines[-1] += " " + word
            (text_path / "title.txt").write_text("\n".join(lines), encoding="utf-8")
            creator = " ".join(str(item["creator"]).split())[:64]
            (text_path / "credit.txt").write_text("Fonte: " + creator, encoding="utf-8")
            cmd = [
                "ffmpeg", "-n", "-nostdin", "-v", "error",
                "-ss", str(start), "-i", str(source), "-t", str(length),
                "-filter_complex_threads", "1", "-filter_complex", video_filter(settings, fps),
                "-map", "[out]", "-map", "0:a:0?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                "-threads", "2", "-c:a", "aac", "-b:a", "192k",
            ]
            if has_audio:
                cmd += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000"]
            cmd += ["-movflags", "+faststart", str(target)]
            subprocess.run(cmd, check=True, capture_output=True, timeout=900, cwd=text_dir)
        info = probe(target)
        video = next((s for s in info.get("streams", []) if s["codec_type"] == "video"), None)
        if not video or (video.get("width"), video.get("height")) != (1080, 1920):
            raise ValueError("QA failed: invalid portrait dimensions")
        if abs(duration_of(info) - length) > 0.35:
            raise ValueError("QA failed: unexpected output duration")
        output_audio = any(s.get("codec_type") == "audio" for s in info.get("streams", []))
        if has_audio and not output_audio:
            raise ValueError("QA failed: source audio was lost")
        # Decodificação integral detecta MP4 truncado ou quadros corrompidos.
        subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(target),
                        "-f", "null", "-"], check=True, capture_output=True, timeout=300)
        store.save_analysis(clip_id, qa={"width": 1080, "height": 1920,
                            "duration_sec": duration_of(info), "fps": fps,
                            "audio_preserved": has_audio and output_audio,
                            "source_has_audio": has_audio, "full_decode": True,
                            "editorial_approval": False})
        store.update(clip_id, status="ready", output_path=str(target.resolve()))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        target.unlink(missing_ok=True)
        store.update(clip_id, status="failed", error=str(exc)[-600:])


class Runtime:
    """One rendering worker; database persists results, not an external cloud queue."""
    def __init__(self, root: Path):
        self.store = ClipStore(root)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clip-render")
        from .twitch import TwitchDiscovery
        self.twitch = TwitchDiscovery(self.store.database, self.store.lock, self.store.root,
                                      activity=self.store.activity)
        from .captions import CaptionService
        self.captions = CaptionService(self.store)
        self.auto_transcribe = os.getenv("AUTO_TRANSCRIBE", "0") == "1"
        self.auto_render = os.getenv("AUTO_RENDER", "1") == "1"
        self.auto_scan = os.getenv("AUTO_SCAN", "1") == "1"
        self.poll_seconds = max(10, int(os.getenv("POLL_SECONDS", "30")))
        from .demo import SyntheticDemo
        self.demo = SyntheticDemo(self)
        from .autoclip_bridge import AutoClipBridge
        self.autoclip_bridge = AutoClipBridge(self.store)
        from .editorial_intelligence import EditorialIntelligence
        from .performance_metrics import PerformanceMetrics
        self.editorial = EditorialIntelligence(self.store)
        self.captions.on_complete = self.editorial.queue
        self.performance = PerformanceMetrics(self.store)
        self.autoclip_bridge.on_import = self.editorial.queue
        from .twitch_auto import TwitchAutoIngest
        self.twitch_auto = TwitchAutoIngest(self)
        self.twitch.on_refreshed = self.twitch_auto.kick
        # Jobs herdados de FFmpeg NÃO podem ser retomados: preservamos fontes
        # e MP4s existentes, e falhamos fechado em vez de renderizar novamente.
        with self.store.lock, self.store._db() as db:
            interrupted = db.execute(
                "SELECT id FROM clips WHERE status IN ('queued','rendering')"
            ).fetchall()
            for row in interrupted:
                db.execute(
                    "UPDATE clips SET status='failed',error=? WHERE id=?",
                    ("Renderizador antigo desativado. Reprocessar somente com AutoClip.", row["id"])
                )
            db.commit()
        for row in interrupted:
            self.store.activity.append(row["id"], "edicao", "failed",
                                       "Render legado não retomado; AutoClip obrigatório")

    def queue(self, clip_id: str) -> bool:
        """Garante AutoClip exclusivo; nunca tenta FFmpeg se indisponível."""
        with self.store.lock:
            item = self.store.get(clip_id)
            if not item or item["status"] not in {"detected", "failed", "rejected"}:
                return False
        self.autoclip_bridge.queue(clip_id)
        self.store.activity.append(clip_id, "edicao", "queued",
                                   "Solicitação enviada exclusivamente ao AutoClip")
        return True

    def _after_render(self, clip_id: str):
        """Optional opt-in transcription after successful video render."""
        item = self.store.get(clip_id)
        if item and item["status"] == "ready":
            try:
                self.captions.queue(clip_id)
            except (ValueError, OSError) as exc:
                print(f"Optional caption enqueue failed: {type(exc).__name__}", flush=True)

    def scan(self) -> dict:
        result = self.store.scan()
        if self.auto_render:
            for clip_id in result["added"]:
                try:
                    self.queue(clip_id)
                except (ValueError, PermissionError, OSError) as exc:
                    # Nunca usar FFmpeg como fallback. A ingestão permanece válida.
                    item = self.store.get(clip_id)
                    result["errors"].append({"file": item["filename"] if item else clip_id,
                                             "error": str(exc)[:200]})
        # The bridge has bounded capacity. If ingest outpaces rendering,
        # resubmit authorized DETECTED sources on later scans instead of
        # leaving them stranded forever when the queue was full.
        if self.auto_render and self.autoclip_bridge.available():
            jobs = self.autoclip_bridge.status()["jobs"]
            with self.store._db() as db:
                backlog = db.execute(
                    "SELECT id FROM clips WHERE status='detected' "
                    "ORDER BY created_at ASC LIMIT 50"
                ).fetchall()
            for row in backlog:
                cid = row["id"]
                if jobs.get(cid, {}).get("status") in {"queued", "running", "complete"}:
                    continue
                try:
                    self.queue(cid)
                except (ValueError, PermissionError, OSError) as exc:
                    if "fila" in str(exc).casefold() or "cheia" in str(exc).casefold():
                        break
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
        if os.getenv("NEXUS_PERFORMANCE_POLL", "1") == "1":
            def metrics_loop():
                while True:
                    try:
                        self.performance.refresh(limit=10)
                    except (OSError, ValueError, RuntimeError) as exc:
                        print(f"Metrics refresh skipped: {type(exc).__name__}", flush=True)
                    time.sleep(6 * 3600)
            threading.Thread(target=metrics_loop, name="platform-metrics", daemon=True).start()

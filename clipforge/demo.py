"""Opt-in, rate-limited REAL pipeline rehearsal using original synthetic footage.

No Twitch content, internet, models or external video assets. This is not a
mocked animation: FFmpeg generates a legitimate owned input, then the normal
ingestion, rights gate, curation and render worker process it.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path


class SyntheticDemo:
    MAX_RUNS = 3

    def __init__(self, runtime):
        self.runtime = runtime
        self.enabled = os.getenv("ENABLE_SYNTHETIC_DEMO", "0") == "1"
        self.lock = threading.Lock()
        self.running = False

    def start(self) -> dict:
        if not self.enabled:
            raise PermissionError("Synthetic test mode is disabled")
        with self.lock:
            if self.running:
                raise ValueError("A synthetic test is already being generated")
            existing = sum(
                c["filename"].startswith("mission-demo-")
                for c in self.runtime.store.all()
            )
            if existing >= self.MAX_RUNS:
                raise ValueError("Demo limit reached: 3 owned clips per data volume")
            self.running = True
            index = existing + 1
            threading.Thread(target=self._generate, args=(index,),
                             daemon=True, name="synthetic-demo").start()
        return {"accepted": True, "mode": "synthetic_owned", "run": index}

    def _generate(self, index: int) -> None:
        store = self.runtime.store
        name = f"mission-demo-{index}.mp4"
        video = store.incoming / name
        sidecar = store.incoming / f"{name}.rights.json"
        store.activity.append(None, "ingestao", "running",
                              "Gerando amostra própria com FFmpeg (teste real)")
        try:
            subprocess.run([
                "ffmpeg", "-y", "-nostdin", "-v", "error",
                "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30",
                "-f", "lavfi", "-i", "sine=frequency=500:sample_rate=48000",
                "-t", "12", "-shortest",
                "-c:v", "libx264", "-preset", "ultrafast",
                "-pix_fmt", "yuv420p", "-c:a", "aac", str(video)
            ], check=True, capture_output=True, timeout=75)
            sidecar.write_text(
                json.dumps({
                    "creator": "GTA CLIPS — AMOSTRA SINTÉTICA",
                    "rights_status": "owned", "duration_sec": 10,
                    "source_url": "",
                }), encoding="utf-8")
            item = store.ingest(sidecar)
            if item is None:
                # The regular scanner may have already picked up the sidecar.
                item = next(
                    (c for c in store.all() if c["filename"] == name), None)
            if not item:
                raise ValueError("Could not import generated clip")
            if item["status"] == "detected":
                self.runtime.queue(item["id"])
            store.activity.append(None, "ingestao", "complete",
                                  "Amostra própria adicionada ao pipeline de vídeo")
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            store.activity.append(None, "ingestao", "failed",
                                  "Teste sintético falhou; verificar FFmpeg e armazenamento")
            print(f"Synthetic test failure: {type(exc).__name__}", flush=True)
        finally:
            with self.lock:
                self.running = False

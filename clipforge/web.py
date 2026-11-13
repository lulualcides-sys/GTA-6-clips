"""Minimal protected API and mobile dashboard; no third-party web framework required."""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from .core import Runtime

STATIC = Path(__file__).with_name("static")


def make_handler(runtime: Runtime):
    token = os.getenv("DASHBOARD_TOKEN", "")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            """The Windows --windowed executable has sys.stderr=None.

            HTTP server default logging crashes before headers are sent when
            stderr is unavailable. Event telemetry is stored in SQLite.
            Avoid logging tokens, media paths or private request metadata.
            """
            return

        def _auth(self) -> bool:
            return not token or self.headers.get("Authorization") == f"Bearer {token}"

        def _reply(self, status: int, body: dict):
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _file(self, path: Path, mime: str):
            if not path.is_file():
                return self._reply(404, {"error": "Not found"})
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(path.stat().st_size))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            with path.open("rb") as stream:
                for part in iter(lambda: stream.read(1024 * 1024), b""):
                    self.wfile.write(part)

        def _clip_id(self, pieces: list[str]) -> str | None:
            return pieces[2] if len(pieces) >= 3 and pieces[2].isalnum() else None

        def do_GET(self):
            route = urlsplit(self.path).path
            if route in ("/", "/index.html"):
                return self._file(STATIC / "index.html", "text/html; charset=utf-8")
            assets = {"/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/styles.css": ("styles.css", "text/css; charset=utf-8"),
                      "/candidates.js": ("candidates.js", "text/javascript; charset=utf-8"),
                      "/agents.js": ("agents.js", "text/javascript; charset=utf-8"),
                      "/agents.css": ("agents.css", "text/css; charset=utf-8")}
            if route in assets:
                name, mime = assets[route]
                return self._file(STATIC / name, mime)
            if route == "/api/health":
                return self._reply(200, {"status": "ok", "service": "gta6-clips",
                                         "authenticated": bool(token)})
            if not self._auth():
                return self._reply(401, {"error": "Unauthorized"})
            if route == "/api/agents":
                params = parse_qs(urlsplit(self.path).query)
                clip_ids = params.get("clip_id", [])
                if len(clip_ids) > 1:
                    return self._reply(400, {"error": "One clip ID at a time"})
                clip_id = clip_ids[0] if clip_ids else None
                try:
                    return self._reply(200, runtime.store.activity.snapshot(runtime, clip_id))
                except ValueError:
                    return self._reply(400, {"error": "Invalid clip ID"})
                except LookupError:
                    return self._reply(404, {"error": "Clip not found"})
            if route == "/api/twitch/status":
                return self._reply(200, runtime.twitch.status())
            if route == "/api/twitch/candidates":
                return self._reply(200, {"candidates": runtime.twitch.list_candidates()})
            if route == "/api/captions":
                return self._reply(200, {"captions": runtime.captions.all_statuses(),
                                         "transcription_available": runtime.captions.available(),
                                         "auto_transcribe": runtime.auto_transcribe})
            if route == "/api/clips":
                # Never expose private proof of license or local input paths to UI.
                clips = runtime.store.all()
                for item in clips:
                    item.pop("evidence", None)
                    item.pop("input_path", None)
                    item["output_path"] = bool(item.get("output_path"))
                return self._reply(200, {"clips": clips})
            pieces = route.strip("/").split("/")
            if len(pieces) == 4 and pieces[:2] == ["api", "clips"] and pieces[-1] == "captions.srt":
                clip_id = self._clip_id(pieces)
                subtitle = runtime.captions.captions_file(clip_id or "")
                if not subtitle:
                    return self._reply(404, {"error": "No current captions available"})
                return self._file(subtitle, "text/plain; charset=utf-8")
            if len(pieces) == 4 and pieces[:2] == ["api", "clips"] and pieces[-1] == "hyperframes.zip":
                clip_id = self._clip_id(pieces)
                item = runtime.store.get(clip_id or "")
                if not item or item["status"] not in {"ready", "approved"}:
                    return self._reply(404, {"error": "No exportable clip"})
                archive = runtime.store.root / "hyperframes" / clip_id / "hyperframes-project.zip"
                if not archive.is_file() or archive.is_symlink():
                    return self._reply(404, {"error": "Export first"})
                return self._file(archive, "application/zip")
            if len(pieces) == 4 and pieces[:2] == ["api", "clips"] and pieces[-1] == "video":
                item = runtime.store.get(self._clip_id(pieces) or "")
                if not item or not item["output_path"]:
                    return self._reply(404, {"error": "Video not found"})
                target = Path(item["output_path"])
                if target.parent.resolve() != runtime.store.output:
                    return self._reply(403, {"error": "Invalid output"})
                return self._file(target, "video/mp4")
            return self._reply(404, {"error": "Not found"})

        def do_POST(self):
            route = urlsplit(self.path).path
            if not self._auth():
                return self._reply(401, {"error": "Unauthorized"})
            if self.headers.get("Content-Length", "0") not in ("", "0"):
                return self._reply(400, {"error": "Body not accepted"})
            if route == "/api/twitch/refresh":
                from .twitch import TwitchError
                try:
                    return self._reply(200, runtime.twitch.refresh())
                except TwitchError as exc:
                    return self._reply(503, {"error": str(exc)})
            if route == "/api/demo":
                try:
                    return self._reply(202, runtime.demo.start())
                except PermissionError:
                    return self._reply(403, {"error": "Modo de teste sintético desativado"})
                except ValueError as exc:
                    return self._reply(409, {"error": str(exc)[:180]})
            if route == "/api/scan":
                result = runtime.scan()
                if result["errors"]:
                    runtime.store.activity.append(
                        None, "ingestao", "failed",
                        f"{len(result['errors'])} manifesto(s) rejeitado(s) na leitura local"
                    )
                return self._reply(200, result)
            pieces = route.strip("/").split("/")
            if len(pieces) != 4 or pieces[:2] != ["api", "clips"]:
                return self._reply(404, {"error": "Not found"})
            item_id = self._clip_id(pieces)
            item = runtime.store.get(item_id) if item_id else None
            if not item:
                return self._reply(404, {"error": "Clip not found"})
            action = pieces[-1]
            if action == "transcribe":
                try:
                    queued = runtime.captions.queue(item_id)
                    return self._reply(202 if queued else 409, {
                        "queued": queued,
                        "captions": runtime.captions.status(item_id)
                    })
                except (ValueError, OSError) as exc:
                    return self._reply(409, {"error": str(exc)[:240]})
            if action == "hyperframes":
                from .hyperframes import export_composition
                if item["status"] not in {"ready", "approved"}:
                    return self._reply(409, {"error": "Clip must be ready"})
                runtime.store.activity.append(
                    item_id, "motion", "running", "Preparando pacote editável HyperFrames"
                )
                try:
                    export_composition(
                        runtime.store, item_id,
                        captions_file=runtime.captions.captions_file(item_id)
                    )
                except (ValueError, OSError) as exc:
                    runtime.store.activity.append(
                        item_id, "motion", "failed", "Falha na exportação HyperFrames"
                    )
                    return self._reply(409, {"error": str(exc)[:250]})
                runtime.store.activity.append(
                    item_id, "motion", "complete", "Composição HTML/CSS exportada, não publicada"
                )
                return self._reply(201, {
                    "status": "prepared", "engine": "HyperFrames",
                    "rendered": False,
                    "download_path": f"/api/clips/{item_id}/hyperframes.zip"
                })
            if action == "render":
                queued = runtime.queue(item_id)
                return self._reply(202 if queued else 409, {"queued": queued})
            if action in ("approve", "reject"):
                if item["status"] not in ({"ready"} if action == "approve" else {"ready", "approved"}):
                    return self._reply(409, {"error": "Invalid state"})
                runtime.store.update(item_id, status="approved" if action == "approve" else "rejected")
                return self._reply(200, {"status": action})
            return self._reply(404, {"error": "Not found"})

    return Handler


def main():
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    token = os.getenv("DASHBOARD_TOKEN", "")
    if host not in {"localhost", "127.0.0.1", "::1"} and (
        len(token) < 24 or token.startswith(("REPLACE_", "CHANGE_ME", "example-"))
    ):
        raise SystemExit(
            "Strong DASHBOARD_TOKEN (24+ characters) required for non-local binding. "
            "Configure an HTTPS reverse proxy before exposing the service."
        )
    runtime = Runtime(Path(os.getenv("CLIPS_DATA_DIR", "./data")))
    runtime.start_polling()
    runtime.twitch.start_polling()
    httpd = ThreadingHTTPServer((host, port), make_handler(runtime))
    print(f"GTA6 Clips dashboard listening at http://{host}:{port}", flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        runtime.executor.shutdown(wait=False)
        runtime.captions.stop()


if __name__ == "__main__":
    main()

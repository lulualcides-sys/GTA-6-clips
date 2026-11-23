"""Minimal protected API and mobile dashboard; no third-party web framework required."""
from __future__ import annotations

import json
import os
import re
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from .core import Runtime

STATIC = Path(__file__).with_name("static")


def start_publishing(runtime):
    """Inicia fila somente quando habilitada, compartilhada com painel e desktop."""
    with runtime.store.lock:
        if not hasattr(runtime, "publishing"):
            from .publishing import PublishingService
            runtime.publishing = PublishingService(runtime.store)
        runtime.publishing.start()
        return runtime.publishing


def stop_publishing(runtime):
    """Interrompe polling sem apagar trabalhos persistidos."""
    service = getattr(runtime, "publishing", None)
    if service is not None:
        service.stop()


def make_handler(runtime: Runtime):
    token = os.getenv("DASHBOARD_TOKEN", "")
    from .mobile_pairing import MobilePairing
    mobile = MobilePairing()

    def publishing():
        # Serviço compartilhado; inicialização não inicia postagens.
        with runtime.store.lock:
            if not hasattr(runtime, "publishing"):
                from .publishing import PublishingService
                runtime.publishing = PublishingService(runtime.store)
        return runtime.publishing

    def autoclip():
        with runtime.store.lock:
            if not hasattr(runtime, "autoclip_bridge"):
                from .autoclip_bridge import AutoClipBridge
                runtime.autoclip_bridge = AutoClipBridge(runtime.store)
        return runtime.autoclip_bridge

    def exporter():
        with runtime.store.lock:
            if not hasattr(runtime, "exporter"):
                from .exporter import Exporter
                runtime.exporter = Exporter(runtime.store)
        return runtime.exporter

    def local_ai():
        with runtime.store.lock:
            if not hasattr(runtime, "local_ai"):
                from .local_ai import LocalAI
                runtime.local_ai = LocalAI(runtime.store.root)
            bridge = autoclip()
            if bridge.local_ai is None:
                bridge.local_ai = runtime.local_ai
        return runtime.local_ai

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            """The Windows --windowed executable has sys.stderr=None.

            HTTP server default logging crashes before headers are sent when
            stderr is unavailable. Event telemetry is stored in SQLite.
            Avoid logging tokens, media paths or private request metadata.
            """
            return

        def _owner_auth(self):
            return bool(token and self.headers.get("Authorization") == f"Bearer {token}")

        def _auth(self) -> bool:
            if self._owner_auth():
                return True
            if mobile.valid_cookie(self.headers.get("Cookie", "")):
                route = urlsplit(self.path).path
                if mobile.allowed(self.command, route):
                    if self.command == "POST":
                        return mobile._same_origin(self.headers.get("Origin", ""),
                                                   self.headers.get("Host", ""))
                    return True
            # Preserve local dev behavior; Windows uses a random owner token.
            return not token

        def _reply(self, status: int, body: dict, extra_headers=None):
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if extra_headers:
                for name, value in extra_headers:
                    self.send_header(name, value)
            self.end_headers()
            self.wfile.write(payload)

        def _file(self, path: Path, mime: str):
            if not path.is_file() or path.is_symlink():
                return self._reply(404, {"error": "Not found"})
            size = path.stat().st_size
            start, end = 0, size - 1
            requested = self.headers.get("Range")
            if requested:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
                try:
                    if not match or not any(match.groups()) or size == 0:
                        raise ValueError
                    left, right = match.groups()
                    if left:
                        start = int(left)
                        end = min(int(right), size - 1) if right else size - 1
                    else:
                        count = int(right)
                        if count <= 0:
                            raise ValueError
                        start = max(0, size - count)
                    if start > end or start >= size:
                        raise ValueError
                except ValueError:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
            self.send_response(206 if requested else 200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(max(0, end - start + 1)))
            self.send_header("Accept-Ranges", "bytes")
            if requested:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            try:
                with path.open("rb") as stream:
                    stream.seek(start)
                    remaining = end - start + 1
                    while remaining > 0:
                        part = stream.read(min(1024 * 1024, remaining))
                        if not part:
                            break
                        self.wfile.write(part)
                        remaining -= len(part)
            except (BrokenPipeError, ConnectionResetError):
                pass  # O player pode cancelar uma leitura ao buscar outro instante.

        def _body(self):
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("Transfer-Encoding não aceito")
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise ValueError("Content-Length inválido") from None
            if not 0 < length <= 16384:
                raise ValueError("JSON deve ter entre 1 e 16384 bytes")
            if self.headers.get_content_type() != "application/json":
                raise ValueError("Content-Type application/json obrigatório")
            self.connection.settimeout(10)
            try:
                body = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Número não finito")))
            except (ValueError, UnicodeDecodeError, TimeoutError):
                raise ValueError("JSON inválido") from None
            if not isinstance(body, dict):
                raise ValueError("Objeto JSON obrigatório")
            return body

        def _clip_id(self, pieces: list[str]) -> str | None:
            return pieces[2] if len(pieces) >= 3 and pieces[2].isalnum() else None

        def do_GET(self):
            route = urlsplit(self.path).path
            if route in ("/", "/index.html"):
                return self._file(STATIC / "index.html", "text/html; charset=utf-8")
            if route in ("/review", "/review/"):
                return self._file(STATIC / "mobile-review.html", "text/html; charset=utf-8")
            assets = {"/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/editor.js": ("editor.js", "text/javascript; charset=utf-8"),
                      "/styles.css": ("styles.css", "text/css; charset=utf-8"),
                      "/candidates.js": ("candidates.js", "text/javascript; charset=utf-8"),
                      "/viral.js": ("viral.js", "text/javascript; charset=utf-8"),
                      "/activity.js": ("activity.js", "text/javascript; charset=utf-8"),
                      "/youtube.js": ("youtube.js", "text/javascript; charset=utf-8"),
                      "/agents.js": ("agents.js", "text/javascript; charset=utf-8"),
                      "/agents.css": ("agents.css", "text/css; charset=utf-8"),
                      "/studio-v2.css": ("studio-v2.css", "text/css; charset=utf-8"),
                      "/shell.css": ("shell.css", "text/css; charset=utf-8"),
                      "/shell.js": ("shell.js", "text/javascript; charset=utf-8"),
                      "/mobile-review.js": ("mobile-review.js", "text/javascript; charset=utf-8"),
                      "/mobile-review.css": ("mobile-review.css", "text/css; charset=utf-8"),
                      "/editorial.js": ("editorial.js", "text/javascript; charset=utf-8")}
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
                return self._reply(200, {**runtime.twitch.status(),
                                         "auto_pipeline": runtime.twitch_auto.status()})
            if route == "/api/twitch/candidates":
                return self._reply(200, {"candidates": runtime.twitch.list_candidates()})
            if route == "/api/twitch/viral":
                from .viral_radar import radar
                pt_only = parse_qs(urlsplit(self.path).query).get("pt", ["1"])[0] != "0"
                return self._reply(200, radar(runtime, pt_only=pt_only))
            if route == "/api/youtube/radar":
                from .youtube_radar import radar as youtube_radar
                pt_only = parse_qs(urlsplit(self.path).query).get("pt", ["0"])[0] == "1"
                return self._reply(200, youtube_radar(runtime, pt_only=pt_only))
            if route == "/api/youtube/status":
                return self._reply(200, runtime.youtube_auto.status())
            if route == "/api/twitch/streamers":
                return self._reply(200, {"streamers": runtime.twitch.list_streamers()})
            if route == "/api/ingest/history":
                query = parse_qs(urlsplit(self.path).query)
                status = query.get("status", [""])[0] or None
                return self._reply(200, {"items": runtime.ingest_log.list(150, status),
                                         "counts": runtime.ingest_log.counts(),
                                         "twitch": runtime.twitch_auto.status(),
                                         "youtube": runtime.youtube_auto.status()})
            if route == "/api/live":
                return self._reply(200, runtime.live_monitor.status())
            if route == "/api/notifications":
                from .notifications import collect
                return self._reply(200, collect(runtime, publishing()))
            if route == "/api/autoclip/settings":
                from . import autoclip_settings as acs
                return self._reply(200, {"settings": acs.load(runtime.store.root),
                                         "presets": acs.PRESETS, "fonts": list(acs.FONTS),
                                         "framing": acs.FRAMING,
                                         "custom_supported": autoclip().custom_captions_supported()})
            if route == "/api/exports":
                return self._reply(200, {"exports": exporter().list()})
            if route.startswith("/api/exports/"):
                try:
                    file = exporter().path(route.rsplit("/", 1)[1])
                except ValueError as exc:
                    return self._reply(404, {"error": str(exc)})
                mime = {"mp4": "video/mp4", "mov": "video/quicktime", "webm": "video/webm"}.get(
                    file.suffix.lstrip("."), "application/octet-stream")
                return self._file(file, mime)
            if route == "/api/autoclip":
                local_ai()  # Liga o início automático do Ollama ao AutoClip.
                return self._reply(200, autoclip().status())
            if route == "/api/local-ai":
                return self._reply(200, local_ai().status())
            if route == "/api/publishing":
                service = publishing()
                return self._reply(200, {**service.status(), "jobs": service.all()})
            if route == "/api/editorial/summary":
                return self._reply(200, runtime.editorial.feedback_summary())
            if route == "/api/metrics":
                return self._reply(200, runtime.performance.summary())
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
            if (len(pieces) == 5 and pieces[:2] == ["api", "clips"] and
                    pieces[3] == "autoclip-preview" and pieces[4].isdigit()):
                clip_id = self._clip_id(pieces)
                if not clip_id:
                    return self._reply(404, {"error": "Clipe não encontrado"})
                try:
                    target = autoclip().preview(clip_id, int(pieces[4]))
                except ValueError as exc:
                    return self._reply(404, {"error": str(exc)})
                return self._file(target, "video/mp4")
            if len(pieces) == 4 and pieces[:2] == ["api", "clips"] and pieces[-1] == "editorial":
                clip_id = self._clip_id(pieces)
                if not clip_id or not runtime.store.get(clip_id):
                    return self._reply(404, {"error": "Clipe não encontrado"})
                return self._reply(200, runtime.editorial.get(clip_id))
            if len(pieces) == 4 and pieces[:2] == ["api", "clips"] and pieces[-1] in {"original", "edit"}:
                item_id = self._clip_id(pieces)
                item = runtime.store.get(item_id or "")
                if not item:
                    return self._reply(404, {"error": "Clip not found"})
                if pieces[-1] == "edit":
                    return self._reply(200, runtime.store.get_edit(item_id))
                target = Path(item["input_path"])
                if target.is_symlink() or target.parent.resolve() != runtime.store.incoming:
                    return self._reply(403, {"error": "Invalid source"})
                mime = {".webm": "video/webm", ".mov": "video/quicktime", ".mkv": "video/x-matroska"}.get(target.suffix.lower(), "video/mp4")
                return self._file(target, mime)
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
            if route == "/api/mobile/connect":
                try:
                    body = self._body()
                    if set(body) != {"code"}:
                        raise ValueError("Informe apenas o código de pareamento")
                    session = mobile.claim(body["code"], self.headers.get("Origin", ""),
                                           self.headers.get("Host", ""))
                    cookie = (f"{mobile.COOKIE}={session}; Path=/; Max-Age=43200; "
                              "Secure; HttpOnly; SameSite=Strict")
                    return self._reply(200, {"connected": True}, [("Set-Cookie", cookie)])
                except (ValueError, TypeError, PermissionError) as exc:
                    return self._reply(403, {"error": str(exc)[:160]})
            if not self._auth():
                return self._reply(401, {"error": "Unauthorized"})
            if route == "/api/mobile/pair":
                if not self._owner_auth():
                    return self._reply(403, {"error": "Somente o computador pode iniciar o pareamento"})
                return self._reply(200, {**mobile.new_code(), "port": self.server.server_port})
            if route == "/api/twitch/policies":
                if not self._owner_auth():
                    return self._reply(403, {"error": "Somente o computador consulta a Twitch"})
                from .viral_radar import radar, scan_policies
                try:
                    ids = [r["broadcaster_id"] for r in radar(runtime)["streamers"]]
                    return self._reply(200, scan_policies(runtime, ids))
                except ValueError as exc:
                    return self._reply(409, {"error": str(exc)[:200]})
            if route == "/api/twitch/sources":
                if not self._owner_auth():
                    return self._reply(403, {"error": "Somente o computador altera autorizações"})
                from .viral_radar import add_source, remove_source
                try:
                    body = self._body()
                    if not isinstance(body, dict):
                        raise ValueError("JSON inválido")
                    if body.get("action") == "remove":
                        removed = remove_source(runtime.store.root, str(body.get("broadcaster_id", "")))
                        return self._reply(200, {"removed": removed})
                    added = add_source(runtime.store.root, body.get("broadcaster_id", ""),
                                       body.get("creator", ""), body.get("rights_status", ""),
                                       body.get("evidence", ""))
                    return self._reply(200, {"added": added})
                except ValueError as exc:
                    return self._reply(400, {"error": str(exc)[:200]})
            if route == "/api/youtube/radar/refresh":
                if not self._owner_auth():
                    return self._reply(403, {"error": "Somente o computador consulta o YouTube"})
                from .youtube_radar import radar as youtube_radar
                return self._reply(200, youtube_radar(runtime, force=True))
            if route == "/api/youtube/run":
                if not self._owner_auth():
                    return self._reply(403, {"error": "Somente o computador inicia downloads"})
                started = runtime.youtube_auto.kick()
                state = runtime.youtube_auto.status()
                if not started:
                    return self._reply(409, {"started": False,
                                             "error": state.get("last_error") or "Já em execução."})
                return self._reply(202, {"started": True, **state})
            if route == "/api/youtube/sources":
                if not self._owner_auth():
                    return self._reply(403, {"error": "Somente o computador altera autorizações"})
                from .youtube_radar import add_source as yt_add, remove_source as yt_remove
                try:
                    body = self._body()
                    if body.get("action") == "remove":
                        removed = yt_remove(runtime.store.root, str(body.get("channel_id", "")))
                        return self._reply(200, {"removed": removed})
                    added = yt_add(runtime.store.root, body.get("channel_id", ""),
                                   body.get("creator", ""), body.get("rights_status", ""),
                                   body.get("evidence", ""))
                    return self._reply(200, {"added": added})
                except ValueError as exc:
                    return self._reply(400, {"error": str(exc)[:200]})
            if route == "/api/connections/check":
                if not self._owner_auth():
                    return self._reply(403, {"error": "Somente o computador testa conexões"})
                from .connection_check import check_all
                return self._reply(200, check_all(runtime))
            if route == "/api/ingest/run":
                if not self._owner_auth():
                    return self._reply(403, {"error": "Somente o computador inicia verificações"})
                import threading as _threading
                runtime.twitch_auto.trigger = "manual"
                runtime.youtube_auto.trigger = "manual"
                started = {"twitch": runtime.twitch_auto.kick(), "youtube": runtime.youtube_auto.kick()}
                for name, worker in (("twitch", runtime.twitch_auto), ("youtube", runtime.youtube_auto)):
                    if not started[name]:
                        worker.trigger = "automatico"  # nada iniciou: não marcar a próxima rodada
                _threading.Thread(target=runtime.live_monitor.check, args=("manual",),
                                  daemon=True, name="live-check-manual").start()
                started["lives"] = True
                return self._reply(202, {"started": started})
            if route == "/api/live/settings":
                if not self._owner_auth():
                    return self._reply(403, {"error": "Somente o computador altera o monitor de lives"})
                try:
                    body = self._body()
                    if not isinstance(body, dict) or set(body) - {"vod_download", "public_download", "record"} \
                            or any(not isinstance(v, bool) for v in body.values()):
                        raise ValueError("Envie vod_download/public_download como true/false")
                    updates = {}
                    if "vod_download" in body:
                        updates["TWITCH_LIVE_VOD_DOWNLOAD"] = "1" if body["vod_download"] else "0"
                    if "record" in body:
                        updates["TWITCH_LIVE_RECORD"] = "1" if body["record"] else "0"
                    if "public_download" in body:
                        updates["TWITCH_PUBLIC_DOWNLOAD"] = "1" if body["public_download"] else "0"
                    from .twitch_oauth import save_private_config
                    save_private_config(runtime.store.root.parent, updates)
                    return self._reply(200, runtime.live_monitor.status())
                except (ValueError, OSError) as exc:
                    return self._reply(400, {"error": str(exc)[:200]})
            if route == "/api/autoclip/settings":
                if not self._owner_auth():
                    return self._reply(403, {"error": "Somente o computador altera o AutoClip"})
                from . import autoclip_settings as acs
                try:
                    return self._reply(200, {"settings": acs.save(runtime.store.root, self._body())})
                except ValueError as exc:
                    return self._reply(400, {"error": str(exc)[:200]})
            if route.startswith("/api/exports/") and route.endswith("/delete"):
                if not self._owner_auth():
                    return self._reply(403, {"error": "Somente o computador apaga exportações"})
                try:
                    exporter().delete(route.split("/")[3])
                    return self._reply(200, {"deleted": True})
                except (ValueError, OSError) as exc:
                    return self._reply(404, {"error": str(exc)[:200]})
            parts = route.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["api", "clips"] and parts[3] == "export":
                if not self._owner_auth():
                    return self._reply(403, {"error": "Somente o computador exporta"})
                try:
                    return self._reply(200, exporter().export(parts[2], self._body()))
                except ValueError as exc:
                    return self._reply(400, {"error": str(exc)[:220]})
            if route == "/api/local-ai/prepare":
                if not self._owner_auth():
                    return self._reply(403, {"error": "Somente o computador pode instalar a IA local"})
                try:
                    body = self._body()
                    model = body.get("model", "") if isinstance(body, dict) else ""
                    return self._reply(202, local_ai().prepare(model or "llama3.1:8b"))
                except ValueError as exc:
                    return self._reply(409, {"error": str(exc)[:200]})
            if route == "/api/metrics/refresh":
                if not self._owner_auth():
                    return self._reply(403, {"error": "Somente o proprietário atualiza métricas"})
                return self._reply(200, runtime.performance.refresh(limit=10))
            pieces = route.strip("/").split("/")
            json_action = (route == "/api/clips/approve-batch" or
                           (len(pieces) == 4 and pieces[:2] == ["api", "clips"] and pieces[-1] in {"edit", "publish", "review"}))
            if json_action:
                try:
                    body = self._body()
                except ValueError as exc:
                    return self._reply(400, {"error": str(exc)})
                if route == "/api/clips/approve-batch":
                    ids = body.get("clip_ids")
                    if set(body) != {"clip_ids"} or not isinstance(ids, list) or not 1 <= len(ids) <= 100 or any(not isinstance(i, str) or not i.isalnum() for i in ids):
                        return self._reply(400, {"error": "Selecione de 1 a 100 clipes válidos"})
                    approved, skipped = [], []
                    with runtime.store.lock:
                        for clip_id in dict.fromkeys(ids):
                            item = runtime.store.get(clip_id)
                            if item and item["status"] == "ready":
                                runtime.editorial.review(clip_id, "approve")
                                approved.append(clip_id)
                            else:
                                skipped.append(clip_id)
                    return self._reply(200, {"approved": approved, "skipped": skipped})
                item_id = self._clip_id(pieces)
                if not runtime.store.get(item_id or ""):
                    return self._reply(404, {"error": "Clip not found"})
                try:
                    if pieces[-1] == "edit":
                        return self._reply(409, {"error": "Edição manual desativada. Somente AutoClip edita novos vídeos."})
                    if pieces[-1] == "review":
                        if set(body) - {"decision", "reason", "note"} or "decision" not in body:
                            raise ValueError("Informe uma decisão válida")
                        return self._reply(200, runtime.editorial.review(
                            item_id, body["decision"], body.get("reason"), body.get("note", "")))
                    allowed = {"platform", "title", "description", "scheduled_at"}
                    if set(body) - allowed or not {"platform", "title"} <= set(body):
                        raise ValueError("Plataforma e título obrigatórios")
                    result = publishing().enqueue(item_id, **body)
                    return self._reply(202, result)
                except (ValueError, TypeError, PermissionError, OSError, subprocess.SubprocessError) as exc:
                    return self._reply(409, {"error": str(exc)[:240]})
            if route == "/api/publishing/process" and self.headers.get("Content-Length", "0") in ("", "0"):
                return self._reply(200, {"job": publishing().process_one()})
            if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Length", "0") not in ("", "0"):
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
            if (len(pieces) == 5 and pieces[:2] == ["api", "clips"] and
                    pieces[3] == "autoclip-import" and pieces[4].isdigit()):
                clip_id = self._clip_id(pieces)
                if not clip_id or not runtime.store.get(clip_id):
                    return self._reply(404, {"error": "Clipe não encontrado"})
                try:
                    # A saída AutoClip é validada e disponibilizada diretamente
                    # para revisão; jamais reencaminhar ao renderizador FFmpeg.
                    trim = None
                    if int(self.headers.get("Content-Length", "0") or 0) > 0:
                        body = self._body()
                        if isinstance(body, dict) and body.get("end") not in (None, ""):
                            trim = {"start": body.get("start", 0), "end": body.get("end")}
                    result = autoclip().import_suggestion(clip_id, int(pieces[4]), trim)
                    return self._reply(201 if result["created"] else 200, result)
                except PermissionError as exc:
                    return self._reply(403, {"error": str(exc)[:200]})
                except (ValueError, OSError, subprocess.SubprocessError) as exc:
                    return self._reply(409, {"error": str(exc)[:200]})
            if len(pieces) == 4 and pieces[:2] == ["api", "clips"] and pieces[3] == "autoclip-redo":
                if not self._owner_auth():
                    return self._reply(403, {"error": "Somente o computador refaz cortes"})
                try:
                    return self._reply(202, autoclip().redo(pieces[2]))
                except (ValueError, PermissionError) as exc:
                    return self._reply(409, {"error": str(exc)[:200]})
            if len(pieces) != 4 or pieces[:2] != ["api", "clips"]:
                return self._reply(404, {"error": "Not found"})
            item_id = self._clip_id(pieces)
            item = runtime.store.get(item_id) if item_id else None
            if not item:
                return self._reply(404, {"error": "Clip not found"})
            action = pieces[-1]
            if action == "autoclip":
                try:
                    return self._reply(202, autoclip().queue(item_id))
                except PermissionError as exc:
                    return self._reply(403, {"error": str(exc)[:180]})
                except ValueError as exc:
                    return self._reply(409, {"error": str(exc)[:180]})
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
                    settings = runtime.store.get_edit(item_id)
                    include_captions = parse_qs(urlsplit(self.path).query).get("captions") == ["1"]
                    export_composition(
                        runtime.store, item_id,
                        title=settings.get("title", "") if settings.get("title_verified") else "",
                        captions_file=runtime.captions.captions_file(item_id) if include_captions else None
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
                try:
                    queued = runtime.queue(item_id)
                    return self._reply(202 if queued else 409, {"queued": queued,
                                                                  "engine": "autoclip"})
                except PermissionError as exc:
                    return self._reply(403, {"error": str(exc)[:200]})
                except (ValueError, OSError) as exc:
                    return self._reply(409, {"error": str(exc)[:200]})
            if action in ("approve", "reject"):
                # Releitura protegida evita aprovar versão invalidada por edição concorrente.
                with runtime.store.lock:
                    item = runtime.store.get(item_id)
                    if not item or item["status"] not in ({"ready"} if action == "approve" else {"ready", "approved"}):
                        return self._reply(409, {"error": "Invalid state"})
                    runtime.editorial.review(item_id, action, "outro" if action == "reject" else None)
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
    start_publishing(runtime)
    httpd = ThreadingHTTPServer((host, port), make_handler(runtime))
    print(f"GTA6 Clips dashboard listening at http://{host}:{port}", flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        runtime.executor.shutdown(wait=False)
        runtime.captions.stop()
        stop_publishing(runtime)


if __name__ == "__main__":
    main()

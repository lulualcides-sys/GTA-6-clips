"""One-time Twitch user OAuth consent for first-party clip download.

App credentials are for metadata; channel/editor clip downloads require a
separate user token with the official manage:clips scope. The browser grants
authorization; there is no scraping or bypass. Tokens stay on the local PC.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REDIRECT = "http://localhost:3000"
AUTHORIZE = "https://id.twitch.tv/oauth2/authorize"
EXCHANGE = "https://id.twitch.tv/oauth2/token"
VALIDATE = "https://id.twitch.tv/oauth2/validate"
SCOPES = "channel:manage:clips editor:manage:clips"


def _post_token(fields: dict) -> dict:
    payload = urllib.parse.urlencode(fields).encode("ascii")
    req = urllib.request.Request(EXCHANGE, data=payload, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=15) as response:
        raw = response.read(65536)
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError("Invalid Twitch token response")
    return obj


def _validate(token: str) -> dict:
    req = urllib.request.Request(VALIDATE,
                                 headers={"Authorization": "OAuth " + token})
    with urllib.request.urlopen(req, timeout=15) as response:
        obj = json.loads(response.read(65536))
    if not isinstance(obj, dict) or not str(obj.get("user_id", "")).isdigit():
        raise ValueError("Invalid Twitch authorization")
    if not {"channel:manage:clips", "editor:manage:clips"} & set(obj.get("scopes", [])):
        raise ValueError("Twitch did not grant the clip-download scope")
    return obj


def save_private_config(home: Path, updates: dict[str, str]):
    """Atomic edit of allowlisted secrets only, never submit tokens to browser JS."""
    from .desktop import initialize_settings
    conf = initialize_settings(home)
    current = conf.read_text(encoding="utf-8-sig").splitlines()
    pending = dict(updates)
    lines = []
    for line in current:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        lines.append(f"{key}={pending.pop(key)}" if key in pending else line)
    lines.extend(f"{k}={v}" for k, v in pending.items())
    temp = home / ("twitch-oauth-" + secrets.token_hex(8) + ".tmp")
    try:
        with temp.open("x", encoding="utf-8") as stream:
            stream.write("\n".join(lines) + "\n")
        os.replace(temp, conf)
    finally:
        temp.unlink(missing_ok=True)
    os.environ.update(updates)


def ensure_owned_channel(home: Path, user_id: str):
    """Auto-allowlist only the explicitly authorized user's OWN channel."""
    root = home / "data"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "twitch_sources.json"
    if path.is_symlink():
        raise ValueError("Invalid Twitch rights file")
    obj = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "broadcasters": []
    }
    if not isinstance(obj, dict) or not isinstance(obj.get("broadcasters"), list):
        raise ValueError("Invalid Twitch rights manifest")
    if not any(str(entry.get("id")) == user_id for entry in obj["broadcasters"]
               if isinstance(entry, dict)):
        obj["broadcasters"].append({
            "id": user_id, "creator": "Meu canal Twitch", "rights_status": "owned",
            "evidence": "Canal autenticado pelo OAuth Twitch",
        })
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)


class TwitchDownloadOAuth:
    def __init__(self, home: Path, runtime):
        self.home = home
        self.runtime = runtime
        self.lock = threading.Lock()
        self.active = False
        self.last_status = "not_started"
        self.last_error = None

    def status(self):
        return {"active": self.active, "status": self.last_status,
                "last_error": self.last_error,
                "grant_present": bool(os.getenv("TWITCH_USER_ACCESS_TOKEN")
                                      and os.getenv("TWITCH_EDITOR_ID"))}

    def begin(self):
        cid = os.getenv("TWITCH_CLIENT_ID", "").strip()
        secret = os.getenv("TWITCH_CLIENT_SECRET", "").strip()
        if not cid or not secret:
            return {"ok": False, "error": "Conecte a Twitch (Client ID e Secret) primeiro."}
        with self.lock:
            if self.active:
                return {"ok": False, "error": "Autorização Twitch já em andamento."}
            try:
                # Bind first to ensure that the configured OAuth redirect is usable.
                server = HTTPServer(("127.0.0.1", 3000), self._make_handler())
                server.timeout = 120
            except OSError:
                return {"ok": False, "error": "Porta 3000 indisponível; feche o programa que a utiliza."}
            self.active = True
            self.last_status = "waiting_for_twitch"
            self.last_error = None
        state = secrets.token_urlsafe(32)
        server.oauth_state = state
        server.oauth_result = None
        params = urllib.parse.urlencode({
            "client_id": cid,
            "redirect_uri": REDIRECT,
            "response_type": "code",
            "scope": SCOPES,
            "state": state,
        })
        url = AUTHORIZE + "?" + params
        threading.Thread(target=self._complete, args=(server, cid, secret),
                         daemon=True, name="twitch-user-oauth").start()
        if not webbrowser.open(url):
            self.last_error = "Navegador não abriu. Acesse a autenticação na Twitch."
        return {"ok": True, "status": "waiting_for_twitch",
                "message": "Conceda o acesso no site oficial Twitch aberto no navegador."}

    def _make_handler(self):
        class Callback(BaseHTTPRequestHandler):
            def do_GET(self):
                values = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                state = values.get("state", [""])[0]
                if not hmac.compare_digest(state, self.server.oauth_state):
                    self.send_error(403, "Invalid authorization state")
                    return
                code = values.get("code", [""])[0]
                denied = values.get("error", [""])[0]
                if not ((code.isascii() and 3 < len(code) < 500) or denied):
                    self.send_error(400, "Missing OAuth result")
                    return
                self.server.oauth_result = (code, denied)
                html = (b"<html><meta charset='utf-8'><title>Nexus Twitch</title>"
                        b"<body><h2>Twitch: volte ao Nexus Clips BR</h2>"
                        b"Pode fechar esta aba.</body></html>")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)

            def log_message(self, *_):
                return  # Never log OAuth codes or query strings.
        return Callback

    def _complete(self, server, client_id, client_secret):
        try:
            deadline = time.monotonic() + 120
            while server.oauth_result is None and time.monotonic() < deadline:
                # Ignore a browser favicon/preflight/invalid-state request;
                # never accept it as the OAuth callback.
                server.timeout = min(5, max(0.1, deadline - time.monotonic()))
                server.handle_request()
            result = server.oauth_result
            if not result:
                raise ValueError("Autorização Twitch não concluída.")
            code, denied = result
            if denied:
                raise ValueError("Permissão Twitch não concedida.")
            token = _post_token({
                "client_id": client_id, "client_secret": client_secret,
                "code": code, "grant_type": "authorization_code",
                "redirect_uri": REDIRECT,
            })
            access = str(token.get("access_token", ""))
            refresh = str(token.get("refresh_token", ""))
            if not access or not refresh:
                raise ValueError("Twitch não retornou credenciais renováveis.")
            verified = _validate(access)
            if verified.get("client_id") != client_id:
                raise ValueError("Token de outro aplicativo Twitch.")
            user_id = str(verified["user_id"])
            save_private_config(self.home, {
                "TWITCH_AUTO_DOWNLOAD": "1", "TWITCH_EDITOR_ID": user_id,
                "TWITCH_USER_ACCESS_TOKEN": access, "TWITCH_REFRESH_TOKEN": refresh,
            })
            ensure_owned_channel(self.home, user_id)
            self.last_status = "authorized"
            self.last_error = None
            # Refresh public metadata so eligible clips can enter the queue.
            threading.Thread(target=self._refresh, daemon=True).start()
        except (OSError, ValueError, KeyError, urllib.error.URLError,
                json.JSONDecodeError) as exc:
            self.last_status = "failed"
            self.last_error = str(exc)[:160] if not isinstance(exc, urllib.error.URLError) else (
                "Twitch OAuth indisponível; confirme Redirect URL http://localhost:3000.")
        finally:
            server.server_close()
            with self.lock:
                self.active = False

    def _refresh(self):
        from .twitch import TwitchError
        try:
            self.runtime.twitch.refresh()
        except (TwitchError, OSError):
            pass


def refreshed_token(home: Path, client_id: str, client_secret: str):
    """Refresh user OAuth without asking for another browser login."""
    access = os.getenv("TWITCH_USER_ACCESS_TOKEN", "").strip()
    refresh = os.getenv("TWITCH_REFRESH_TOKEN", "").strip()
    if not access or not refresh:
        return access
    try:
        obj = _validate(access)
        if int(obj.get("expires_in", 0)) >= 300:
            return access
    except (OSError, ValueError, urllib.error.URLError):
        pass
    try:
        data = _post_token({
            "grant_type": "refresh_token", "refresh_token": refresh,
            "client_id": client_id, "client_secret": client_secret,
        })
        updated = data.get("access_token")
        if not isinstance(updated, str) or not updated:
            return access
        changes = {"TWITCH_USER_ACCESS_TOKEN": updated}
        if data.get("refresh_token"):
            changes["TWITCH_REFRESH_TOKEN"] = str(data["refresh_token"])
        save_private_config(home, changes)
        return updated
    except (OSError, ValueError, urllib.error.URLError):
        return access

"""Short-lived manual device pairing for private mobile review over HTTPS.

Nexus continues to listen on localhost. The user must separately enable
Tailscale Serve (private tailnet HTTPS), never public Funnel/port forwarding.
Mobile cookies grant only read-only preview + explicit review decisions.
"""
from __future__ import annotations
import hashlib
import hmac
import secrets
import threading
import time
from http.cookies import SimpleCookie
from urllib.parse import urlsplit


class MobilePairing:
    COOKIE = "nexus_review"
    def __init__(self):
        self.lock = threading.RLock()
        self.code_digest = ""
        self.expires = 0
        self.tries = 0
        self.sessions = {}

    def new_code(self):
        code = f"{secrets.randbelow(10**10):010d}"
        with self.lock:
            self.code_digest = hashlib.sha256(code.encode()).hexdigest()
            self.expires = time.time() + 180
            self.tries = 0
        return {"code": code, "expires_in": 180,
                "message": "Abra /review via Tailscale Serve HTTPS e informe este código."}

    @staticmethod
    def _same_origin(origin: str, host: str):
        try:
            parsed = urlsplit(origin)
            return parsed.scheme == "https" and parsed.netloc.casefold() == host.casefold()
        except ValueError:
            return False

    def claim(self, code: str, origin: str, host: str):
        if not self._same_origin(origin, host):
            raise PermissionError("Conexão móvel requer HTTPS privado da mesma origem")
        if not isinstance(code, str) or len(code) != 10 or not code.isdecimal():
            raise PermissionError("Código inválido")
        with self.lock:
            if self.tries >= 8 or time.time() > self.expires or not self.code_digest:
                raise PermissionError("Código expirado ou tentativas excedidas")
            self.tries += 1
            digest = hashlib.sha256(code.encode()).hexdigest()
            if not hmac.compare_digest(digest, self.code_digest):
                raise PermissionError("Código incorreto")
            self.code_digest = ""  # one-time use
            token = secrets.token_urlsafe(40)
            self.sessions[hashlib.sha256(token.encode()).hexdigest()] = time.time() + 12 * 3600
            for key in list(self.sessions):
                if self.sessions[key] < time.time():
                    self.sessions.pop(key, None)
            return token

    def valid_cookie(self, raw_cookie: str) -> bool:
        if not isinstance(raw_cookie, str) or len(raw_cookie) > 4096:
            return False
        try:
            parsed = SimpleCookie()
            parsed.load(raw_cookie)
            morsel = parsed.get(self.COOKIE)
            token = morsel.value if morsel else ""
        except Exception:
            return False
        if not 24 < len(token) < 200:
            return False
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            return self.sessions.get(digest, 0) > time.time()

    @staticmethod
    def allowed(method: str, path: str) -> bool:
        from re import fullmatch
        if method == "GET":
            return path in {"/api/clips", "/api/editorial/summary", "/api/metrics"} or bool(
                fullmatch(r"/api/clips/[A-Za-z0-9]+/(video|editorial)", path))
        if method == "POST":
            return bool(fullmatch(r"/api/clips/[A-Za-z0-9]+/review", path))
        return False

    def revoke_all(self):
        with self.lock:
            self.sessions.clear()
            self.code_digest = ""

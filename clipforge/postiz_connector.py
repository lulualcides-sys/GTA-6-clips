"""Conector Postiz para a fila Nexus; não publica sem opt-in e conta conectada.

API pública documentada: /public/v1/upload, /posts, GET /posts.
A confirmação de upload no Postiz não é confirmação de publicação social.
"""
from __future__ import annotations

import http.client
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


BASE_HOST = "api.postiz.com"
BASE_PATH = "/public/v1"
MAX_MEDIA_BYTES = 512 * 1024 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _read_json(response):
    raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Resposta Postiz acima do limite.")
    data = json.loads(raw)
    return data


def api_json(key: str, endpoint: str, *, payload=None, query=None):
    """HTTPS fixo, sem seguir redirects para não vazar API key."""
    if not endpoint.startswith("/") or "?" in endpoint:
        raise ValueError("Endpoint Postiz inválido.")
    url = f"https://{BASE_HOST}{BASE_PATH}{endpoint}"
    if query:
        url += "?" + urlencode(query)
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Authorization": key, "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers,
                      method="POST" if body is not None else "GET")
    with build_opener(_NoRedirect).open(request, timeout=45) as response:
        return _read_json(response)


def upload_mp4(key: str, file: Path):
    """Multipart via stream (sem ler o MP4 inteiro em RAM)."""
    if file.is_symlink() or not file.is_file() or file.suffix.lower() != ".mp4":
        raise ValueError("Postiz exige MP4 regular.")
    size = file.stat().st_size
    if not 0 < size <= MAX_MEDIA_BYTES:
        raise ValueError("MP4 deve ter até 512 MiB para este conector.")
    boundary = "nexus-" + secrets.token_hex(16)
    prefix = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="adjust"\r\n\r\n'
        "false\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="clip.mp4"\r\n'
        "Content-Type: video/mp4\r\n\r\n"
    ).encode("ascii")
    suffix = f"\r\n--{boundary}--\r\n".encode("ascii")
    conn = http.client.HTTPSConnection(BASE_HOST, timeout=180)
    try:
        conn.putrequest("POST", BASE_PATH + "/upload")
        conn.putheader("Authorization", key)
        conn.putheader("Accept", "application/json")
        conn.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
        conn.putheader("Content-Length", str(len(prefix) + size + len(suffix)))
        conn.endheaders()
        conn.send(prefix)
        with file.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                conn.send(block)
        conn.send(suffix)
        response = conn.getresponse()
        if not 200 <= response.status < 300:
            raise ValueError("Upload ao Postiz rejeitado.")
        data = _read_json(response)
    finally:
        conn.close()
    if not isinstance(data, dict) or not data.get("id") or not data.get("path"):
        raise ValueError("Postiz não retornou mídia com ID e URL.")
    if not str(data["path"]).startswith("https://"):
        raise ValueError("Postiz retornou URL de mídia não HTTPS.")
    return {"id": str(data["id"]), "path": str(data["path"])}


class PostizConnector:
    """Usado com a mesma fila, revisão, limite e anti-duplicação do Nexus."""
    limitations = (
        "Requer POSTIZ_ENABLED=1, API key e ID do canal conectado. "
        "Publicação inicia privada; confirmação exige state=PUBLISHED e releaseURL. "
        "A conta e o processamento não foram validados remotamente."
    )

    def __init__(self, provider, key="", integration_id="", enabled=False):
        if provider not in {"youtube", "tiktok"}:
            raise ValueError("Canal Postiz não suportado.")
        self.provider = provider
        self.key = key
        self.integration_id = integration_id
        self.connected = bool(enabled and key and integration_id)

    def _settings(self, title):
        if self.provider == "youtube":
            return {"__type": "youtube", "title": title, "type": "private",
                    "selfDeclaredMadeForKids": "no", "tags": []}
        return {"__type": "tiktok", "title": "", "privacy_level": "SELF_ONLY",
                "duet": False, "stitch": False, "comment": True,
                "autoAddMusic": "no", "brand_content_toggle": False,
                "brand_organic_toggle": False, "content_posting_method": "DIRECT_POST"}

    def submit(self, job, path):
        if not self.connected:
            raise ValueError("Postiz não conectado.")
        media = upload_mp4(self.key, Path(path))
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        post = {
            "type": "now", "date": now, "shortLink": False, "tags": [],
            "posts": [{
                "integration": {"id": self.integration_id},
                "value": [{"content": job["title"] +
                           (("\n" + job["description"]) if job.get("description") else ""),
                           "image": [media]}],
                "settings": self._settings(job["title"])
            }]
        }
        response = api_json(self.key, "/posts", payload=post)
        if not isinstance(response, list) or len(response) != 1:
            raise ValueError("Postiz não confirmou uma postagem única.")
        entry = response[0]
        if not isinstance(entry, dict) or entry.get("integration") != self.integration_id:
            raise ValueError("Postiz retornou canal inesperado.")
        operation_id = entry.get("postId")
        if not isinstance(operation_id, str) or not operation_id:
            raise ValueError("Postiz não retornou ID de postagem.")
        return operation_id

    def check(self, remote_id):
        """Nunca confundir job do Postiz com vídeo publicado."""
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=7)).isoformat().replace("+00:00", "Z")
        end = (now + timedelta(days=7)).isoformat().replace("+00:00", "Z")
        data = api_json(self.key, "/posts", query={"startDate": start, "endDate": end})
        rows = data.get("posts", []) if isinstance(data, dict) else []
        if not isinstance(rows, list):
            return {"state": "pending"}
        for row in rows:
            if not isinstance(row, dict) or str(row.get("id")) != str(remote_id):
                continue
            integration = row.get("integration")
            if not isinstance(integration, dict) or integration.get("id") != self.integration_id:
                return {"state": "pending"}
            if row.get("state") == "ERROR":
                return {"state": "failed"}
            if row.get("state") == "PUBLISHED" and row.get("releaseURL"):
                return {"state": "confirmed", "remote_id": str(row["releaseURL"]),
                        "visibility": "unknown"}
            break
        return {"state": "pending"}


def postiz_connectors():
    enabled = os.getenv("POSTIZ_ENABLED", "0") == "1"
    key = os.getenv("POSTIZ_API_KEY", "")
    return {
        "postiz_youtube": PostizConnector("youtube", key,
            os.getenv("POSTIZ_YOUTUBE_INTEGRATION_ID", ""), enabled),
        "postiz_tiktok": PostizConnector("tiktok", key,
            os.getenv("POSTIZ_TIKTOK_INTEGRATION_ID", ""), enabled)
    }

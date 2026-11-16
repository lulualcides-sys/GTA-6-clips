"""Obtenção opt-in via Get Clips Download oficial; nunca infere URLs de mídia.

Contrato: https://dev.twitch.tv/docs/api/reference/clips#get-clips-download
Validado em 14/11/2026. Exige token de usuário com concessão específica e
manifesto separado de republicação. Links temporários não são persistidos.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .core import duration_of, probe

HELIX_BASE = "https://api.twitch.tv/helix"
VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
MAX_BYTES = 512 * 1024 * 1024
SCOPES = {"editor:manage:clips", "channel:manage:clips"}


class DownloadError(RuntimeError):
    """Erro seguro para interface, sem tokens ou URLs assinadas."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Impede envio de token para outro host e redirecionamento para rede local.
        raise DownloadError("Redirecionamento recusado; solicite novo link oficial")


def safe_download_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return (parsed.scheme == "https" and parsed.hostname == "production.assets.clips.twitchcdn.net"
                and parsed.port in (None, 443) and not parsed.username and not parsed.password)
    except (ValueError, TypeError):
        return False


def _json(opener, url: str, headers: dict) -> dict:
    with opener.open(Request(url, headers=headers), timeout=20) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise DownloadError("Resposta Twitch acima do limite")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise DownloadError("Resposta Twitch inválida")
    return result


def download_clip(clip_id: str, broadcaster_id: str, editor_id: str,
                  client_id: str, user_token: str, manifest: dict, incoming: Path) -> Path:
    """Obtém um clipe autorizado sem sobrescrever fonte ou manifesto existente.

    A autorização Helix é verificada antes do download. O manifesto é declaração
    independente de direitos de reutilização, não prova jurídica automática.
    """
    if (not re.fullmatch(r"[A-Za-z0-9_-]{1,180}", clip_id)
            or not broadcaster_id.isdigit() or not editor_id.isdigit()):
        raise DownloadError("IDs Twitch inválidos")
    if not client_id.strip() or not user_token.strip():
        raise DownloadError("Client ID e token de usuário privado são obrigatórios")
    if not isinstance(manifest, dict):
        raise DownloadError("Manifesto de direitos obrigatório")
    creator = str(manifest.get("creator", "")).strip()
    rights = manifest.get("rights_status")
    evidence = str(manifest.get("evidence", "")).strip()
    if (not creator or not isinstance(rights, str) or rights not in {"owned", "permission_granted"}
            or str(manifest.get("broadcaster_id", "")) != broadcaster_id
            or (rights == "permission_granted" and len(evidence) < 8)):
        raise DownloadError("Manifesto sem autorização válida para este broadcaster")
    incoming = Path(incoming).resolve()
    target = incoming / f"twitch-{clip_id}.mp4"
    sidecar = Path(str(target) + ".rights.json")
    if target.exists() or target.is_symlink() or sidecar.exists() or sidecar.is_symlink():
        raise DownloadError("Fonte ou manifesto já existe; download duplicado bloqueado")
    opener = build_opener(NoRedirect())
    temp_path = None
    installed = False
    sidecar_installed = False
    temp_sidecar = None
    try:
        token = _json(opener, VALIDATE_URL, {"Authorization": f"OAuth {user_token}"})
        if (token.get("client_id") != client_id or token.get("user_id") != editor_id
                or not SCOPES.intersection(token.get("scopes") or [])
                or int(token.get("expires_in", 0)) <= 0):
            raise DownloadError("Token incompatível com client/editor ou sem scope de download")
        query = urlencode({"broadcaster_id": broadcaster_id, "editor_id": editor_id, "clip_id": clip_id})
        payload = _json(opener, f"{HELIX_BASE}/clips/downloads?{query}",
                        {"Client-Id": client_id, "Authorization": f"Bearer {user_token}"})
        records = payload.get("data") or []
        record = next((row for row in records if isinstance(row, dict) and row.get("clip_id") == clip_id), None)
        if record is None:
            raise DownloadError("Clipe ausente ou sem autorização de acesso pelo editor")
        url = record.get("landscape_download_url") or record.get("portrait_download_url")
        if not url or not safe_download_url(url):
            raise DownloadError("URL oficial ausente ou domínio de download não permitido")
        incoming.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        # Arquivo parcial não é descoberto pelo scanner; o sidecar só aparece ao final.
        with tempfile.NamedTemporaryFile(dir=incoming, prefix=".twitch-", suffix=".part", delete=False) as output:
            temp_path = Path(output.name)
            with opener.open(Request(url), timeout=30) as response:
                declared = int(response.headers.get("Content-Length", 0))
                if declared > MAX_BYTES:
                    raise DownloadError("Mídia acima de 512 MiB")
                total, started = 0, time.monotonic()
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_BYTES or time.monotonic() - started > 180:
                        raise DownloadError("Download excedeu limite de tamanho ou tempo")
                    output.write(chunk)
                    digest.update(chunk)
                if not total or (declared and total != declared):
                    raise DownloadError("Download vazio ou incompleto")
        info = probe(temp_path)
        if duration_of(info) <= 0 or not any(s.get("codec_type") == "video" for s in info.get("streams", [])):
            raise DownloadError("Mídia recebida não é vídeo válido")
        # link falha atomicamente se outro processo já instalou o mesmo arquivo.
        os.link(temp_path, target)
        installed = True
        metadata = dict(manifest)
        metadata.update({"source_url": f"https://clips.twitch.tv/{clip_id}", "twitch_clip_id": clip_id,
                         "broadcaster_id": broadcaster_id, "download_method": "twitch_helix_clips_downloads",
                         "source_sha256": digest.hexdigest()})
        with tempfile.NamedTemporaryFile(dir=incoming, prefix=".twitch-rights-", suffix=".part",
                                         mode="w", encoding="utf-8", delete=False) as output:
            temp_sidecar = Path(output.name)
            json.dump(metadata, output, ensure_ascii=False, indent=2)
        os.link(temp_sidecar, sidecar)
        sidecar_installed = True
        return target
    except DownloadError:
        raise
    except HTTPError as exc:
        raise DownloadError(f"Twitch/download HTTP {exc.code}; confira concessões e tente novamente") from None
    except (URLError, OSError, ValueError, TypeError, http.client.HTTPException, subprocess.SubprocessError):
        raise DownloadError("Falha de rede, resposta ou arquivo; nenhum download foi aprovado") from None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        if temp_sidecar is not None:
            temp_sidecar.unlink(missing_ok=True)
        # Em falha de publicação do sidecar, não deixar mídia órfã como entrada pronta.
        if installed and not sidecar_installed:
            target.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Download oficial de clipe com direitos documentados")
    parser.add_argument("clip_id")
    parser.add_argument("--broadcaster-id", required=True)
    parser.add_argument("--editor-id", required=True)
    parser.add_argument("--rights", type=Path, required=True)
    parser.add_argument("--incoming", type=Path, default=Path("data/incoming"))
    args = parser.parse_args()
    try:
        if args.rights.is_symlink() or args.rights.stat().st_size > 64_000:
            raise DownloadError("Manifesto inválido ou acima de 64 KiB")
        manifest = json.loads(args.rights.read_text(encoding="utf-8"))
        result = download_clip(args.clip_id, args.broadcaster_id, args.editor_id,
                               os.getenv("TWITCH_CLIENT_ID", ""), os.getenv("TWITCH_USER_ACCESS_TOKEN", ""),
                               manifest, args.incoming)
        print(f"Fonte autorizada obtida: {result}")
    except (DownloadError, OSError, ValueError) as exc:
        parser.exit(1, f"Download bloqueado: {exc}\n")


if __name__ == "__main__":
    main()

"""Teste de conexão somente leitura: credencial salva ≠ credencial válida.

Cada verificação faz UMA chamada de leitura à API oficial (nunca posta, nunca
envia arquivo) e devolve apenas ok/erro curto e dados públicos do perfil.
Tokens nunca entram na resposta, em logs ou em mensagens de erro.
"""
from __future__ import annotations

import os
from urllib.error import HTTPError

from .social_connectors import request_json


def _http_error(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        if exc.code in (401, 403):
            return f"Credencial recusada (HTTP {exc.code}). Reconecte a conta."
        return f"API respondeu HTTP {exc.code}."
    return "Falha de rede ou resposta inválida."


def check_twitch(runtime) -> dict:
    twitch = runtime.twitch
    if not (twitch.client or (twitch.client_id and twitch.secret)):
        return {"configured": False, "ok": False, "detail": "Client ID/Secret não configurados."}
    from .twitch import TwitchClient, TwitchError
    client = twitch.client or TwitchClient(twitch.client_id, twitch.secret)
    try:
        client._token_value()
    except TwitchError as exc:
        return {"configured": True, "ok": False, "detail": f"Login do app recusado: {exc}"}
    result = {"configured": True, "ok": True, "detail": "Login do app Twitch válido."}
    # Responde também se a categoria GTA VI já existe para a virada de 19/11.
    try:
        configured = os.getenv("TWITCH_GAME_ID", "").strip()
        result["gta6_category_id"] = configured or client.find_gta6_game()
        result["detail"] += " Categoria GTA VI encontrada."
    except TwitchError:
        result["gta6_category_id"] = None
        result["detail"] += " Categoria GTA VI ainda não existe na Twitch."
    return result


def check_youtube() -> dict:
    token = os.getenv("YOUTUBE_ACCESS_TOKEN", "")
    if not token:
        return {"configured": False, "ok": False, "detail": "YOUTUBE_ACCESS_TOKEN não configurado."}
    try:
        data, _ = request_json("https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true", token)
        items = data.get("items") or []
        if not items:
            return {"configured": True, "ok": False, "detail": "Token válido, mas sem canal YouTube."}
        title = str(items[0].get("snippet", {}).get("title", ""))[:80]
        return {"configured": True, "ok": True, "detail": f"Canal conectado: {title}"}
    except (HTTPError, OSError, ValueError, AttributeError) as exc:
        return {"configured": True, "ok": False, "detail": _http_error(exc)}


def check_tiktok() -> dict:
    token = os.getenv("TIKTOK_ACCESS_TOKEN", "")
    if not token:
        return {"configured": False, "ok": False, "detail": "TIKTOK_ACCESS_TOKEN não configurado."}
    try:
        data, _ = request_json("https://open.tiktokapis.com/v2/user/info/?fields=display_name", token)
        error = (data.get("error") or {}).get("code", "ok")
        if error != "ok":
            return {"configured": True, "ok": False, "detail": f"TikTok recusou: {str(error)[:60]}"}
        name = str(((data.get("data") or {}).get("user") or {}).get("display_name", ""))[:80]
        return {"configured": True, "ok": True, "detail": f"Conta conectada: {name}"}
    except (HTTPError, OSError, ValueError, AttributeError) as exc:
        return {"configured": True, "ok": False, "detail": _http_error(exc)}


def check_postiz() -> dict:
    key = os.getenv("POSTIZ_API_KEY", "")
    if not key:
        return {"configured": False, "ok": False, "detail": "POSTIZ_API_KEY não configurada."}
    from .postiz_connector import api_json
    try:
        data = api_json(key, "/integrations")
    except (HTTPError, OSError, ValueError) as exc:
        return {"configured": True, "ok": False, "detail": _http_error(exc)}
    rows = data if isinstance(data, list) else (data.get("integrations") or [] if isinstance(data, dict) else [])
    ids = {str(r.get("id")) for r in rows if isinstance(r, dict)}
    missing = [name for name, env in (("YouTube", "POSTIZ_YOUTUBE_INTEGRATION_ID"),
                                      ("TikTok", "POSTIZ_TIKTOK_INTEGRATION_ID"))
               if os.getenv(env, "") and os.getenv(env, "") not in ids]
    if missing:
        return {"configured": True, "ok": False,
                "detail": "Chave válida, mas canal não encontrado no Postiz: " + ", ".join(missing)}
    return {"configured": True, "ok": True, "detail": f"Chave válida; {len(ids)} canal(is) no Postiz."}


def check_all(runtime) -> dict:
    return {"twitch": check_twitch(runtime), "youtube": check_youtube(),
            "tiktok": check_tiktok(), "postiz": check_postiz()}

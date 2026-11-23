"""Checklist "O que falta para funcionar": estado REAL de cada etapa do fluxo.

Ordem do fluxo: motor AutoClip -> IA local -> Twitch/YouTube conectados ->
canais autorizados -> download ligado -> primeiro download -> cortes prontos
-> publicação. Cada etapa diz se está ok, por quê, e qual ação resolve
(abrir a aba certa ou um clique que chama a API real). Nada é simulado.
"""
from __future__ import annotations


def _step(key, label, ok, detail, action=None, optional=False):
    return {"key": key, "label": label, "ok": bool(ok), "detail": detail,
            "action": action, "optional": optional}


def check(runtime, publishing=None, local_ai=None) -> dict:
    steps = []
    bridge = runtime.autoclip_bridge
    engine = bridge.available()
    steps.append(_step("engine", "Motor AutoClip", engine,
                       "Pronto para editar." if engine else
                       "Motor não encontrado. No app Windows ele vem junto; use a versão do GitHub Releases.",
                       {"type": "view", "target": "ajustes", "label": "Ver Ajustes"}))
    ai = local_ai.status() if local_ai is not None else {"model_ready": False, "job": None}
    job = ai.get("job") or {}
    preparing = job.get("state") == "running"
    steps.append(_step("ai", "IA local (Ollama + modelo)", ai.get("model_ready"),
                       "Modelo instalado: " + ", ".join(ai.get("models", [])) if ai.get("model_ready") else
                       (f"Preparando: {job.get('phase', '')}" if preparing else
                        "Falta a IA que escolhe os melhores momentos (grátis, roda no seu PC)."),
                       None if preparing else {"type": "post", "target": "/api/local-ai/prepare",
                                               "body": {"model": ai.get("recommended", "llama3.1:8b")},
                                               "label": "Preparar IA agora"}))
    twitch = runtime.twitch.status()
    yt = runtime.youtube_auto.status()
    connected = bool(twitch.get("configured")) or bool(yt.get("api_key_present"))
    steps.append(_step("source", "Twitch ou YouTube conectado", connected,
                       ("Twitch conectada. " if twitch.get("configured") else "") +
                       ("Chave do YouTube configurada." if yt.get("api_key_present") else "") or
                       "Conecte a Twitch (Client ID/Secret) ou a chave da YouTube Data API.",
                       {"type": "view", "target": "ajustes", "label": "Conectar"}))
    auto = runtime.twitch_auto.status()
    authorized = int(auto.get("authorized_broadcasters", 0)) + int(yt.get("authorized_channels", 0))
    steps.append(_step("authorized", "Canais autorizados", authorized > 0,
                       f"{authorized} canal(is) autorizado(s)." if authorized else
                       "Autorize streamers no Radar viral (bio que libera cortes ou permissão).",
                       {"type": "view", "target": "radar", "label": "Abrir Radar"}))
    download = bool(auto.get("editor_grant_present") or auto.get("public_download") or yt.get("enabled"))
    steps.append(_step("download", "Download automático ligado", download,
                       "Downloads ligados." if download else
                       "Sem acesso de editor e download público desligado: nada é baixado.",
                       {"type": "post", "target": "/api/live/settings", "body": {"public_download": True},
                        "label": "Ligar download"}))
    log = getattr(runtime, "ingest_log", None)
    counts = log.counts() if log is not None else {}
    last_error = auto.get("last_error") or yt.get("last_error")
    steps.append(_step("first_download", "Primeiro vídeo baixado", counts.get("done", 0) > 0,
                       f"{counts.get('done', 0)} download(s) concluído(s)." if counts.get("done") else
                       ("Último erro: " + str(last_error) if last_error else
                        "Ainda nenhum. Clique para verificar agora (clipes virais de autorizados)."),
                       {"type": "post", "target": "/api/ingest/run", "body": {}, "label": "Verificar agora"}))
    clips = runtime.store.all()
    ready = sum(1 for c in clips if c["status"] in {"ready", "approved"})
    editing = bridge.status()
    running = editing.get("running") or editing.get("pending")
    steps.append(_step("cuts", "Cortes prontos para revisar", ready > 0,
                       f"{ready} corte(s) prontos/aprovados." if ready else
                       ("AutoClip editando agora…" if running else
                        "Aparecem aqui depois que o AutoClip editar um vídeo baixado."),
                       {"type": "view", "target": "clipes", "label": "Abrir Clipes"}))
    pub = publishing.status() if publishing is not None else {"platforms": []}
    live_platforms = [p["platform"] for p in pub.get("platforms", []) if p.get("connected")]
    steps.append(_step("publish", "Publicação conectada", bool(live_platforms),
                       "Conectado: " + ", ".join(live_platforms) if live_platforms else
                       "Opcional: conecte YouTube/TikTok para publicar pelo app (ou baixe e poste à mão).",
                       {"type": "view", "target": "publicar", "label": "Abrir Publicar"}, optional=True))
    required = [s for s in steps if not s["optional"]]
    next_step = next((s for s in required if not s["ok"]), None)
    return {"steps": steps, "done": sum(s["ok"] for s in required), "total": len(required),
            "next": next_step["key"] if next_step else None, "working": next_step is None}

"""Automated, authorization-gated Twitch -> AutoClip intake.

Only the official Helix Get Clips Download API supplies media. An app token
for metadata discovery does NOT grant a right to fetch another streamer's clips.
No unverified download URLs, scraping, or hidden fallbacks.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from .twitch_download import DownloadError, download_clip
from .curation import ranked_shortlist
from .ingest_log import record


class TwitchAutoIngest:
    def __init__(self, runtime):
        self.runtime = runtime
        self.lock = threading.RLock()
        self.running = False
        self.next_retry = {}
        self.last_error = None
        self.processed = 0
        self.attempted = 0
        self.last_candidates_scanned = 0
        self.last_quality_passed = 0
        self.trigger = "automatico"  # "manual" quando o proprietário clica em Verificar agora

    def status(self):
        enabled = os.getenv("TWITCH_AUTO_DOWNLOAD", "1") == "1"
        credentials = bool(os.getenv("TWITCH_USER_ACCESS_TOKEN", "").strip()
                           and os.getenv("TWITCH_EDITOR_ID", "").strip().isdigit())
        try:
            allowed = sum(1 for x in self._allowed_sources())
        except (OSError, ValueError, TypeError):
            allowed = 0
        from .public_clip_download import enabled as public_enabled
        public = public_enabled()
        return {
            "enabled": enabled,
            "editor_grant_present": credentials,
            "public_download": public,
            "authorized_broadcasters": allowed,
            "running": self.running,
            "last_error": self.last_error,
            "downloaded": self.processed,
            "attempted": self.attempted,
            "last_candidates_scanned": self.last_candidates_scanned,
            "last_quality_passed": self.last_quality_passed,
            "min_score": self._minimum_score(),
            "ready": enabled and (credentials or public) and bool(allowed)
                     and self.runtime.autoclip_bridge.available(),
        }

    @staticmethod
    def _minimum_score():
        try:
            return max(0, min(100, int(os.getenv("TWITCH_AUTO_MIN_SCORE", "78"))))
        except ValueError:
            return 78

    def _allowed_sources(self):
        """Read rights declaration, not simply a public Twitch clip."""
        path = self.runtime.store.root / "twitch_sources.json"
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 64_000:
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("broadcasters"), list):
            return []
        result = []
        for source in data["broadcasters"][:100]:
            if not isinstance(source, dict):
                continue
            ident = str(source.get("id", ""))
            rights = source.get("rights_status")
            evidence = str(source.get("evidence", "")).strip()
            creator = str(source.get("creator") or source.get("name") or "").strip()
            if (ident.isdigit() and creator and rights in {"owned", "permission_granted"}
                    and (rights == "owned" or len(evidence) >= 8)):
                result.append({
                    "broadcaster_id": ident, "creator": creator,
                    "rights_status": rights, "evidence": evidence,
                })
        return result

    def _gta6_only(self) -> bool:
        """Segue o calendário: só GTA VI a partir da virada; antes, os clipes
        virais do perfil ativo (categorias em alta). 'force' = sempre GTA VI;
        '0' = nunca restringir."""
        value = os.getenv("TWITCH_AUTO_GTA6_ONLY", "1").strip().lower()
        if value == "force":
            return True
        if value == "0":
            return False
        profile = getattr(self.runtime.twitch, "profile", None)
        if profile is None:
            return True
        try:
            return profile()["profile"] == "gta6_only"
        except (ValueError, TypeError, KeyError, RuntimeError):
            return True

    def kick(self):
        if os.getenv("TWITCH_AUTO_DOWNLOAD", "1") != "1":
            return False
        if not self.runtime.autoclip_bridge.available():
            self.last_error = "Motor AutoClip indisponível: instale/configure o modelo de IA."
            return False
        if (hasattr(self.runtime.autoclip_bridge, "model_ready")
                and not self.runtime.autoclip_bridge.model_ready()):
            self.last_error = ("Modelo de IA AutoClip indisponível. "
                               "Configure/inicie Ollama antes de baixar vídeos.")
            return False
        from .public_clip_download import enabled as public_enabled
        if not (os.getenv("TWITCH_USER_ACCESS_TOKEN", "").strip()
                and os.getenv("TWITCH_EDITOR_ID", "").strip().isdigit()) and not public_enabled():
            self.last_error = ("Token OAuth de editor/broadcaster ausente. "
                               "Client ID/Secret permitem apenas pesquisa.")
            return False
        with self.lock:
            if self.running:
                return False
            self.running = True
        threading.Thread(target=self._work, name="twitch-authorized-auto-intake",
                         daemon=True).start()
        return True

    def _work(self):
        try:
            sources = {s["broadcaster_id"]: s for s in self._allowed_sources()}
            if not sources:
                self.last_error = ("Nenhum criador autorizado em twitch_sources.json; "
                                   "pesquisa pública não equivale à autorização.")
                return
            # Eligibility checked against rights allowlist and Twitch's real
            # editor/broadcaster grant. Do not download from arbitrary links.
            items = self.runtime.twitch.list_candidates(limit=1000)
            score_threshold = self._minimum_score()
            per_creator = max(1, min(4, int(os.getenv("TWITCH_AUTO_PER_CREATOR", "2"))))
            learning = getattr(self.runtime, "editorial", None)
            bias = learning.feedback_summary()["creator_bias"] if learning else {}
            gta6_only = self._gta6_only()
            eligible = ranked_shortlist(
                items, min_score=score_threshold, per_creator=per_creator,
                gta6_only=gta6_only, creator_bias=bias)
            self.last_candidates_scanned = len(items)
            self.last_quality_passed = len(eligible)
            # A bounded batch avoids downloading gigabytes on every 15-minute
            # refresh; increase through config.env within this safety ceiling.
            # GTA VI no ar = prioridade máxima: lote no teto de segurança (12),
            # a menos que o config.env peça explicitamente outro valor.
            batch_key = "TWITCH_GTA6_BATCH" if gta6_only else "TWITCH_AUTO_BATCH"
            quota = min(12, max(1, int(os.getenv(batch_key, "12" if gta6_only else "5"))))
            editor = os.getenv("TWITCH_EDITOR_ID", "").strip()
            client_id = self.runtime.twitch.client_id
            from .public_clip_download import download_public_clip, enabled as public_enabled
            public = public_enabled()
            token = ""
            if os.getenv("TWITCH_USER_ACCESS_TOKEN", "").strip() and editor.isdigit():
                from .twitch_oauth import refreshed_token
                try:
                    token = refreshed_token(self.runtime.store.root.parent, client_id,
                                            self.runtime.twitch.secret)
                except (OSError, ValueError, RuntimeError):
                    if not public:
                        raise
                    token = ""
            for candidate in eligible:
                if quota <= 0:
                    break
                clip_id = str(candidate.get("id", ""))
                owner_id = str(candidate.get("broadcaster_id", ""))
                if not clip_id or owner_id not in sources:
                    continue
                filename = self.runtime.store.incoming / ("twitch-" + clip_id + ".mp4")
                if filename.exists() or filename.with_name(filename.name + ".rights.json").exists():
                    continue
                if self.next_retry.get(clip_id, 0) > time.monotonic():
                    continue
                source = sources[owner_id]
                record(self.runtime, "start", "twitch", "clip", owner_id, clip_id,
                       source_name=source.get("creator", ""), title=str(candidate.get("title", "")),
                       trigger=self.trigger)
                try:
                    self.attempted += 1
                    proof = {**source, "duration_sec": 35}
                    # 1º: API oficial (dono/editor). Se a Twitch recusar e o
                    # proprietário ativou TWITCH_PUBLIC_DOWNLOAD=1, baixa o clipe
                    # público via yt-dlp — somente de streamer autorizado.
                    official_error = None
                    if token:
                        try:
                            download_clip(clip_id, owner_id, editor, client_id, token,
                                          proof, self.runtime.store.incoming)
                        except DownloadError as exc:
                            official_error = exc
                    if not token or official_error is not None:
                        if not public:
                            raise official_error or DownloadError(
                                "Sem acesso de editor; ative TWITCH_PUBLIC_DOWNLOAD=1")
                        download_public_clip(clip_id, owner_id, proof,
                                             self.runtime.store.incoming)
                    result = self.runtime.scan()
                    # scan() is the ONLY authority that queues AutoClip.
                    if not result["added"]:
                        self.last_error = "Download recebido, mas mídia rejeitada pela ingestão."
                        record(self.runtime, "finish", "twitch", clip_id, "failed", self.last_error)
                    else:
                        self.processed += 1
                        quota -= 1
                        self.last_error = None
                        record(self.runtime, "finish", "twitch", clip_id, "done")
                except (DownloadError, OSError, ValueError) as exc:
                    self.last_error = str(exc)[:190]
                    self.next_retry[clip_id] = time.monotonic() + 900
                    record(self.runtime, "finish", "twitch", clip_id, "failed", self.last_error)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self.last_error = "Busca automática: " + str(exc)[:150]
        finally:
            with self.lock:
                self.running = False
                self.trigger = "automatico"

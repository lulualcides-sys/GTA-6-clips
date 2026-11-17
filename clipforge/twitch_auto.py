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


class TwitchAutoIngest:
    def __init__(self, runtime):
        self.runtime = runtime
        self.lock = threading.RLock()
        self.running = False
        self.next_retry = {}
        self.last_error = None
        self.processed = 0
        self.attempted = 0

    def status(self):
        enabled = os.getenv("TWITCH_AUTO_DOWNLOAD", "1") == "1"
        credentials = bool(os.getenv("TWITCH_USER_ACCESS_TOKEN", "").strip()
                           and os.getenv("TWITCH_EDITOR_ID", "").strip().isdigit())
        try:
            allowed = sum(1 for x in self._allowed_sources())
        except (OSError, ValueError, TypeError):
            allowed = 0
        return {
            "enabled": enabled,
            "editor_grant_present": credentials,
            "authorized_broadcasters": allowed,
            "running": self.running,
            "last_error": self.last_error,
            "downloaded": self.processed,
            "attempted": self.attempted,
            "ready": enabled and credentials and bool(allowed)
                     and self.runtime.autoclip_bridge.available(),
        }

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
            creator = str(source.get("creator", "")).strip()
            if (ident.isdigit() and creator and rights in {"owned", "permission_granted"}
                    and (rights == "owned" or len(evidence) >= 8)):
                result.append({
                    "broadcaster_id": ident, "creator": creator,
                    "rights_status": rights, "evidence": evidence,
                })
        return result

    def kick(self):
        if os.getenv("TWITCH_AUTO_DOWNLOAD", "1") != "1":
            return False
        if not self.runtime.autoclip_bridge.available():
            self.last_error = "Motor AutoClip indisponível: instale/configure o modelo de IA."
            return False
        if not (os.getenv("TWITCH_USER_ACCESS_TOKEN", "").strip()
                and os.getenv("TWITCH_EDITOR_ID", "").strip().isdigit()):
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
            items = self.runtime.twitch.list_candidates()
            quota = min(3, max(1, int(os.getenv("TWITCH_AUTO_BATCH", "2"))))
            editor = os.getenv("TWITCH_EDITOR_ID", "").strip()
            from .twitch_oauth import refreshed_token
            client_id = self.runtime.twitch.client_id
            token = refreshed_token(self.runtime.store.root.parent, client_id,
                                    self.runtime.twitch.secret)
            for candidate in items:
                if self.processed >= 10_000:  # long-lived session hard cap
                    return
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
                try:
                    self.attempted += 1
                    source = sources[owner_id]
                    proof = {**source, "duration_sec": 35}
                    download_clip(clip_id, owner_id, editor, client_id, token,
                                  proof, self.runtime.store.incoming)
                    result = self.runtime.scan()
                    # scan() is the ONLY authority that queues AutoClip.
                    if not result["added"]:
                        self.last_error = "Download recebido, mas mídia rejeitada pela ingestão."
                    else:
                        self.processed += 1
                        quota -= 1
                        self.last_error = None
                except (DownloadError, OSError, ValueError) as exc:
                    self.last_error = str(exc)[:190]
                    self.next_retry[clip_id] = time.monotonic() + 900
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self.last_error = "Busca automática: " + str(exc)[:150]
        finally:
            with self.lock:
                self.running = False

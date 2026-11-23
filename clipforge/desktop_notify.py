"""Notificações nativas do Windows (toast) para falhas novas — grátis, sem instalar nada.

Usa a API WinRT ToastNotificationManager via PowerShell que já vem no Windows
10/11. O texto vai por variáveis de ambiente (nunca concatenado no comando).
A primeira leitura só marca o que já existia, para não disparar avisos antigos.
Desligue com NEXUS_WINDOWS_NOTIFY=0.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

_SCRIPT = (
    "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
    "$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
    "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
    "$n = $t.GetElementsByTagName('text');"
    "$n.Item(0).AppendChild($t.CreateTextNode($env:NEXUS_TOAST_TITLE)) | Out-Null;"
    "$n.Item(1).AppendChild($t.CreateTextNode($env:NEXUS_TOAST_BODY)) | Out-Null;"
    "$id = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe';"
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($id).Show("
    "[Windows.UI.Notifications.ToastNotification]::new($t))"
)

AREAS = {"download": "Download falhou", "autoclip": "AutoClip falhou", "publicacao": "Publicação falhou",
         "automacao": "Automação com problema"}


def _key(item: dict) -> str:
    return "|".join(str(item.get(k, "")) for k in ("area", "platform", "title", "message", "at"))


class WindowsNotifier:
    def __init__(self, runtime, *, run=subprocess.run, collect=None, platform=None):
        self.runtime = runtime
        self._run = run
        if collect is None:
            from .notifications import collect
        self._collect = collect
        self.platform = platform or sys.platform
        self.seen: set[str] | None = None
        self.sent = 0

    def enabled(self) -> bool:
        return self.platform == "win32" and os.getenv("NEXUS_WINDOWS_NOTIFY", "1") == "1"

    def toast(self, title: str, body: str) -> bool:
        env = {**os.environ, "NEXUS_TOAST_TITLE": " ".join(str(title).split())[:80],
               "NEXUS_TOAST_BODY": " ".join(str(body).split())[:220]}
        try:
            result = self._run(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                                "-Command", _SCRIPT], env=env, stdin=subprocess.DEVNULL,
                               capture_output=True, timeout=20, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def tick(self) -> int:
        """Uma rodada: avisa só falhas que não existiam na rodada anterior (máx. 3)."""
        if not self.enabled():
            return 0
        items = self._collect(self.runtime, getattr(self.runtime, "publishing", None))["items"]
        keys = {_key(i) for i in items}
        if self.seen is None:
            self.seen = keys
            return 0
        new = [i for i in items if _key(i) not in self.seen]
        self.seen |= keys
        count = 0
        for item in new[:3]:
            mode = "automático" if item.get("automatic") else "manual"
            title = f"Nexus Clips · {AREAS.get(item.get('area'), 'Falha')} ({mode})"
            if self.toast(title, f"{item.get('title', '')}: {item.get('message', '')}"):
                count += 1
        if len(new) > 3:
            self.toast("Nexus Clips", f"Mais {len(new) - 3} falha(s). Veja a aba Atividade.")
        self.sent += count
        return count

    def start(self, seconds: int = 60) -> None:
        if not self.enabled():
            return

        def loop():
            while True:
                try:
                    self.tick()
                except Exception:  # noqa: BLE001 - aviso nunca derruba o app
                    pass
                time.sleep(seconds)
        threading.Thread(target=loop, name="windows-notifier", daemon=True).start()

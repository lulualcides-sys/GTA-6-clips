"""Assistente de IA local do AutoClip: Ollama oficial + modelo, dentro do app.

O motor AutoClip já vai empacotado no Windows; o que faltava para editar era o
modelo de linguagem. Este módulo instala o Ollama oficial (instalador assinado,
assinatura Authenticode conferida antes de executar), inicia o serviço local
em 127.0.0.1 e baixa um modelo de uma lista fechada pela API oficial do Ollama.

Nada roda sem clique do proprietário. Nenhum segredo é usado ou armazenado.
Pesos de modelo NUNCA vão para o ZIP do aplicativo nem para o GitHub.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

OLLAMA_API = "http://127.0.0.1:11434"
OLLAMA_INSTALLER_URL = "https://ollama.com/download/OllamaSetup.exe"
MAX_INSTALLER_BYTES = 3 * 1024 ** 3
# Lista fechada: o painel não aceita nomes arbitrários de modelos.
MODEL_CATALOG = {
    "llama3.1:8b": {"label": "Llama 3.1 8B (recomendado)", "size_gb": 4.9},
    "llama3.2:3b": {"label": "Llama 3.2 3B (PC mais fraco, qualidade menor)", "size_gb": 2.0},
}
RECOMMENDED_MODEL = "llama3.1:8b"


class LocalAI:
    def __init__(self, home: Path, *, opener=urlopen, popen=subprocess.Popen,
                 run=subprocess.run, platform: str | None = None,
                 sleep=time.sleep, disk_usage=shutil.disk_usage):
        self.home = Path(home)
        self.downloads = self.home / "extensions" / "local-ai"
        self._open = opener
        self._popen = popen
        self._run = run
        self._sleep = sleep
        self._disk_usage = disk_usage
        self.platform = platform or sys.platform
        self.lock = threading.RLock()
        self.job: dict | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ status
    def ollama_path(self) -> str | None:
        found = shutil.which("ollama")
        if found:
            return found
        if self.platform == "win32":
            base = os.getenv("LOCALAPPDATA", "")
            candidate = Path(base) / "Programs" / "Ollama" / "ollama.exe" if base else None
            if candidate and candidate.is_file():
                return str(candidate)
        return None

    def models(self) -> list[str] | None:
        """Modelos instalados, ou None quando o serviço não responde."""
        try:
            with self._open(f"{OLLAMA_API}/api/tags", timeout=2) as response:
                body = json.loads(response.read(500_000))
        except (OSError, ValueError, TypeError):
            return None
        if not isinstance(body, dict):
            return None
        return [str(x.get("name")) for x in body.get("models", [])
                if isinstance(x, dict) and x.get("name")]

    def status(self) -> dict:
        models = self.models()
        with self.lock:
            job = dict(self.job) if self.job else None
        installed = models is not None or bool(self.ollama_path())
        return {
            "can_install": self.platform == "win32",
            "ollama_installed": installed,
            "ollama_running": models is not None,
            "models": models or [],
            "model_ready": bool(models),
            "recommended": RECOMMENDED_MODEL,
            "catalog": [{"name": k, **v} for k, v in MODEL_CATALOG.items()],
            "job": job,
        }

    # -------------------------------------------------------------- job state
    def _set(self, **changes):
        with self.lock:
            if self.job is not None:
                self.job.update(changes)

    def busy(self) -> bool:
        with self.lock:
            return bool(self.job and self.job.get("state") == "running")

    def prepare(self, model: str = RECOMMENDED_MODEL) -> dict:
        """Um clique: instala Ollama (se faltar), inicia e baixa o modelo."""
        if model not in MODEL_CATALOG:
            raise ValueError("Modelo fora da lista permitida.")
        with self.lock:
            if self.busy():
                raise ValueError("Preparação da IA já está em andamento.")
            if self.models() is None and not self.ollama_path() and self.platform != "win32":
                raise ValueError("Instale o Ollama (ollama.com/download) neste sistema; "
                                 "a instalação automática existe somente no Windows.")
            self.job = {"state": "running", "phase": "Verificando", "model": model,
                        "progress": 0.0, "error": "", "started_at": time.time()}
            self._thread = threading.Thread(target=self._prepare, args=(model,),
                                            daemon=True, name="nexus-local-ai")
            self._thread.start()
            return dict(self.job)

    def _prepare(self, model: str):
        try:
            if self.models() is None:
                if not self.ollama_path():
                    self._install_ollama()
                self._start_ollama()
            installed = self.models() or []
            if model not in installed:
                self._pull(model)
            if model not in (self.models() or []):
                raise RuntimeError("Ollama não listou o modelo após o download.")
            self._set(state="done", phase="IA local pronta", progress=1.0)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            self._set(state="failed", phase="Falhou", error=str(exc)[:240])

    # ---------------------------------------------------------- install/start
    def _install_ollama(self):
        if self.platform != "win32":
            raise RuntimeError("Instalação automática do Ollama existe somente no Windows.")
        self.downloads.mkdir(parents=True, exist_ok=True)
        target = self.downloads / "OllamaSetup.exe"
        partial = target.with_suffix(".partial")
        self._set(phase="Baixando instalador oficial do Ollama", progress=0.0)
        try:
            request = Request(OLLAMA_INSTALLER_URL, headers={"User-Agent": "NexusClips"})
            with self._open(request, timeout=60) as response:
                final_url = getattr(response, "geturl", lambda: OLLAMA_INSTALLER_URL)()
                if not str(final_url).startswith("https://"):
                    raise RuntimeError("Download do Ollama redirecionado para HTTP inseguro.")
                total = int(response.headers.get("Content-Length") or 0)
                if total > MAX_INSTALLER_BYTES:
                    raise RuntimeError("Instalador do Ollama maior que o limite.")
                done = 0
                with partial.open("wb") as stream:
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        done += len(block)
                        if done > MAX_INSTALLER_BYTES:
                            raise RuntimeError("Instalador do Ollama maior que o limite.")
                        stream.write(block)
                        if total:
                            self._set(progress=round(done / total, 3))
            if done < 1_000_000:
                raise RuntimeError("Instalador do Ollama incompleto.")
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)
        self._set(phase="Conferindo assinatura digital do instalador", progress=0.0)
        self._verify_signature(target)
        self._set(phase="Instalando Ollama (pode levar alguns minutos)")
        result = self._run([str(target), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                           stdin=subprocess.DEVNULL, capture_output=True,
                           timeout=1200, check=False)
        target.unlink(missing_ok=True)
        if result.returncode != 0:
            raise RuntimeError(f"Instalador do Ollama terminou com código {result.returncode}.")
        if not self.ollama_path():
            raise RuntimeError("Ollama instalado, mas ollama.exe não foi encontrado.")

    def _verify_signature(self, path: Path):
        """Executa somente instalador com assinatura Authenticode válida da Ollama."""
        script = ("$s=Get-AuthenticodeSignature -LiteralPath $env:NEXUS_VERIFY_PATH;"
                  "Write-Output $s.Status.ToString();"
                  "Write-Output $s.SignerCertificate.Subject")
        result = self._run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                           env={**os.environ, "NEXUS_VERIFY_PATH": str(path)},
                           stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=60, check=False)
        lines = [x.strip() for x in (result.stdout or "").splitlines() if x.strip()]
        subject = lines[1] if len(lines) > 1 else ""
        cn = next((p.split("=", 1)[1] for p in subject.split(",")
                   if p.strip().upper().startswith(("CN=", "O="))), "")
        if result.returncode != 0 or not lines or lines[0] != "Valid" or "ollama" not in cn.lower():
            path.unlink(missing_ok=True)
            raise RuntimeError("Assinatura digital do instalador do Ollama inválida; instalação bloqueada.")

    def _start_ollama(self):
        if self.models() is not None:
            return
        binary = self.ollama_path()
        if not binary:
            raise RuntimeError("Ollama não encontrado.")
        self._set(phase="Iniciando serviço local do Ollama")
        flags = 0
        if self.platform == "win32":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        env = {**os.environ, "OLLAMA_HOST": "127.0.0.1:11434"}
        self._popen([binary, "serve"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, env=env, creationflags=flags)
        for _ in range(30):
            if self.models() is not None:
                return
            self._sleep(1)
        raise RuntimeError("Ollama não respondeu em 127.0.0.1:11434 após iniciar.")

    def ensure_running(self) -> bool:
        """Usado pelo AutoClip: inicia o Ollama já instalado, sem instalar nada."""
        if self.models() is not None:
            return True
        if not self.ollama_path():
            return False
        try:
            self._start_ollama()
            return True
        except (OSError, RuntimeError, subprocess.SubprocessError):
            return False

    # ------------------------------------------------------------------- pull
    def _pull(self, model: str):
        needed = MODEL_CATALOG[model]["size_gb"] + 1.0
        try:
            free = self._disk_usage(str(Path.home())).free / 1024 ** 3
        except OSError:
            free = needed
        if free < needed:
            raise RuntimeError(f"Espaço insuficiente: são necessários ~{needed:.0f} GB livres.")
        self._set(phase=f"Baixando modelo {model} (~{MODEL_CATALOG[model]['size_gb']} GB)", progress=0.0)
        request = Request(f"{OLLAMA_API}/api/pull", method="POST",
                          data=json.dumps({"model": model, "stream": True}).encode(),
                          headers={"Content-Type": "application/json"})
        success = False
        with self._open(request, timeout=300) as response:
            for raw in response:
                line = raw.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get("error"):
                    raise RuntimeError("Ollama: " + str(event["error"])[:180])
                total, completed = event.get("total"), event.get("completed")
                if isinstance(total, int) and total > 0 and isinstance(completed, int):
                    self._set(progress=round(min(completed / total, 1.0), 3))
                if event.get("status") == "success":
                    success = True
        if not success:
            raise RuntimeError("Download do modelo interrompido; tente novamente.")

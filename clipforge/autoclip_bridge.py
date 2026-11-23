"""Ponte AutoClip isolada: sugestão de cortes autorizados, nunca aprovação.

O AutoClip roda em processo local opcional. Resultados permanecem isolados e
podem ser assistidos no Nexus, sem alterar o original ou publicar automaticamente.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from urllib.request import urlopen


class AutoClipBridge:
    def __init__(self, store):
        self.store = store
        self.home = store.root / "extensions" / "autoclip"
        self.exports = self.home / "exports"
        self.state_file = self.home / "nexus-jobs.json"
        self.lock = threading.RLock()
        self.jobs = self._load()
        self.active = None
        self.max_pending = 25
        self.on_import = None
        self.local_ai = None  # LocalAI opcional: inicia Ollama já instalado.

    def _load(self):
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {}
            for job in data.values():
                if job.get("status") in ("running", "queued"):
                    job["status"] = "interrupted"
            return data
        except (ValueError, OSError, TypeError, AttributeError):
            return {}

    def _save(self):
        self.home.mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.jobs, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.state_file)

    def _bundled_runtime(self):
        # AutoClip Python 3.12 sidecar, isolated from PyInstaller's Python.
        if not getattr(sys, "frozen", False):
            return None
        folder = Path(sys.executable).resolve().parent / "autoclip_runtime"
        python, runner = folder / "python.exe", folder / "nexus_autoclip_runner.py"
        return [str(python), str(runner)] if python.is_file() and runner.is_file() else None

    def _command(self):
        bundled = self._bundled_runtime()
        if bundled:
            return bundled
        configured = os.getenv("AUTOCLIP_BINARY", "autoclip").strip() or "autoclip"
        external = shutil.which(configured)
        return [external] if external else None

    def custom_captions_supported(self) -> bool:
        """Só o runner empacotado registra a legenda personalizada (nexus_custom)."""
        bundled = self._bundled_runtime()
        if not bundled:
            return False
        try:
            return "NEXUS_CAPTION_STYLE" in Path(bundled[1]).read_text(encoding="utf-8")
        except OSError:
            return False

    def binary(self):
        command = self._command()
        return command[0] if command else None

    def _enabled(self):
        return os.getenv("AUTOCLIP_ENABLED", "1" if self._bundled_runtime() else "0") == "1"

    def available(self):
        return self._enabled() and bool(self._command())

    def status(self):
        with self.lock:
            return {
                "enabled": self._enabled(),
                "installed": bool(self._command()),
                "bundled": bool(self._bundled_runtime()),
                "running": self.active is not None,
                "pending": sum(x.get("status") == "queued" for x in self.jobs.values()),
                "auto_review": os.getenv("AUTOCLIP_AUTO_IMPORT", "1") == "1",
                "jobs": {key: dict(value) for key, value in self.jobs.items()}
            }

    def _source(self, clip_id):
        clip = self.store.get(clip_id)
        if not clip:
            raise ValueError("Clipe não encontrado.")
        if clip["rights_status"] not in {"owned", "permission_granted"}:
            raise PermissionError("Fonte sem direitos de edição e publicação registrados.")
        if clip["rights_status"] == "permission_granted" and len((clip.get("evidence") or "").strip()) < 8:
            raise PermissionError("Fonte sem evidência de permissão.")
        source = Path(clip["input_path"])
        if (source.is_symlink() or not source.is_file() or
                source.resolve().parent != self.store.incoming.resolve()):
            raise ValueError("Fonte fora da pasta autorizada.")
        sha = hashlib.sha256()
        with source.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                sha.update(block)
        if sha.hexdigest() != clip["sha256"]:
            raise ValueError("Fonte mudou após conferência; não usar AutoClip.")
        return source

    def model_ready(self):
        """Avoid expensive downloads while the local editing model is absent."""
        if not self.available():
            return False
        try:
            self._prepare_local_ai()
            return True
        except (RuntimeError, OSError, ValueError, TypeError):
            return False

    def queue(self, clip_id):
        if not self.available():
            raise ValueError("AutoClip desativado, não instalado ou Python 3.12 indisponível.")
        self._source(clip_id)
        with self.lock:
            prior = self.jobs.get(clip_id, {})
            if prior.get("status") in {"queued", "running", "complete"}:
                raise ValueError("Fonte já está na fila AutoClip ou possui resultados.")
            if sum(x.get("status") == "queued" for x in self.jobs.values()) >= self.max_pending:
                raise ValueError("Fila AutoClip cheia; aguardando conclusão.")
            self.jobs[clip_id] = {"status": "queued", "suggestions": [], "imports": []}
            self._save()
            self._start_next_locked()
        return {"status": "queued", "clip_id": clip_id}

    def _start_next_locked(self):
        if self.active is not None:
            return
        for clip_id, entry in self.jobs.items():
            if entry.get("status") != "queued":
                continue
            self.active = clip_id
            worker = threading.Thread(target=self._run, args=(clip_id,),
                                      daemon=True, name="nexus-autoclip")
            worker.start()
            break

    def _prepare_local_ai(self):
        """Use Ollama installed on this PC; never pretend an AI model is bundled."""
        provider = os.getenv("AUTOCLIP_PROVIDER", "ollama" if self._bundled_runtime() else "").strip()
        if provider != "ollama":
            return []
        if self.local_ai is not None:
            self.local_ai.ensure_running()
        try:
            with urlopen("http://127.0.0.1:11434/api/tags", timeout=4) as response:
                body = json.loads(response.read(200_000))
            models = [str(x.get("name", "")) for x in body.get("models", [])
                      if isinstance(x, dict) and x.get("name")]
        except (OSError, ValueError, TypeError) as exc:
            raise RuntimeError("IA local indisponível. Use 'Preparar IA do AutoClip' no painel.") from exc
        preferred = os.getenv("AUTOCLIP_OLLAMA_MODEL", "").strip()
        if preferred and preferred not in models:
            raise RuntimeError("Modelo Ollama configurado não está instalado.")
        if not models:
            raise RuntimeError("Nenhum modelo de IA instalado. Use 'Preparar IA do AutoClip' no painel.")
        selected = preferred or next((v for v in ("llama3.1:8b", "qwen2.5:14b",
                            "mistral-nemo:12b", "gemma2:9b", "llama3.2:3b") if v in models), models[0])
        self.home.mkdir(parents=True, exist_ok=True)
        conf = self.home / "config.json"
        try:
            data = json.loads(conf.read_text(encoding="utf-8")) if conf.is_file() else {}
        except (OSError, ValueError, TypeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        providers = data.setdefault("providers", {})
        if not isinstance(providers, dict):
            providers = data["providers"] = {}
        setting = providers.setdefault("ollama", {})
        if not isinstance(setting, dict):
            setting = providers["ollama"] = {}
        # Respect an explicitly configured model on disk if no override.
        current = str(setting.get("model", ""))
        setting["model"] = preferred or (current if current in models else selected)
        setting.setdefault("base_url", "http://127.0.0.1:11434")
        data["active_provider"] = "ollama"
        tmp = conf.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(conf)
        return ["--provider", "ollama"]

    @staticmethod
    def _timeout_for(source: Path) -> int:
        """30 min para clipes curtos; vídeos longos do YouTube ganham 2x a duração (até 3 h).

        A duração vem do manifesto gravado no download (sem rodar ffprobe aqui).
        """
        override = os.getenv("AUTOCLIP_TIMEOUT_SECONDS", "").strip()
        if override.isdigit():
            return max(600, min(10800, int(override)))
        seconds = 0.0
        sidecar = Path(str(source) + ".rights.json")
        try:
            if sidecar.is_file() and not sidecar.is_symlink() and sidecar.stat().st_size < 1_000_000:
                seconds = float(json.loads(sidecar.read_text(encoding="utf-8")).get("source_duration_sec") or 0)
        except (OSError, ValueError, TypeError, AttributeError):
            seconds = 0.0
        return int(max(1800, min(10800, seconds * 2)))

    def _run(self, clip_id):
        try:
            source = str(self._source(clip_id))
            timeout = self._timeout_for(Path(source))
            provider_options = self._prepare_local_ai()
            self.exports.mkdir(parents=True, exist_ok=True)
            before = {p.name for p in self.exports.iterdir() if p.is_dir() and not p.is_symlink()}
            with self.lock:
                self.jobs[clip_id]["status"] = "running"
                self._save()
            from . import autoclip_settings
            settings = autoclip_settings.load(self.store.root)
            options, extra_env = autoclip_settings.cli_args(settings, self.custom_captions_supported())
            env = {**os.environ, "AUTOCLIP_HOME": str(self.home), **extra_env}
            result = subprocess.run(
                [*self._command(), "clip", source, *options, *provider_options],
                env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, errors="replace",
                timeout=timeout, check=False
            )
            if result.returncode != 0:
                raise RuntimeError("CLI retornou código de erro; verificar AutoClip local.")
            after = [p for p in self.exports.iterdir()
                     if p.is_dir() and not p.is_symlink() and p.name not in before]
            suggestions = []
            for directory in sorted(after):
                for file in sorted(directory.glob("*.mp4")):
                    if file.is_file() and not file.is_symlink() and len(suggestions) < settings["max_clips"]:
                        suggestions.append(str(file.relative_to(self.exports)))
            if not suggestions:
                raise RuntimeError("AutoClip finalizou sem novos MP4s na pasta de exportação.")
            with self.lock:
                self.jobs[clip_id] = {"status": "complete", "suggestions": suggestions,
                                      "imports": [], "import_errors": []}
                self._save()
            # Only actual AutoClip outputs are checked and promoted to REVIEW;
            # never approve/publish before the user's editorial decision.
            if os.getenv("AUTOCLIP_AUTO_IMPORT", "1") == "1":
                for index in range(len(suggestions)):
                    try:
                        imported = self.import_suggestion(clip_id, index)
                        if self.on_import is not None and imported.get("status") == "ready":
                            try:
                                self.on_import(imported["clip_id"])
                            except (ValueError, OSError, RuntimeError):
                                pass  # A análise opcional nunca altera o MP4 AutoClip.
                        with self.lock:
                            self.jobs[clip_id]["imports"].append(imported["clip_id"])
                            self._save()
                    except (ValueError, PermissionError, OSError, subprocess.SubprocessError) as exc:
                        with self.lock:
                            self.jobs[clip_id]["import_errors"].append(str(exc)[:180])
                            self._save()
        except (OSError, subprocess.SubprocessError, RuntimeError, ValueError, PermissionError) as exc:
            with self.lock:
                self.jobs[clip_id] = {"status": "failed", "suggestions": [],
                                      "finished_at": __import__("datetime").datetime.now(
                                          __import__("datetime").timezone.utc).isoformat(timespec="seconds"),
                                      "error": str(exc)[:180]}
                self._save()
        finally:
            with self.lock:
                self.active = None
                self._start_next_locked()

    def import_suggestion(self, clip_id, index):
        """Copia proposta para ingestão normal e exige nova revisão Nexus."""
        candidate = self.preview(clip_id, index)
        self._source(clip_id)  # Revalida SHA/direitos da mídia de origem.
        original = self.store.get(clip_id)
        from .core import duration_of, probe
        seconds = duration_of(probe(candidate))
        if not 10 <= seconds <= 60:
            raise ValueError("Sugestão AutoClip precisa ter entre 10 e 60 segundos.")
        digest = hashlib.sha256()
        with candidate.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        basename = f"autoclip-{clip_id}-{index}-{digest.hexdigest()[:12]}.mp4"
        target = self.store.incoming / basename
        sidecar = self.store.incoming / (basename + ".rights.json")
        from .publishing import media_digest
        with self.store.lock:
            if target.exists():
                if target.is_symlink() or media_digest(target) != digest.hexdigest():
                    raise ValueError("Arquivo de importação já existe com outro conteúdo.")
            else:
                temporary = target.with_suffix(".mp4.partial")
                try:
                    shutil.copyfile(candidate, temporary)
                    temporary.replace(target)
                finally:
                    temporary.unlink(missing_ok=True)
            manifest = {
                "creator": original["creator"],
                "source_url": original.get("source_url") or "",
                "rights_status": original["rights_status"],
                "evidence": original.get("evidence") or "",
                "start_sec": 0,
                "duration_sec": min(60, round(seconds, 2)),
                "derived_from": clip_id,
                "review_required": True
            }
            if not sidecar.exists():
                sidecar.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            imported = self.store.ingest(sidecar)
            freshly_imported = imported is not None
            if not imported:
                for item in self.store.all():
                    if item.get("sha256") == digest.hexdigest():
                        imported = item
                        break
            if not imported:
                raise ValueError("Arquivo já existe sem identificação válida.")
            # Não existe segundo render: o MP4 criado pelo AutoClip vira a
            # versão revisável diretamente. FFmpeg só verifica a decodificação.
            if getattr(self.store, "output", None) is not None and imported["status"] not in {"approved", "ready"}:
                self._promote_autoclip_result(imported["id"], target, digest.hexdigest(), Path(original["input_path"]))
            updated = self.store.get(imported["id"])
            return {"clip_id": imported["id"], "status": updated["status"] if updated else imported["status"],
                    "created": freshly_imported}

    def _promote_autoclip_result(self, clip_id, source: Path, expected_sha: str, original_source: Path):
        """QA de vídeo real e cópia sem qualquer edição pelo pipeline Nexus."""
        from .core import duration_of, probe
        import subprocess
        item = self.store.get(clip_id)
        if not item or item["sha256"] != expected_sha:
            raise ValueError("Hash da sugestão AutoClip divergente.")
        info = probe(source)
        seconds = duration_of(info)
        video = next((v for v in info.get("streams", []) if v.get("codec_type") == "video"), None)
        if not video:
            raise ValueError("Resultado AutoClip sem trilha de vídeo.")
        width, height = int(video.get("width", 0)), int(video.get("height", 0))
        if width < 360 or height < 640 or abs(width / height - 9 / 16) > 0.035:
            raise ValueError("Resultado AutoClip não está em vídeo vertical 9:16.")
        if not 10 <= seconds <= 60:
            raise ValueError("Duração AutoClip fora do intervalo 10–60 s.")
        source_has_audio = any(v.get("codec_type") == "audio" for v in
                               probe(original_source).get("streams", []))
        result_has_audio = any(v.get("codec_type") == "audio" for v in info.get("streams", []))
        if source_has_audio and not result_has_audio:
            raise ValueError("AutoClip removeu o áudio da fonte.")
        # Este comando apenas decodifica e descarta quadros; não produz vídeo.
        subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(source),
                        "-f", "null", "-"], capture_output=True, check=True, timeout=300)
        destination = self.store.output / f"{clip_id}-autoclip-{expected_sha[:12]}.mp4"
        temp = destination.with_suffix(".mp4.partial")
        try:
            if destination.exists():
                if destination.is_symlink() or hashlib.sha256(destination.read_bytes()).hexdigest() != expected_sha:
                    raise ValueError("Saída AutoClip preexistente tem conteúdo inesperado.")
            else:
                shutil.copyfile(source, temp)
                if hashlib.sha256(temp.read_bytes()).hexdigest() != expected_sha:
                    raise ValueError("Cópia AutoClip falhou verificação de hash.")
                temp.replace(destination)
            self.store.save_analysis(clip_id, analysis={
                "engine": "autoclip", "source_sha256": expected_sha,
                "method": "autoclip-export-no-nexus-render"
            }, qa={
                "engine": "autoclip", "width": width, "height": height,
                "duration_sec": seconds, "audio_preserved": result_has_audio,
                "full_decode": True, "editorial_approval": False
            })
            self.store.update(clip_id, status="ready", output_path=str(destination.resolve()))
        finally:
            temp.unlink(missing_ok=True)

    def preview(self, clip_id, index):
        with self.lock:
            entry = self.jobs.get(clip_id, {})
            if entry.get("status") != "complete":
                raise ValueError("AutoClip não possui sugestão pronta.")
            suggestions = entry.get("suggestions", [])
            if not isinstance(index, int) or not 0 <= index < len(suggestions):
                raise ValueError("Sugestão inexistente.")
            relative = Path(suggestions[index])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Caminho AutoClip inválido.")
            file = self.exports / relative
        if (file.is_symlink() or not file.is_file() or
                not file.resolve().is_relative_to(self.exports.resolve())):
            raise ValueError("Sugestão não encontrada.")
        return file

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
import threading
from pathlib import Path


class AutoClipBridge:
    def __init__(self, store):
        self.store = store
        self.home = store.root / "extensions" / "autoclip"
        self.exports = self.home / "exports"
        self.state_file = self.home / "nexus-jobs.json"
        self.lock = threading.RLock()
        self.jobs = self._load()
        self.active = None

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

    def binary(self):
        configured = os.getenv("AUTOCLIP_BINARY", "autoclip").strip() or "autoclip"
        return shutil.which(configured)

    def available(self):
        return os.getenv("AUTOCLIP_ENABLED", "0") == "1" and bool(self.binary())

    def status(self):
        with self.lock:
            return {
                "enabled": os.getenv("AUTOCLIP_ENABLED", "0") == "1",
                "installed": bool(self.binary()),
                "running": self.active is not None,
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

    def queue(self, clip_id):
        if not self.available():
            raise ValueError("AutoClip desativado ou CLI não instalada no servidor.")
        source = self._source(clip_id)
        with self.lock:
            if self.active is not None:
                raise ValueError("AutoClip já está processando outro clipe.")
            self.active = clip_id
            self.jobs[clip_id] = {"status": "queued", "suggestions": []}
            self._save()
            worker = threading.Thread(target=self._run, args=(clip_id, str(source)),
                                      daemon=True, name="nexus-autoclip")
            worker.start()
        return {"status": "queued", "clip_id": clip_id}

    def _run(self, clip_id, source):
        try:
            self.exports.mkdir(parents=True, exist_ok=True)
            before = {p.name for p in self.exports.iterdir() if p.is_dir() and not p.is_symlink()}
            with self.lock:
                self.jobs[clip_id]["status"] = "running"
                self._save()
            env = {**os.environ, "AUTOCLIP_HOME": str(self.home)}
            result = subprocess.run(
                [self.binary(), "clip", source, "--max-clips", "3",
                 "--ratio", "9:16", "--style", "boxed"],
                env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, errors="replace",
                timeout=1800, check=False
            )
            if result.returncode != 0:
                raise RuntimeError("CLI retornou código de erro; verificar AutoClip local.")
            after = [p for p in self.exports.iterdir()
                     if p.is_dir() and not p.is_symlink() and p.name not in before]
            suggestions = []
            for directory in sorted(after):
                for file in sorted(directory.glob("*.mp4")):
                    if file.is_file() and not file.is_symlink() and len(suggestions) < 3:
                        suggestions.append(str(file.relative_to(self.exports)))
            if not suggestions:
                raise RuntimeError("AutoClip finalizou sem novos MP4s na pasta de exportação.")
            with self.lock:
                self.jobs[clip_id] = {"status": "complete", "suggestions": suggestions}
                self._save()
        except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as exc:
            with self.lock:
                self.jobs[clip_id] = {"status": "failed", "suggestions": [],
                                      "error": str(exc)[:180]}
                self._save()
        finally:
            with self.lock:
                self.active = None

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

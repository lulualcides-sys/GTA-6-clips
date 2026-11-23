"""Exportação de cortes prontos: formato, resolução, qualidade, trecho e metadados.

O MP4 gerado pelo AutoClip nunca é alterado: cada exportação é uma CÓPIA nova em
data/exports, com um .json ao lado registrando origem, autoria e as opções.

Metadados são legítimos e servem para organizar e identificar o arquivo
(título, criador, link de origem, direitos). Não existe opção para apagar a
origem nem para disfarçar o vídeo de detectores de conteúdo duplicado.

Sem trecho, sem mudança de resolução e qualidade "original" em MP4/MOV, a cópia
é feita sem reencodar (stream copy): zero perda de qualidade.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .core import duration_of, probe

FORMATS = {"mp4": ("libx264", "aac"), "mov": ("libx264", "aac"), "webm": ("libvpx-vp9", "libopus")}
RESOLUTIONS = {"original": None, "1080x1920": (1080, 1920), "720x1280": (720, 1280),
               "540x960": (540, 960)}
QUALITY = {"original": 18, "alta": 18, "media": 23, "leve": 28}  # CRF x264 / VP9 aproximado
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,150}")


def _clean(text: str, limit: int = 200) -> str:
    return " ".join(str(text or "").replace("\x00", "").split())[:limit]


def build_metadata(clip: dict, title: str) -> dict:
    """Metadados de organização; a origem e a autoria são sempre preservadas."""
    creator = _clean(clip.get("creator"), 120)
    source = _clean(clip.get("source_url"), 300)
    rights = _clean(clip.get("rights_status"), 40)
    comment = " | ".join(x for x in (
        f"Criador: {creator}" if creator else "",
        f"Origem: {source}" if source else "",
        f"Direitos: {rights}" if rights else "",
        "Corte editado pelo AutoClip; exportado pelo Nexus Clips BR") if x)
    return {"title": _clean(title, 120) or _clean(clip.get("filename"), 120),
            "artist": creator, "comment": comment, "copyright": f"Conteúdo original: {creator}" if creator else "",
            "description": comment, "encoded_by": "Nexus Clips BR",
            "creation_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def validate_options(options: dict, duration: float) -> dict:
    if not isinstance(options, dict):
        raise ValueError("Opções de exportação inválidas")
    unknown = set(options) - {"format", "resolution", "quality", "start", "end", "title"}
    if unknown:
        raise ValueError("Campo desconhecido: " + ", ".join(sorted(unknown)))
    fmt = options.get("format", "mp4")
    res = options.get("resolution", "original")
    quality = options.get("quality", "original")
    if fmt not in FORMATS or res not in RESOLUTIONS or quality not in QUALITY:
        raise ValueError("Formato, resolução ou qualidade inválidos")
    try:
        start = float(options.get("start") or 0)
        end = float(options.get("end") or duration)
    except (TypeError, ValueError) as exc:
        raise ValueError("Início/fim devem ser números em segundos") from exc
    end = min(end, duration)
    if start < 0 or end - start < 1:
        raise ValueError("O trecho precisa ter pelo menos 1 segundo dentro do vídeo")
    return {"format": fmt, "resolution": res, "quality": quality, "start": round(start, 3),
            "end": round(end, 3), "title": _clean(options.get("title"), 120),
            "trimmed": start > 0.05 or end < duration - 0.05}


def ffmpeg_command(src: Path, dst: Path, opts: dict, metadata: dict) -> list[str]:
    lossless = (opts["format"] in {"mp4", "mov"} and opts["resolution"] == "original"
                and opts["quality"] == "original" and not opts["trimmed"])
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if opts["trimmed"]:
        cmd += ["-ss", f"{opts['start']:.3f}", "-to", f"{opts['end']:.3f}"]
    cmd += ["-i", str(src), "-map", "0:v:0", "-map", "0:a?", "-map_metadata", "0"]
    for key, value in metadata.items():
        if value:
            cmd += ["-metadata", f"{key}={value}"]
    if lossless:
        cmd += ["-c", "copy"]
    else:
        vcodec, acodec = FORMATS[opts["format"]]
        crf = str(QUALITY[opts["quality"]] + (12 if vcodec == "libvpx-vp9" else 0))
        size = RESOLUTIONS[opts["resolution"]]
        if size:
            w, h = size
            cmd += ["-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                           f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"]
        if vcodec == "libx264":
            cmd += ["-c:v", vcodec, "-preset", "slow", "-crf", crf, "-pix_fmt", "yuv420p"]
        else:
            cmd += ["-c:v", vcodec, "-b:v", "0", "-crf", crf, "-row-mt", "1"]
        cmd += ["-c:a", acodec, "-b:a", "192k"]
    if opts["format"] in {"mp4", "mov"}:
        cmd += ["-movflags", "+faststart+use_metadata_tags"]
    cmd.append(str(dst))
    return cmd


class Exporter:
    def __init__(self, store, run=subprocess.run):
        self.store = store
        self.folder = Path(store.root) / "exports"
        self._run = run

    def export(self, clip_id: str, options: dict) -> dict:
        clip = self.store.get(clip_id)
        if not clip:
            raise ValueError("Clipe não encontrado")
        if clip["status"] not in {"ready", "approved"}:
            raise ValueError("Só cortes prontos ou aprovados podem ser exportados")
        src = Path(clip.get("output_path") or "")
        if not src.is_file() or src.is_symlink():
            raise ValueError("Arquivo do corte não encontrado")
        duration = duration_of(probe(src))
        opts = validate_options(options, duration)
        metadata = build_metadata(clip, opts["title"])
        self.folder.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        name = f"{clip_id}-{stamp}.{opts['format']}"
        dst = self.folder / name
        partial = self.folder / (name + ".partial." + opts["format"])
        cmd = ffmpeg_command(src, partial, opts, metadata)
        try:
            result = self._run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                               errors="replace", timeout=3600, check=False)
            if result.returncode != 0:
                tail = (result.stderr or "").strip().splitlines()[-1:] or [""]
                raise ValueError("FFmpeg falhou na exportação: " + tail[0][:160])
            info = probe(partial)
            if duration_of(info) <= 0:
                raise ValueError("Exportação gerou vídeo inválido")
            partial.replace(dst)
        finally:
            partial.unlink(missing_ok=True)
        record = {"file": name, "clip_id": clip_id, "options": opts, "metadata": metadata,
                  "lossless": "-c" in cmd and cmd[cmd.index("-c") + 1] == "copy",
                  "source_file": src.name, "creator": clip.get("creator"),
                  "source_url": clip.get("source_url"), "rights_status": clip.get("rights_status"),
                  "size_bytes": dst.stat().st_size, "created_at": stamp}
        (self.folder / (name + ".json")).write_text(json.dumps(record, ensure_ascii=False, indent=2),
                                                    encoding="utf-8")
        return record

    def list(self, clip_id: str | None = None) -> list[dict]:
        if not self.folder.is_dir():
            return []
        rows = []
        for meta in sorted(self.folder.glob("*.json"), reverse=True):
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if clip_id and data.get("clip_id") != clip_id:
                continue
            if (self.folder / str(data.get("file", ""))).is_file():
                rows.append(data)
        return rows[:100]

    def path(self, name: str) -> Path:
        if not NAME.fullmatch(name or "") or name.endswith(".json"):
            raise ValueError("Nome de exportação inválido")
        file = (self.folder / name).resolve()
        if file.parent != self.folder.resolve() or not file.is_file() or file.is_symlink():
            raise ValueError("Exportação não encontrada")
        return file

    def delete(self, name: str) -> None:
        file = self.path(name)
        file.unlink()
        (self.folder / (name + ".json")).unlink(missing_ok=True)


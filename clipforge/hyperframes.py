"""Optional HyperFrames finishing stage for local, rights-checked clips.

This exports a valid HTML/CSS composition using a real, already-rendered MP4.
It never downloads Twitch material and never posts to social networks.
HyperFrames CLI and Chromium are only needed for the optional final render.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .core import ClipStore, duration_of, probe

CSS_TEMPLATE = Path(__file__).with_name("templates") / "shorts.css"
TIME_CODE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s+-->\s+"
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})(?:\s+.*)?$"
)
MAX_SRT_BYTES = 128 * 1024
MAX_CAPTIONS = 150
MAX_VIDEO_BYTES = 320 * 1024 * 1024


def _timecode(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_srt(text: str, duration: float) -> list[tuple[float, float, str]]:
    """Parse *provided* SRT subtitles. Never pretend to transcribe speech."""
    if len(text.encode("utf-8")) > MAX_SRT_BYTES:
        raise ValueError("Subtitle input exceeds 128 KiB")
    cues: list[tuple[float, float, str]] = []
    for block in re.split(r"\r?\n\s*\r?\n", text.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        index = 1 if lines[0].isdigit() else 0
        if index >= len(lines):
            continue
        match = TIME_CODE.match(lines[index])
        if not match:
            continue
        groups = match.groups()
        start = _timecode(*groups[0:4])
        end = _timecode(*groups[4:8])
        content = " ".join(lines[index + 1 :]).strip()
        if not content:
            continue
        if start < 0 or start >= duration or end <= start:
            continue
        end = min(end, duration)
        if end - start < 0.08:
            continue
        cues.append((start, end - start, content[:220]))
        if len(cues) >= MAX_CAPTIONS:
            break
    return cues


def composition_html(duration: float, creator: str, title: str,
                     captions: list[tuple[float, float, str]] | None = None) -> str:
    """Pure HTML writer; all externally sourced strings are escaped."""
    if not (1 <= duration <= 60):
        raise ValueError("Final video must last between 1 and 60 seconds")
    safe_title = html.escape(title.strip()[:72] or "GTA VI • DESTAQUES", quote=True)
    safe_creator = html.escape(creator.strip()[:90], quote=True)
    if not safe_creator:
        raise ValueError("Creator attribution required")
    safe_duration = f"{duration:.3f}"
    title_length = f"{min(4.5, duration):.3f}"
    subtitle = []
    for index, (start, length, text) in enumerate(captions or []):
        if start < 0 or length <= 0 or start + length > duration + 0.01:
            raise ValueError("Caption outside video duration")
        cleaned = html.escape(text.strip()[:220], quote=True)
        if not cleaned:
            continue
        subtitle.append(
            f'<div id="caption-{index}" class="clip caption" data-start="{start:.3f}" '
            f'data-duration="{length:.3f}" data-track-index="3">'
            f'<span>{cleaned}</span></div>'
        )
    caption_html = "\n".join(subtitle)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GTA CLIPS — HyperFrames</title>
<link rel="stylesheet" href="./style.css">
</head>
<body>
<div id="root" data-composition-id="gta6-clips" data-start="0"
     data-duration="{safe_duration}" data-width="1080" data-height="1920"
     data-fps="30" data-no-timeline="true">
  <video id="gameplay" class="clip" src="./source.mp4"
         data-start="0" data-duration="{safe_duration}"
         data-track-index="0" playsinline preload="auto"></video>
  <section id="header" class="clip headline" data-start="0"
           data-duration="{title_length}" data-track-index="1">
    <div class="kicker">GTA VI <span class="kicker-bullet">/</span> CLIP</div>
    <h1>{safe_title}</h1>
    <div class="headline-line"></div>
  </section>
  <div id="credit" class="clip credit" data-start="0"
       data-duration="{safe_duration}" data-track-index="2">
    <span class="credit-mark">SOURCE</span>
    <span class="credit-creator">{safe_creator}</span>
  </div>
  {caption_html}
</div>
</body>
</html>
"""


def export_composition(store: ClipStore, clip_id: str, *, title: str = "",
                       captions_file: Path | None = None) -> Path:
    """Create a self-contained local project. Strictly reuse ready/approved output."""
    if not re.fullmatch(r"[a-zA-Z0-9]{12}", clip_id):
        raise ValueError("Invalid clip ID")
    item = store.get(clip_id)
    if not item or item["status"] not in {"ready", "approved"}:
        raise ValueError("Only reviewed-ready or approved clips can be exported")
    source = store.output / f"{clip_id}.mp4"
    if source.is_symlink() or not source.is_file():
        raise ValueError("Expected ready video is missing")
    if not item.get("output_path") or Path(item["output_path"]).resolve() != source.resolve():
        raise ValueError("Video does not match the stored ready artifact")
    if source.stat().st_size > MAX_VIDEO_BYTES:
        raise ValueError("Video exceeds finishing-stage size limit")
    info = probe(source)
    video = next((s for s in info.get("streams", [])
                  if s.get("codec_type") == "video"), None)
    if not video or (video.get("width"), video.get("height")) != (1080, 1920):
        raise ValueError("HyperFrames requires 1080x1920 source from FFmpeg pipeline")
    duration = duration_of(info)
    if duration < 1 or duration > 60:
        raise ValueError("Unexpected source duration")

    captions = []
    if captions_file is not None:
        if captions_file.is_symlink() or captions_file.suffix.lower() != ".srt":
            raise ValueError("Only regular SRT subtitle files are supported")
        if captions_file.stat().st_size > MAX_SRT_BYTES:
            raise ValueError("Subtitle file too large")
        captions = parse_srt(captions_file.read_text(encoding="utf-8-sig"), duration)

    projects_root = store.root / "hyperframes"
    if projects_root.exists() and projects_root.is_symlink():
        raise ValueError("Unsafe HyperFrames output directory")
    projects_root.mkdir(parents=True, exist_ok=True)
    final_dir = projects_root / clip_id
    if final_dir.exists() and final_dir.is_symlink():
        raise ValueError("Unsafe composition directory")
    final_dir.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=final_dir, prefix="source-", suffix=".tmp",
                                     delete=False) as f:
        temporary = Path(f.name)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, final_dir / "source.mp4")
    finally:
        temporary.unlink(missing_ok=True)

    markup = composition_html(duration, item["creator"], title, captions)
    (final_dir / "index.html").write_text(markup, encoding="utf-8")
    (final_dir / "style.css").write_text(CSS_TEMPLATE.read_text(encoding="utf-8"),
                                         encoding="utf-8")
    # Public metadata only: no signature/evidence of privately granted permission.
    metadata = {
        "clip_id": clip_id, "creator": item["creator"],
        "source_url": item.get("source_url") or "",
        "status_at_export": item["status"],
        "engine": "HyperFrames (optional post-production)",
        "duration_sec": round(duration, 3),
        "captions_count": len(captions),
        "rights_status": item["rights_status"],
        "rendered": False,
    }
    (final_dir / "manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return final_dir


def render_composition(directory: Path, *, timeout: int = 1200) -> Path:
    """Render via *installed* HyperFrames CLI. No auto-install, no cloud uploads."""
    directory = directory.resolve()
    if not (directory / "index.html").is_file() or not (directory / "source.mp4").is_file():
        raise ValueError("Incomplete HyperFrames composition")
    if shutil.which("node") is None or shutil.which("npx") is None:
        raise RuntimeError("Install Node.js 22+ and HyperFrames CLI before rendering")
    command = ["npx", "--no-install", "hyperframes"]
    env = dict(os.environ, npm_config_offline="true", HYPERFRAMES_NO_UPDATE_CHECK="1")
    for args in (["lint", "."], ["render", "-o", "final.mp4"]):
        try:
            result = subprocess.run(command + args, cwd=directory, env=env,
                                    check=False, capture_output=True, text=True,
                                    timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError("HyperFrames CLI unavailable or render timed out") from exc
        if result.returncode:
            raise RuntimeError(
                "HyperFrames CLI failed. Run 'npm install --no-save hyperframes' "
                "in the composition directory, then repeat. "
                f"Exit code: {result.returncode}"
            )
    output = directory / "final.mp4"
    if not output.is_file():
        raise RuntimeError("HyperFrames reported success without output.mp4")
    info = probe(output)
    vid = next((s for s in info.get("streams", [])
                if s.get("codec_type") == "video"), None)
    if not vid or (vid.get("width"), vid.get("height")) != (1080, 1920):
        output.unlink(missing_ok=True)
        raise RuntimeError("HyperFrames output failed portrait QA")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare an authorized clip for HyperFrames")
    parser.add_argument("clip_id", help="12-character ID shown in the clip database")
    parser.add_argument("--data-dir", default=os.getenv("CLIPS_DATA_DIR", "./data"))
    parser.add_argument("--title", default="GTA VI • DESTAQUES")
    parser.add_argument("--srt", type=Path, help="Optional real subtitle SRT, not generated")
    parser.add_argument("--render", action="store_true",
                        help="Use installed local HyperFrames CLI after exporting")
    args = parser.parse_args()
    project = export_composition(
        ClipStore(Path(args.data_dir)), args.clip_id,
        title=args.title, captions_file=args.srt
    )
    print("HyperFrames project:", project)
    if args.render:
        print("Rendered:", render_composition(project))


if __name__ == "__main__":
    main()

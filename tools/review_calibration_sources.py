"""Fetch real Twitch source clips for private, unlisted editorial calibration.

Only source media and provenance are produced here. Nothing is published
to social networks; public listing is not a reuse license.
"""
from __future__ import annotations
import json
import subprocess
from pathlib import Path

TARGETS = (
    ("gaules", "BrainyPluckyTermiteDxCat-a3FXab60ZA7_JdQQ", "Gaules", "Ticket to Ride", "QUEM MIJOU AQUI????"),
    ("sodapoppin", "SmoothFitAdminSwiftRage-9wn3aLtEkJVSCQaO", "sodapoppin", "World of Warcraft", "average mitch stream"),
    ("caedrel", "BenevolentKitschyCiderStinkyCheese-YznSpMgb8ToByJv5", "Caedrel", "League of Legends", "Seraphine ult"),
)
OUT = Path("review-artifacts")
OUT.mkdir(exist_ok=True)


def cmd(*args, timeout=180):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout)


def download(name: str, clip_id: str):
    problems = []
    for url in ("https://clips.twitch.tv/" + clip_id,):
        try:
            cmd("yt-dlp", "--no-playlist", "--no-warnings", "--retries", "2",
                "--socket-timeout", "18", "-f", "b[ext=mp4]/b",
                "--merge-output-format", "mp4",
                "-o", str(OUT / (name + ".%(ext)s")), url, timeout=170)
            candidates = list(OUT.glob(name + ".*"))
            if candidates:
                return candidates[0]
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            problems.append(str(exc)[-250:])
    raise RuntimeError(f"{name}: download failed: {problems}")


def main():
    imported, errors = [], []
    for name, clip_id, creator, category, title in TARGETS:
        try:
            source = download(name, clip_id)
            info = json.loads(cmd("ffprobe", "-v", "error",
                "-show_entries", "format=duration,size:stream=codec_type,width,height",
                "-of", "json", str(source), timeout=40).stdout)
            seconds = float(info["format"]["duration"])
            if seconds < 8 or seconds > 180 or not any(
                x.get("codec_type") == "video" for x in info["streams"]
            ):
                raise ValueError("Invalid media duration or no video stream")
            imported.append({
                "slug": name, "filename": source.name,
                "creator": creator, "category": category, "title": title,
                "source": "https://clips.twitch.tv/" + clip_id,
                "duration": seconds, "for_review_only": True,
                "republication_approval": False,
            })
            print(f"DOWNLOADED {name}: {seconds:.2f}s",flush=True)
        except (RuntimeError, ValueError, KeyError, TypeError) as exc:
            print(f"FAILED {name}: {exc}",flush=True)
            errors.append({"slug": name, "error": str(exc)[-220:]})
    (OUT / "sources.json").write_text(
        json.dumps({"sources": imported, "errors": errors},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")
    if len(imported) < 2:
        raise SystemExit(f"Only {len(imported)} clips downloaded; require >=2")
    print(f"PASS: {len(imported)} real source videos for calibration")


if __name__ == "__main__":
    main()

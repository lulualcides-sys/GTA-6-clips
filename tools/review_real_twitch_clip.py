"""Produce a PRIVATE editorial review from a publicly accessible Twitch clip.
Not for automated publishing; no claims of rights or ownership.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

CLIP_ID = "EagerMagnificentOpossumRaccAttack-Z_1cH-jBbf9w3u7C"
CLIP_URL = "https://clips.twitch.tv/" + CLIP_ID
STREAMER = "xQc"
OUTPUT = Path("review-artifacts")
FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def run(*cmd, timeout=180):
    return subprocess.run(cmd, check=True, text=True, capture_output=True, timeout=timeout)


def download() -> Path:
    OUTPUT.mkdir(exist_ok=True)
    sources = [
        CLIP_URL,
        "https://www.twitch.tv/xqc/clip/" + CLIP_ID,
    ]
    issues = []
    for url in sources:
        try:
            run("yt-dlp", "--no-playlist", "--no-warnings", "--retries", "2",
                "-f", "b[ext=mp4]/b", "--merge-output-format", "mp4",
                "-o", str(OUTPUT / "source.%(ext)s"), url, timeout=150)
            candidates = list(OUTPUT.glob("source.*"))
            if candidates:
                return candidates[0]
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            issues.append((url, (e.stderr or str(e))[-300:]))
    raise RuntimeError("No Twitch source could be retrieved: " + repr(issues))


def edit(video: Path) -> Path:
    if not FONT.exists():
        raise FileNotFoundError(FONT)
    details = json.loads(run("ffprobe", "-v", "error", "-show_entries",
                             "format=duration:stream=codec_type,width,height",
                             "-of", "json", str(video)).stdout)
    length = float(details["format"]["duration"])
    if not 8 <= length <= 65:
        raise ValueError(f"unexpected Twitch source duration {length}")
    # Blur fills the portrait canvas while gameplay remains fully visible.
    # Titles identify this as a review of a real clip, not an owned recording.
    font = str(FONT)
    filters = (
        "[0:v]split=2[base][front];"
        "[base]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,boxblur=32:2,eq=brightness=-0.17:saturation=0.9[bg];"
        "[front]scale=1080:-2:flags=lanczos[game];"
        "[bg][game]overlay=x=0:y=(H-h)/2:shortest=1,format=yuv420p,"
        "drawbox=x=0:y=0:w=iw:h=260:color=0x0b182e@0.82:t=fill,"
        "drawbox=x=0:y=1600:w=iw:h=320:color=0x0b182e@0.82:t=fill,"
        f"drawtext=fontfile={font}:text='TWITCH / GTA V':x=(w-text_w)/2:y=72:fontcolor=0xbaf6dc:fontsize=44,"
        f"drawtext=fontfile={font}:text='SPLAT':x=(w-text_w)/2:y=145:fontcolor=white:fontsize=106:enable='between(t,0,3.7)',"
        f"drawtext=fontfile={font}:text='CLIPE REAL':x=(w-text_w)/2:y=160:fontcolor=white:fontsize=79:enable='gte(t,3.7)',"
        f"drawtext=fontfile={font}:text='xQc  -  TWITCH':x=(w-text_w)/2:y=1663:fontcolor=0xa7bfff:fontsize=49,"
        f"drawtext=fontfile={font}:text='EDICAO PARA AVALIACAO':x=(w-text_w)/2:y=1760:fontcolor=0xe3ecff:fontsize=37,"
        "fps=30,format=yuv420p[out]"
    )
    result = OUTPUT / "GTA_Twitch_xQc_Splat_Review.mp4"
    cmd = ["ffmpeg", "-y", "-nostdin", "-v", "error", "-i", str(video),
           "-filter_complex", filters, "-map", "[out]", "-map", "0:a?",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
           "-movflags", "+faststart", str(result)]
    run(*cmd, timeout=400)
    check = json.loads(run("ffprobe", "-v", "error", "-show_entries",
                           "stream=codec_type,width,height:format=duration,size",
                           "-of", "json", str(result)).stdout)
    v = next(s for s in check["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (1080, 1920)
    assert float(check["format"]["duration"]) >= 8
    (OUTPUT / "source.json").write_text(json.dumps({
        "title": "Splat", "streamer": STREAMER, "original_url": CLIP_URL,
        "game": "Grand Theft Auto V", "purpose": "Private editorial review only",
        "input_duration_sec": length, "output": result.name,
        "publishing_authorized": False,
    }, indent=2), encoding="utf-8")
    print("REAL CLIP REVIEW RENDERED", result, "duration", length)
    return result


if __name__ == "__main__":
    edit(download())

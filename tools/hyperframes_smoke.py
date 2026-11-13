"""Dedicated real HyperFrames render test, with generated own/test footage.

Use only after installing Node>=22 and HyperFrames locally. This script never
connects to Twitch, accesses social accounts, or publishes media.
"""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from clipforge.core import ClipStore
from clipforge.hyperframes import export_composition, render_composition


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--render", action="store_true", help="Run local HyperFrames CLI too")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="gta-hyperframes-pilot-") as root:
        store = ClipStore(Path(root))
        clip_id = "abcdef123456"
        source = store.output / (clip_id + ".mp4")
        subprocess.run([
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "2", "-shortest",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
        ], check=True, timeout=100)
        with store._db() as db:
            db.execute(
                """INSERT INTO clips
                   (id,sha256,filename,creator,source_url,evidence,rights_status,
                    input_path,output_path,start_sec,duration_sec,score,status,error,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    clip_id, "f" * 64, "synthetic.mp4", "Synthetic QA Footage",
                    "", "", "owned", str(source), str(source),
                    0, 2, None, "ready", None, "2026-11-13T00:00:00Z"
                ),
            )
            db.commit()
        subtitle = Path(root) / "caption.srt"
        subtitle.write_text(
            "1\n00:00:00,200 --> 00:00:01,500\nSynthetic QA — GTA VI\n",
            encoding="utf-8",
        )
        project = export_composition(store, clip_id, title="GTA VI / LAB TEST",
                                     captions_file=subtitle)
        assert (project / "index.html").exists()
        assert (project / "hyperframes-project.zip").exists()
        print("HyperFrames export PASS", flush=True)
        if args.render:
            output = render_composition(project, timeout=300)
            assert output.is_file()
            print("HyperFrames final render PASS: 1080x1920 MP4", flush=True)


if __name__ == "__main__":
    main()

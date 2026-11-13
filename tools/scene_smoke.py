"""Actual PySceneDetect acceptance test on synthetic edits, no protected media."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from clipforge.smart import find_cuts, scene_aware_start


def main():
    with tempfile.TemporaryDirectory(prefix="gta-scenes-") as temp:
        movie = Path(temp) / "hard-cuts.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=black:s=320x180:r=15:d=2",
            "-f", "lavfi", "-i", "color=c=white:s=320x180:r=15:d=2",
            "-f", "lavfi", "-i", "color=c=black:s=320x180:r=15:d=2",
            "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
            "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", str(movie)
        ], check=True, timeout=45)
        from scenedetect import open_video, SceneManager, ContentDetector
        debug_video = open_video(str(movie))
        debug_mgr = SceneManager()
        debug_mgr.add_detector(ContentDetector(threshold=27.0))
        processed = debug_mgr.detect_scenes(video=debug_video, end_time=6.0)
        print("DEBUG scene frames processed:", processed,
              "raw cuts:", [c.get_seconds() for c in debug_mgr.get_cut_list()],
              "scenes:", len(debug_mgr.get_scene_list(start_in_scene=True)), flush=True)
        cuts = find_cuts(movie, limit_seconds=6)
        assert len(cuts) >= 2, f"Expected at least 2 synthetic edits: {cuts}"
        assert 1.5 < cuts[0] < 2.5, cuts
        assert 3.5 < cuts[1] < 4.5, cuts
        start = scene_aware_start(1.7, total=6, length=3, cuts=cuts)
        assert 0 <= start <= 3, start
        print(f"SCENES SMOKE PASS: cut points={cuts} proposed_start={start}",flush=True)


if __name__=="__main__":
    main()

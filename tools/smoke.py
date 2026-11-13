"""E2E smoke test with a synthetic owned video, no streamers or external assets."""
from __future__ import annotations
import json
import subprocess
import tempfile
from pathlib import Path
from clipforge.core import ClipStore, render_clip


def main():
    with tempfile.TemporaryDirectory(prefix="gta6-smoke-") as temp:
        store=ClipStore(Path(temp))
        source=store.incoming/"demo.mp4"
        subprocess.run([
            "ffmpeg","-y","-v","error","-f","lavfi","-i","testsrc2=size=640x360:rate=30",
            "-f","lavfi","-i","sine=frequency=500:sample_rate=48000",
            "-t","12","-shortest","-c:v","libx264","-preset","ultrafast",
            "-pix_fmt","yuv420p","-c:a","aac",str(source)
        ],check=True,timeout=90)
        (store.incoming/"demo.mp4.rights.json").write_text(
            json.dumps({"creator":"Synthetic test generator","rights_status":"owned",
                        "start_sec":0,"duration_sec":10}),encoding="utf-8")
        result=store.scan()
        assert len(result["added"])==1 and not result["errors"],result
        clip_id=result["added"][0]
        store.update(clip_id,status="queued")
        render_clip(store,clip_id)
        item=store.get(clip_id)
        assert item["status"]=="ready",item.get("error")
        assert Path(item["output_path"]).is_file()
        events=store.activity.recent(clip_id)
        names={e["agent"] for e in events}
        assert {"ingestao","direitos","curadoria","edicao"}.issubset(names), events
        assert any(e["agent"]=="edicao" and e["state"]=="complete" for e in events)
        print("SMOKE PASS: generated source -> rights -> ffmpeg -> 1080x1920 MP4")


if __name__=="__main__":
    main()

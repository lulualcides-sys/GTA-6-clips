"""Temporary GTA V source audition for three different editorial styles.

Public Twitch clip URLs used only for non-social editorial calibration.
Source credits and metadata retained. No publication/license claims.
"""
import json, subprocess
from pathlib import Path
OUT=Path("review-gta5-v9"); OUT.mkdir(exist_ok=True)
SOURCES=[
("bicycle_collision","Xiceman","FancyWrongGarageChocolateRain-fpBTAe1Qh1ySFH8R","GTA V RP","Bicycle vs Car - Car Wins","humor"),
("ziggy_flop","Ziggy","ThoughtfulCoweringBatDeIlluminati-igMSsHdENoyzs02v","GTA V RP","Flop jump","humor"),
("alvis_fall","Harmless","SquarePrettyWaspMrDestructoid-2wM5dz0beWM48oNo","GTA V RP","alvis falls 10000 feet","humor"),
("test_drive","pasty","BlitheSpotlessSpindleTooSpicy-ZUDkVYCF8D0zjxrM","GTA V RP","Joe and Roxy go on a quick test drive","perseguicao"),
("monkey_shot","Burn","GlamorousDeadFishLitFam-eeOd038AcvQsQzrQ","GTA V RP","Burn as a Monkey gets oneshot","humor")
]
manifest=[]
for slug,creator,clip_id,game,title,style in SOURCES:
    url="https://clips.twitch.tv/"+clip_id
    row=dict(slug=slug,creator=creator,clip_id=clip_id,source=url,game=game,title=title,style=style)
    try:
        result=subprocess.run(["yt-dlp","--no-playlist","--no-warnings","--retries","2",
         "--socket-timeout","16","--download-sections","*0-180",
         "-f","b[ext=mp4]/b","-o",str(OUT/(slug+".%(ext)s")),url],
         text=True,capture_output=True,timeout=145)
        if result.returncode: raise RuntimeError(result.stderr[-380:])
        files=list(OUT.glob(slug+".*"))
        files=[f for f in files if f.suffix.lower() in (".mp4",".mkv",".webm")]
        if not files: raise RuntimeError("No video file")
        file=files[0]
        probe=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration,size:stream=codec_type,width,height","-of","json",str(file)],capture_output=True,text=True,timeout=30,check=True)
        meta=json.loads(probe.stdout);seconds=float(meta["format"]["duration"])
        if seconds<8 or seconds>190: raise RuntimeError("Unexpected duration "+str(seconds))
        row.update(ready=True,file=file.name,duration=seconds,size_bytes=file.stat().st_size)
        print("OK",slug,round(seconds,1),flush=True)
    except Exception as e:
        row.update(ready=False,error=str(e)[-350:])
        print("SKIP",slug,row["error"],flush=True)
    manifest.append(row)
(OUT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
if sum(x["ready"] for x in manifest)<3: raise SystemExit("Fewer than 3 playable source candidates")

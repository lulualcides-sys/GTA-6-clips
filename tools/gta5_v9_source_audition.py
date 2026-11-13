"""Temporary GTA V source audition for three different editorial styles.

Public Twitch clip URLs used only for non-social editorial calibration.
Source credits and metadata retained. No publication/license claims.
"""
import json, subprocess
from pathlib import Path
OUT=Path("review-gta5-v9"); OUT.mkdir(exist_ok=True)
SOURCES=[
("cotonete_malandro","Cotonete","BraveRelatedCobraJebaited-NIqBWDRIjtJgG9zi","GTA V RP","malandro demais se engana","dialogo"),
("mungo_chase","Mungo","DaintyShinyClamSMOrc-M_WuDYEie_m_QSCG","GTA V RP","when chase ends with a bang","perseguicao"),
("nakkida_scare","Nakkida","ThirstyStrongBobaSquadGoals-3cec78fl0q86yQvi","GTA V RP","Tessa Scares JP","humor"),
("xqc_driving","xQc","DeadOnerousWallabyMoreCowbell-4T3ZlNLPxxnFgrX_","GTA V RP","becoming a jet","perseguicao"),
("jenny_driving","Jennybeartv","TameGlamorousCurlewWholeWheat-OWOnpzhluySLFusB","GTA V RP","Ratty driving has consequences","humor"),
("xqc_splat","xQc","ProudEphemeralScorpionTheTarFu-gElb_ERdab-xW0E8","GTA V RP","unexpected moment","humor")
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

"""Download actual public Twitch clips for private editorial tests only.

We need full setup > conflict > payoff > reaction, not just a 7s punchline.
Do not publish, simulate audience reaction, or claim reuse licenses.
"""
import json
import pathlib
import subprocess

OUT=pathlib.Path("review-storytelling")
OUT.mkdir(parents=True,exist_ok=True)
CLIPS=[
 ("alanzoka_unspottable","alanzoka","CrispyAnnoyingChamoisChefFrank-zb91tP595-wunBYK","Unspottable","TOMA TOMA TOMA"),
 ("alanzoka_rocket_league","alanzoka","ZanyBlitheEggplantBCouch-JmSuRhLkW2YhEplt","Rocket League","Último tornas do ano"),
 ("alanzoka_tomate","alanzoka","GlamorousCrispyDragonfruitDendiFace-_-g5xd3Cgs1k9YmB","Black Myth: Wukong","ALAN COMENDO TOMATE INTEIRO"),
 ("gaules_cs","gaules","SlickCrazyMooseBleedPurple-Ud75EWwjvKNIO76F","Counter-Strike","KSCERATO e molodoy vencem 2v4"),
]
results=[]
for slug,channel,clip_id,game,title in CLIPS:
    url="https://clips.twitch.tv/"+clip_id
    try:
        r=subprocess.run(["yt-dlp","--no-playlist","--no-warnings","--retries","2",
            "--socket-timeout","17","-f","b[ext=mp4]/b",
            "--merge-output-format","mp4",
            "-o",str(OUT/(slug+".%(ext)s")),url],
            text=True,capture_output=True,timeout=170)
        if r.returncode: raise RuntimeError(r.stderr[-600:])
        files=list(OUT.glob(slug+".*"))
        if not files: raise RuntimeError("No MP4 created")
        file=files[0]
        probe=subprocess.run(["ffprobe","-v","error","-show_entries",
          "format=duration,size:stream=codec_type,width,height",
          "-of","json",str(file)],check=True,capture_output=True,text=True,timeout=40)
        meta=json.loads(probe.stdout)
        duration=float(meta["format"]["duration"])
        if not 20 <= duration <= 185: raise ValueError("Source length unexpected: "+str(duration))
        if not any(x.get("codec_type")=="video" for x in meta["streams"]):
            raise ValueError("No video track")
        results.append({"slug":slug,"filename":file.name,"game":game,"creator":channel,
         "title":title,"url":url,"duration":duration,
         "republication_authorized":False})
        print("SUCCESS",slug,round(duration,2),"s",file.stat().st_size,flush=True)
    except Exception as exc:
        print("FAILED",slug,str(exc)[-200:],flush=True)
        results.append({"slug":slug,"error":str(exc)[-260:],"url":url})
(OUT/"manifest.json").write_text(json.dumps(results,ensure_ascii=False,indent=2))
if sum("duration" in x for x in results)<2: raise SystemExit("Fewer than 2 usable long clips")

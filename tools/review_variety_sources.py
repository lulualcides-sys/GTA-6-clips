"""Private clip-source audition; no social publishing, no repo media."""
from pathlib import Path
import json
import subprocess
OUT = Path("review-variety")
OUT.mkdir(exist_ok=True)
SAMPLES = [
 ("rocket_own_goal","alphakep","MoralHeadstrongEggFreakinStinkin-2rzx7r4wGF94Ia7I","Rocket League","OWN GOAL OF A LIFE TIME?!"),
 ("fortnite_no_scope","suetam1v4","SpineyExquisiteUdonResidentSleeper-IKNxkOggg7XcSCAc","Fortnite","NO SCOPE LINDISSIMO"),
 ("minecraft_flying","hivise","RenownedFaithfulToadSuperVinlin-fo3YNf9D8qxwN5uK","Minecraft","Bro went flying LMAOOO"),
 ("cs_ace","ESLCS","YawningEphemeralSrirachaKeyboardCat-jaB-a4iKdM6HiCa-","Counter-Strike","makazze ACE"),
]
records=[]
for slug,channel,clip_id,game,title in SAMPLES:
    url="https://clips.twitch.tv/"+clip_id
    data={"slug":slug,"streamer":channel,"game":game,"title":title,"source":url}
    try:
        result=subprocess.run(["yt-dlp","--no-warnings","--no-playlist","--retries","2",
          "--socket-timeout","15","-f","b[ext=mp4]/b", "-o",
          str(OUT/(slug+".%(ext)s")),url],capture_output=True,text=True,timeout=145)
        if result.returncode: raise RuntimeError(result.stderr[-340:])
        files=list(OUT.glob(slug+".*"))
        if not files: raise RuntimeError("No output file")
        file=files[0]
        meta=subprocess.run(["ffprobe","-v","error","-show_entries",
            "format=duration,size:stream=codec_type,width,height",
            "-of","json",str(file)],capture_output=True,text=True,check=True,timeout=20)
        data.update(json.loads(meta.stdout)["format"])
        data["filename"]=file.name
        data["ready"]=True
        print("OK",slug,data["duration"],flush=True)
    except Exception as e:
        data.update({"ready":False,"error":str(e)[-300:]})
        print("FAILED",slug,data["error"],flush=True)
    records.append(data)
(OUT/"index.json").write_text(json.dumps(records,ensure_ascii=False,indent=2))
if sum(x["ready"] for x in records)<2: raise SystemExit("Need >=2 verified source clips")

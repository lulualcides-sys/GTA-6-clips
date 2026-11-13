import http.client
import json
import os
import tempfile
import threading
import time
import unittest
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

from clipforge.core import Runtime
from clipforge.web import make_handler


class CaptionEndpointsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {
            "DASHBOARD_TOKEN":"test-secret-unique", "AUTO_SCAN":"0",
            "AUTO_RENDER":"0", "AUTO_TRANSCRIBE":"0",
            "TWITCH_ENABLED":"0", "TWITCH_CLIENT_ID":"",
            "TWITCH_CLIENT_SECRET":"", "WHISPER_MODEL":"base"
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.runtime = Runtime(Path(self.temp.name))
        self.cid = "ff11aa22bb33"
        self.video = self.runtime.store.output / f"{self.cid}.mp4"
        self.video.write_bytes(b"synthetic safe video for mocked inference")
        with self.runtime.store._db() as db:
            db.execute("""INSERT INTO clips
                (id,sha256,filename,creator,source_url,evidence,rights_status,
                input_path,output_path,start_sec,duration_sec,score,status,error,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self.cid, "f"*64, "my.mp4", "My Creator", "",
                 "private proof should never leak", "owned", "/secret/source.mp4",
                 str(self.video), 0, 12, None, "ready", None,
                 "2026-11-13T00:00:00Z"))
            db.commit()
        self.server=ThreadingHTTPServer(("127.0.0.1",0),make_handler(self.runtime))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.runtime.executor.shutdown(wait=True)
        self.runtime.captions.stop()

    def send(self,method,path,authorized=True):
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=8)
        headers={"Authorization":"Bearer test-secret-unique"} if authorized else {}
        conn.request(method,path,headers=headers)
        res=conn.getresponse()
        code=res.status
        data=res.read()
        conn.close()
        return code,data

    def test_caption_routes_require_auth(self):
        self.assertEqual(self.send("GET","/api/captions",False)[0],401)
        self.assertEqual(self.send("POST",f"/api/clips/{self.cid}/transcribe",False)[0],401)
        self.assertEqual(self.send("GET",f"/api/clips/{self.cid}/captions.srt",False)[0],401)

    def test_get_clip_listing_strips_private_license_evidence(self):
        code,data=self.send("GET","/api/clips")
        self.assertEqual(code,200)
        response=json.loads(data)["clips"][0]
        self.assertNotIn("evidence",response)
        self.assertNotIn("input_path",response)
        self.assertEqual(response["output_path"],True)
        self.assertNotIn("private proof",data.decode("utf-8"))

    def test_transcript_flows_to_hyperframes_export(self):
        word=NS(start=.3,end=1.8,word="Acertou!")
        model=NS(transcribe=lambda *a,**kwargs:(
            [NS(start=.3,end=1.8,text="Acertou!",words=[word])],
            NS(language="pt")))
        with patch("clipforge.captions.whisper_model",return_value=model):
            code,data=self.send("POST",f"/api/clips/{self.cid}/transcribe")
            self.assertEqual(code,202)
            for _ in range(60):
                result=self.runtime.captions.status(self.cid)
                if result["status"] in {"ready","failed"}:
                    break
                time.sleep(.02)
        self.assertEqual(result["status"],"ready",result)
        code,data=self.send("GET",f"/api/clips/{self.cid}/captions.srt")
        self.assertEqual(code,200)
        self.assertIn(b"Acertou!",data)
        info={"format":{"duration":"12"},
              "streams":[{"codec_type":"video","width":1080,"height":1920}]}
        with patch("clipforge.hyperframes.probe",return_value=info):
            code,data=self.send("POST",f"/api/clips/{self.cid}/hyperframes")
        self.assertEqual(code,201,data)
        archive=(self.runtime.store.root/"hyperframes"/self.cid/"hyperframes-project.zip")
        with zipfile.ZipFile(archive) as bundle:
            markup=bundle.read("index.html").decode("utf-8")
        self.assertIn("Acertou!",markup)
        self.assertEqual(self.runtime.store.get(self.cid)["status"],"ready")


if __name__=="__main__":
    unittest.main()

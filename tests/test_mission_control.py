"""Truthful agent-dashboard telemetry and authorization regression tests."""
import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from clipforge.core import ClipStore, Runtime
from clipforge.telemetry import ActivityLog, AGENTS
from clipforge.web import make_handler


class MissionLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ClipStore(Path(self.temp.name))

    def test_new_database_has_no_fake_activity(self):
        self.assertEqual(self.store.activity.recent(), [])
        self.assertEqual(len(AGENTS), 9)

    def test_real_ingest_dedupe_and_persisted_events(self):
        video = self.store.incoming / "owned.mp4"
        video.write_bytes(b"owned video test")
        sidecar = self.store.incoming / "owned.mp4.rights.json"
        sidecar.write_text(json.dumps({"creator": "My owned channel",
                         "rights_status": "owned", "start_sec": 0,
                         "duration_sec": 12}), encoding="utf-8")
        info = {"format": {"duration": "20"},
                "streams": [{"codec_type": "video", "width": 640, "height": 360}]}
        with patch("clipforge.core.probe", return_value=info):
            row = self.store.ingest(sidecar)
            self.assertIsNone(self.store.ingest(sidecar))
        events = self.store.activity.recent(row["id"])
        self.assertEqual([e["agent"] for e in events], ["direitos", "ingestao"])
        self.assertTrue(all(e["state"] == "complete" for e in events))
        self.assertEqual(
            [e["id"] for e in ActivityLog(self.store.database,self.store.lock).recent(row["id"])],
            [e["id"] for e in events]
        )

    def test_render_and_manual_review_record_exact_transitions(self):
        cid="123456789abc"
        self.store.activity.append(cid, "ingestao", "complete", "Local import")
        for stage in ["queued","rendering","ready","approved"]:
            self.store.update(cid, status=stage)  # no row -> must not fabricate actions
        self.assertEqual(len(self.store.activity.recent(cid)), 1)
        self.assertEqual(self.store.activity.recent(cid)[0]["message"], "Local import")

    def test_invalid_telemetry_actor_rejected(self):
        with self.assertRaises(ValueError):
            self.store.activity.append(None,"pretend-agent","running","Fake work")
        with self.assertRaises(ValueError):
            self.store.activity.append("../../bad","edicao","running","Unsafe id")

    def test_event_messages_are_bounded(self):
        cid="aabbccddeeff"
        self.store.activity.append(cid,"motion","complete","text "*1000)
        self.assertLessEqual(len(self.store.activity.recent(cid)[0]["message"]), 220)


class MissionAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env=patch.dict(os.environ,{
            "DASHBOARD_TOKEN":"private-test-token","AUTO_SCAN":"0","AUTO_RENDER":"0",
            "AUTO_TRANSCRIBE":"0","TWITCH_ENABLED":"0",
            "TWITCH_CLIENT_ID":"","TWITCH_CLIENT_SECRET":""
        })
        env.start()
        self.addCleanup(env.stop)
        self.runtime=Runtime(Path(self.temp.name))
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

    def request(self,path,token=True):
        con=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=4)
        headers={"Authorization":"Bearer private-test-token"} if token else {}
        con.request("GET",path,headers=headers)
        res=con.getresponse()
        code=res.status
        data=res.read()
        con.close()
        return code,data

    def test_snapshot_protected_and_has_no_fake_live_agents(self):
        self.assertEqual(self.request("/api/agents",False)[0],401)
        code,raw=self.request("/api/agents")
        self.assertEqual(code,200)
        result=json.loads(raw)
        self.assertEqual(result["mode"],"real_activity_only")
        self.assertEqual(result["activity"],[])
        self.assertEqual(len(result["stages"]),9)
        self.assertEqual(result["counts"]["total"],0)
        self.assertFalse(result["publishing_connected"])
        publish=next(s for s in result["stages"] if s["id"]=="publicacao")
        self.assertEqual(publish["state"],"blocked")
        self.assertEqual(result["counts"]["in_progress"],0)

    def test_bad_clip_id_rejected_and_no_sql_injection(self):
        self.assertEqual(self.request("/api/agents?clip_id=../../fake")[0],400)
        self.assertEqual(self.request("/api/agents?clip_id=abcdefghijkl")[0],404)
        self.assertEqual(self.request("/api/agents?clip_id=aaaa&clip_id=bbbb")[0],400)

    def test_real_db_clip_shows_real_render_status_in_agent_graph(self):
        cid="efefefefef12"
        with self.runtime.store._db() as db:
            db.execute(
                """INSERT INTO clips
                (id,sha256,filename,creator,source_url,evidence,rights_status,
                 input_path,output_path,start_sec,duration_sec,score,status,error,created_at)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (cid,"f"*64,"owned.mp4","Test creator","","DO_NOT_SHARE_PRIVATE_PROOF",
                 "owned","/private/test/source.mp4",None,0,12,None,
                 "detected",None,"2026-11-13T00:00:00Z")
            )
            db.commit()
        self.runtime.store.update(cid,status="queued")
        self.runtime.store.update(cid,status="rendering")
        code,data=self.request("/api/agents?clip_id="+cid)
        self.assertEqual(code,200)
        snapshot=json.loads(data)
        stage=next(s for s in snapshot["stages"] if s["id"]=="edicao")
        self.assertEqual(stage["state"],"running")
        self.assertEqual(snapshot["counts"]["in_progress"],1)
        self.assertTrue(any(e["agent"]=="edicao" for e in snapshot["activity"]))
        self.assertNotIn("DO_NOT_SHARE_PRIVATE_PROOF",data.decode())
        self.assertNotIn("/private/test",data.decode())
        self.runtime.store.update(cid,status="failed")
        code,data=self.request("/api/agents?clip_id="+cid)
        snapshot=json.loads(data)
        stage=next(s for s in snapshot["stages"] if s["id"]=="edicao")
        self.assertEqual(stage["state"],"failed")

    def test_ui_assets_exist_and_are_served(self):
        for path in ["/","/agents.js","/agents.css"]:
            code,body=self.request(path,False)
            self.assertEqual(code,200,path)
            self.assertTrue(len(body)>100)
        index=self.request("/",False)[1].decode()
        for required in ["id=\"agent-nodes\"","id=\"mission-feed\"",
                         "id=\"mission-focus\"","src=\"/agents.js\""]:
            self.assertIn(required,index)


if __name__=="__main__":
    unittest.main()

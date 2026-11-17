"""HTTP integration: real mobile pairing, scoped cookie, stream and feedback."""
import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from clipforge.core import Runtime
from clipforge.web import ThreadingHTTPServer, make_handler


class PrivateMobileHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {
            "DASHBOARD_TOKEN": "owner-private-token-" + "x"*32,
            "AUTO_SCAN": "0", "AUTO_RENDER": "0",
            "TWITCH_ENABLED": "0", "PUBLISHING_ENABLED": "0"
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.runtime = Runtime(Path(self.tmp.name))
        output = self.runtime.store.output / "review1.mp4"
        output.write_bytes(b"range-readable-mock-video")
        with self.runtime.store.lock, self.runtime.store._db() as db:
            db.execute("""INSERT INTO clips
                (id,sha256,filename,creator,source_url,evidence,rights_status,
                 input_path,output_path,start_sec,duration_sec,score,status,error,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                "review1", "d"*64, "clip.mp4", "Owner", "", "", "owned",
                "/none/source.mp4", str(output), 0, 35, 99, "ready", None, "2026-11-17"
            ))
            db.commit()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.runtime))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.runtime.editorial.pool.shutdown(wait=False)
        self.runtime.executor.shutdown(wait=False)
        self.runtime.captions.stop()

    def req(self, method, path, data=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        h=dict(headers or {})
        if data is not None:
            h["Content-Type"]="application/json"
            body=json.dumps(data)
        else: body=None
        conn.request(method,path,body=body,headers=h)
        response=conn.getresponse()
        status=response.status
        cookie=response.getheader("Set-Cookie")
        raw=response.read()
        conn.close()
        try: obj=json.loads(raw)
        except (ValueError,UnicodeDecodeError): obj=raw
        return status,obj,cookie

    def test_unpaired_phone_cannot_view_data(self):
        self.assertEqual(self.req("GET","/review")[0],200)
        self.assertEqual(self.req("GET","/api/clips")[0],401)
        self.assertEqual(self.req("POST","/api/mobile/pair")[0],401)
        self.assertEqual(self.req("POST","/api/mobile/connect",{"code":"0000000000"})[0],403)

    def test_private_pairing_allows_only_review_and_preview(self):
        owner={"Authorization":"Bearer "+os.environ["DASHBOARD_TOKEN"]}
        status,pair,_=self.req("POST","/api/mobile/pair",headers=owner)
        self.assertEqual(status,200)
        self.assertEqual(pair["port"],self.server.server_port)
        mobile_host="nexus-private.example.ts.net"
        base={"Origin":"https://"+mobile_host,"Host":mobile_host}
        status,payload,cookie=self.req("POST","/api/mobile/connect",
                                       {"code":pair["code"]},headers=base)
        self.assertEqual(status,200)
        self.assertTrue(payload["connected"])
        self.assertIn("Secure",cookie)
        self.assertIn("HttpOnly",cookie)
        self.assertIn("SameSite=Strict",cookie)
        auth={"Cookie":cookie.split(";",1)[0],"Host":mobile_host}
        status,clips,_=self.req("GET","/api/clips",headers=auth)
        self.assertEqual(status,200)
        self.assertEqual(len(clips["clips"]),1)
        self.assertNotIn("input_path",clips["clips"][0])
        self.assertEqual(self.req("GET","/api/clips/review1/video",headers=auth)[0],200)
        self.assertEqual(self.req("GET","/api/clips/review1/original",headers=auth)[0],401)
        self.assertEqual(self.req("GET","/api/publishing",headers=auth)[0],401)
        self.assertEqual(self.req("POST","/api/metrics/refresh",headers=auth)[0],401)
        # A mobile cookie without matching HTTPS origin cannot submit a review.
        self.assertEqual(self.req("POST","/api/clips/review1/review",
                     {"decision":"reject","reason":"sem_graca"},headers=auth)[0],401)
        status,review,_=self.req("POST","/api/clips/review1/review",
                {"decision":"reject","reason":"sem_graca","note":"Teste"},
                headers={**auth,"Origin":"https://"+mobile_host})
        self.assertEqual(status,200)
        self.assertEqual(review["status"],"rejected")
        self.assertEqual(self.runtime.editorial.get("review1")["feedback"]["reason"],"sem_graca")

    def test_wrong_origin_does_not_issue_cookie(self):
        owner={"Authorization":"Bearer "+os.environ["DASHBOARD_TOKEN"]}
        _,pair,_=self.req("POST","/api/mobile/pair",headers=owner)
        status,_,cookie=self.req("POST","/api/mobile/connect",
                              {"code":pair["code"]},
                              headers={"Host":"private.example.ts.net",
                                       "Origin":"https://malicious.example.net"})
        self.assertEqual(status,403)
        self.assertIsNone(cookie)


if __name__ == "__main__":
    unittest.main()

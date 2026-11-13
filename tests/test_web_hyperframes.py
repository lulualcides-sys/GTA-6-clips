"""API integration tests: protected HyperFrames export and download."""
import http.client
import json
import os
import tempfile
import threading
import unittest
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from clipforge.core import Runtime
from clipforge.web import make_handler


class HyperFramesAPI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.environment = patch.dict(os.environ, {
            "DASHBOARD_TOKEN": "temporary-protected-key",
            "AUTO_SCAN": "0", "AUTO_RENDER": "0",
            "TWITCH_ENABLED": "0", "TWITCH_CLIENT_ID": "",
            "TWITCH_CLIENT_SECRET": ""
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.runtime = Runtime(Path(self.temp.name))
        self.clip_id = "abc123def456"
        self.media = self.runtime.store.output / (self.clip_id + ".mp4")
        self.media.write_bytes(b"local-mock-video")
        with self.runtime.store._db() as db:
            db.execute(
                """INSERT INTO clips
                   (id,sha256,filename,creator,source_url,evidence,rights_status,
                    input_path,output_path,start_sec,duration_sec,score,status,error,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self.clip_id, "b"*64, "owned.mp4", "Local Creator",
                 "", "", "owned", "/local/file.mp4", str(self.media),
                 0, 11.0, None, "ready", None, "2026-11-13T00:00:00Z")
            )
            db.commit()
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.runtime))
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=5)
        self.runtime.executor.shutdown(wait=True)

    def request(self, method, endpoint, token="temporary-protected-key"):
        connection = http.client.HTTPConnection("127.0.0.1", self.http.server_port, timeout=10)
        headers = {"Authorization": "Bearer " + token} if token else {}
        connection.request(method, endpoint, headers=headers)
        response = connection.getresponse()
        data = response.read()
        code = response.status
        connection.close()
        return code, data

    def test_export_requires_token(self):
        code, _ = self.request("POST", "/api/clips/" + self.clip_id + "/hyperframes", token="")
        self.assertEqual(code, 401)
        code, _ = self.request("GET", "/api/clips/" + self.clip_id + "/hyperframes.zip", token="")
        self.assertEqual(code, 401)

    def test_export_package_is_safe_and_clip_stays_ready(self):
        info = {
            "format": {"duration": "11"},
            "streams": [{"codec_type": "video", "width": 1080, "height": 1920}]
        }
        with patch("clipforge.hyperframes.probe", return_value=info):
            code, raw = self.request("POST", "/api/clips/" + self.clip_id + "/hyperframes")
        self.assertEqual(code, 201)
        response = json.loads(raw)
        self.assertFalse(response["rendered"])
        self.assertEqual(response["engine"], "HyperFrames")
        status, data = self.request("GET", response["download_path"])
        self.assertEqual(status, 200)
        self.assertGreater(len(data), len(self.media.read_bytes()))
        file = (self.runtime.store.root / "hyperframes" /
                self.clip_id / "hyperframes-project.zip")
        with zipfile.ZipFile(file) as archive:
            self.assertEqual(set(archive.namelist()),
                             {"source.mp4", "index.html", "style.css", "manifest.json"})
            self.assertIn(b"Local Creator", archive.read("index.html"))
        self.assertEqual(self.runtime.store.get(self.clip_id)["status"], "ready")

    def test_no_download_before_export(self):
        code, _ = self.request("GET", "/api/clips/" + self.clip_id + "/hyperframes.zip")
        self.assertEqual(code, 404)

    def test_failed_clip_cannot_be_exported(self):
        self.runtime.store.update(self.clip_id, status="failed")
        code, raw = self.request("POST", "/api/clips/" + self.clip_id + "/hyperframes")
        self.assertEqual(code, 409)
        self.assertIn("ready", json.loads(raw)["error"])


if __name__ == "__main__":
    unittest.main()

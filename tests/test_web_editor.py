"""Contratos HTTP reais de revisão; bytes sintéticos apenas para transporte."""
import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from clipforge.core import Runtime
from clipforge.web import make_handler, start_publishing, stop_publishing


class EditorAPI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"DASHBOARD_TOKEN": "editor-test", "AUTO_SCAN": "0", "AUTO_RENDER": "0", "TWITCH_ENABLED": "0"})
        env.start()
        self.addCleanup(env.stop)
        self.runtime = Runtime(Path(self.temp.name))
        self.source = self.runtime.store.incoming / "owned.mp4"
        self.source.write_bytes(b"0123456789")
        for i, state in enumerate(("ready", "failed")):
            with self.runtime.store._db() as db:
                db.execute("INSERT INTO clips (id,sha256,filename,creator,rights_status,input_path,output_path,duration_sec,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)", (f"clip{i:08d}", str(i)*64, "owned.mp4", "Autor", "owned", str(self.source), str(self.source), 10, state, "2026-11-14"))
                db.commit()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.runtime))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.runtime.executor.shutdown(wait=True)

    def request(self, method, path, data=None, headers=None, token=True):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        h = {"Authorization": "Bearer editor-test"} if token else {}
        if data is not None:
            data = json.dumps(data)
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        conn.request(method, path, body=data, headers=h)
        r = conn.getresponse()
        result = r.status, dict(r.getheaders()), r.read()
        conn.close()
        return result

    def test_original_is_protected_and_range_seekable(self):
        self.assertEqual(self.request("GET", "/api/clips/clip00000000/original", token=False)[0], 401)
        code, headers, data = self.request("GET", "/api/clips/clip00000000/original", headers={"Range": "bytes=2-5"})
        self.assertEqual(code, 206)
        self.assertEqual(data, b"2345")
        self.assertEqual(headers["Content-Range"], "bytes 2-5/10")
        self.assertEqual(self.request("GET", "/api/clips/clip00000000/original", headers={"Range": "bytes=99-"})[0], 416)

    def test_original_cannot_escape_incoming(self):
        with self.runtime.store._db() as db:
            db.execute("UPDATE clips SET input_path=? WHERE id='clip00000000'", (str(Path(self.temp.name)/"private.mp4"),))
            db.commit()
        self.assertEqual(self.request("GET", "/api/clips/clip00000000/original")[0], 403)

    def test_batch_only_approves_explicit_ready_ids(self):
        code, _, data = self.request("POST", "/api/clips/approve-batch", {"clip_ids": ["clip00000000", "clip00000001"]})
        self.assertEqual(code, 200)
        result = json.loads(data)
        self.assertEqual(result["approved"], ["clip00000000"])
        self.assertEqual(result["skipped"], ["clip00000001"])
        self.assertEqual(self.runtime.store.get("clip00000001")["status"], "failed")

    def test_batch_rejects_invalid_or_oversized_input(self):
        for data in ({"clip_ids": []}, {"clip_ids": ["clip00000000"]*101}, {"clip_ids": ["../bad"]}, {"clip_ids": "clip00000000"}):
            self.assertEqual(self.request("POST", "/api/clips/approve-batch", data)[0], 400)

    def test_approval_rechecks_state_after_concurrent_edit(self):
        original_get = self.runtime.store.get
        changed = False
        def get_then_edit(clip_id):
            nonlocal changed
            item = original_get(clip_id)
            if not changed:
                changed = True
                self.runtime.store.update(clip_id, status="detected", output_path=None)
            return item
        with patch.object(self.runtime.store, "get", side_effect=get_then_edit):
            self.assertEqual(self.request("POST", "/api/clips/clip00000000/approve")[0], 409)
        self.assertEqual(original_get("clip00000000")["status"], "detected")

    def test_enabled_publication_worker_has_explicit_lifecycle(self):
        with patch.dict(os.environ, {"PUBLISHING_ENABLED": "1"}):
            service = start_publishing(self.runtime)
            self.assertTrue(service._thread.is_alive())
            self.assertIs(start_publishing(self.runtime), service)
            stop_publishing(self.runtime)
            service._thread.join(2)
            self.assertFalse(service._thread.is_alive())

    def test_existing_mutations_still_reject_bodies(self):
        self.assertEqual(self.request("POST", "/api/scan", {"unexpected": True})[0], 400)

    def test_publication_status_does_not_expose_credentials(self):
        code, _, raw = self.request("GET", "/api/publishing")
        self.assertEqual(code, 200)
        body = json.loads(raw)
        self.assertIn("jobs", body)
        self.assertNotIn("access_token", raw.decode())


if __name__ == "__main__":
    unittest.main()

"""Contrato local dos novos conectores; não executa rede ou publica."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from clipforge.autoclip_bridge import AutoClipBridge
from clipforge import postiz_connector as postiz


class PostizContractTests(unittest.TestCase):
    def test_disabled_by_default(self):
        with patch.dict(os.environ, {"POSTIZ_ENABLED": "0",
                                      "POSTIZ_API_KEY": "dummy",
                                      "POSTIZ_YOUTUBE_INTEGRATION_ID": "youtube123"}, clear=True):
            self.assertFalse(postiz.postiz_connectors()["postiz_youtube"].connected)

    def test_submit_private_youtube_and_integrated_id(self):
        connector = postiz.PostizConnector("youtube", "secret", "channel-a", True)
        with patch.object(postiz, "upload_mp4", return_value={"id": "media-a", "path": "https://uploads.postiz.com/v.mp4"}), \
             patch.object(postiz, "api_json", return_value=[{"postId": "post123", "integration": "channel-a"}]) as api:
            self.assertEqual("post123", connector.submit({"title": "Título real", "description": "crédito"}, Path("/tmp/video.mp4")))
            args, kwargs = api.call_args
            sent = kwargs["payload"]
            self.assertEqual("now", sent["type"])
            self.assertEqual("private", sent["posts"][0]["settings"]["type"])
            self.assertEqual("channel-a", sent["posts"][0]["integration"]["id"])
            self.assertEqual("media-a", sent["posts"][0]["value"][0]["image"][0]["id"])

    def test_tiktok_protected_and_no_premature_confirmation(self):
        connector = postiz.PostizConnector("tiktok", "key", "chan", True)
        self.assertEqual("SELF_ONLY", connector._settings("x")["privacy_level"])
        with patch.object(postiz, "api_json", return_value={"posts": [
             {"id": "job", "integration": {"id": "chan"}, "state": "QUEUE"}]}):
            self.assertEqual({"state": "pending"}, connector.check("job"))
        with patch.object(postiz, "api_json", return_value={"posts": [
             {"id": "job", "integration": {"id": "chan"}, "state": "PUBLISHED"}]}):
            self.assertEqual({"state": "pending"}, connector.check("job"))
        with patch.object(postiz, "api_json", return_value={"posts": [
             {"id": "job", "integration": {"id": "chan"}, "state": "PUBLISHED",
              "releaseURL": "https://www.tiktok.com/video/example"}]}):
            self.assertEqual("confirmed", connector.check("job")["state"])
        with patch.object(postiz, "api_json", return_value={"posts": [
             {"id": "job", "integration": {"id": "chan"}, "state": "ERROR"}]}):
            self.assertEqual({"state": "failed"}, connector.check("job"))

    def test_upload_validations_prevent_unsafe_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            media = root / "video.mp4"
            media.write_bytes(b"x" * 128)
            output = {"id": "a", "path": "https://uploads.postiz.com/file.mp4"}
            class Response:
                status = 200
                def read(self, limit): return json.dumps(output).encode()
            class Conn:
                def __init__(self): self.body = bytearray()
                def putrequest(self, method, path):
                    self.method, self.path = method, path
                def putheader(self, name, value): pass
                def endheaders(self): pass
                def send(self, chunk): self.body.extend(chunk)
                def getresponse(self): return Response()
                def close(self): pass
            connection = Conn()
            with patch.object(postiz.http.client, "HTTPSConnection", return_value=connection):
                answer = postiz.upload_mp4("api-key", media)
            self.assertEqual("a", answer["id"])
            self.assertIn(b"video/mp4", connection.body)
            self.assertEqual("/public/v1/upload", connection.path)
            self.assertEqual("POST", connection.method)
            link = root / "shortcut.mp4"
            link.symlink_to(media)
            with self.assertRaises(ValueError):
                postiz.upload_mp4("api-key", link)
            with self.assertRaises(ValueError):
                postiz.upload_mp4("api-key", root / "other.txt")


class AutoClipBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        incoming = root / "incoming"
        incoming.mkdir()
        self.media = incoming / "clip.mp4"
        self.media.write_bytes(b"authorized fake source")
        self.item = {"input_path": str(self.media), "sha256": hashlib.sha256(self.media.read_bytes()).hexdigest(),
                     "creator": "Criador autorizado", "source_url": "https://www.twitch.tv/creator/clip/valid",
                     "rights_status": "permission_granted", "evidence": "creator signed license"}
        self.store = SimpleNamespace(root=root, incoming=incoming,
                                     get=lambda clip_id: self.item if clip_id == "valid" else None)
        self.bridge = AutoClipBridge(self.store)

    def test_disabled_and_rights(self):
        with patch.dict(os.environ, {"AUTOCLIP_ENABLED": "0"}, clear=True):
            with self.assertRaisesRegex(ValueError, "desativado"):
                self.bridge.queue("valid")
        self.item["evidence"] = ""
        with self.assertRaises(PermissionError):
            self.bridge._source("valid")
        self.item["evidence"] = "creator signed license"
        self.media.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "mudou"):
            self.bridge._source("valid")

    def test_queue_generates_preview_without_mutating_original(self):
        original = self.media.read_bytes()
        def fake_run(command, **kwargs):
            self.assertEqual(["clip", str(self.media), "--max-clips", "3"], command[1:5])
            directory = self.bridge.exports / "job-123"
            directory.mkdir(parents=True)
            (directory / "result.mp4").write_bytes(b"fake preview")
            return SimpleNamespace(returncode=0)
        class SyncThread:
            def __init__(self, target, args, **kwargs):
                self.target, self.args = target, args
            def start(self): self.target(*self.args)
        with patch.dict(os.environ, {"AUTOCLIP_ENABLED": "1", "AUTOCLIP_AUTO_IMPORT": "0"}), \
             patch.object(self.bridge, "_command", return_value=["/bin/autoclip"]), \
             patch("clipforge.autoclip_bridge.subprocess.run", side_effect=fake_run), \
             patch("clipforge.autoclip_bridge.threading.Thread", SyncThread):
            self.assertEqual("queued", self.bridge.queue("valid")["status"])
        self.assertEqual(original, self.media.read_bytes())
        self.assertEqual("complete", self.bridge.status()["jobs"]["valid"]["status"])
        self.assertEqual(b"fake preview", self.bridge.preview("valid", 0).read_bytes())
        with self.assertRaises(ValueError):
            self.bridge.preview("valid", 55)


    def test_explicit_import_creates_new_review_manifest(self):
        import threading
        self.store.lock = threading.RLock()
        self.store.all = lambda: []
        self.store.ingest = lambda sidecar: {
            "id": "review123", "status": "detected", "filename": sidecar.name.removesuffix(".rights.json")
        }
        candidate = self.bridge.exports / "job" / "candidate.mp4"
        candidate.parent.mkdir(parents=True)
        candidate.write_bytes(b"synthetic candidate")
        self.bridge.jobs["valid"] = {
            "status": "complete", "suggestions": ["job/candidate.mp4"]
        }
        with patch("clipforge.core.probe", return_value={}), \
             patch("clipforge.core.duration_of", return_value=32.0):
            result = self.bridge.import_suggestion("valid", 0)
        self.assertEqual("review123", result["clip_id"])
        self.assertTrue(result["created"])
        self.assertEqual(self.media.read_bytes(), b"authorized fake source")
        sidecars = list(self.store.incoming.glob("autoclip-*.rights.json"))
        self.assertEqual(1, len(sidecars))
        manifest = json.loads(sidecars[0].read_text(encoding="utf-8"))
        self.assertEqual("permission_granted", manifest["rights_status"])
        self.assertEqual("valid", manifest["derived_from"])
        self.assertEqual(32.0, manifest["duration_sec"])
        self.assertTrue(manifest["review_required"])


if __name__ == "__main__":
    unittest.main()

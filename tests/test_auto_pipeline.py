"""Contract tests for fully automatic, strictly authorized AutoClip workflow."""
import io
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

from clipforge.twitch_auto import TwitchAutoIngest
from clipforge.twitch_oauth import ensure_owned_channel, save_private_config
from clipforge.autoclip_bridge import AutoClipBridge
from clipforge.core import ClipStore


class AutoIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = SimpleNamespace(root=self.root, incoming=self.root / "incoming")
        self.store.incoming.mkdir()
        self.sample = {"id": "GoodClip42", "broadcaster_id": "111", "score": 98}
        self.other = {"id": "OtherClip42", "broadcaster_id": "222", "score": 99}
        self.twitch = SimpleNamespace(
            client_id="twitch-client-id",
            secret="test-secret",
            list_candidates=lambda: [self.other, self.sample]
        )
        self.bridge = SimpleNamespace(available=lambda: True)
        self.runtime = SimpleNamespace(store=self.store, twitch=self.twitch,
                                       autoclip_bridge=self.bridge,
                                       scan=Mock(return_value={"added": ["imported"], "errors": []}))
        self.intake = TwitchAutoIngest(self.runtime)
        (self.root / "twitch_sources.json").write_text(json.dumps({
            "broadcasters": [{
                "id": "111", "creator": "Meu canal", "rights_status": "owned",
                "evidence": "Autorizado pelo titular"
            }]
        }))
        self.env = patch.dict(os.environ, {
            "TWITCH_AUTO_DOWNLOAD": "1", "TWITCH_USER_ACCESS_TOKEN": "private-token",
            "TWITCH_EDITOR_ID": "111", "TWITCH_AUTO_BATCH": "2"
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_status_requires_separate_user_grant(self):
        with patch.dict(os.environ, {"TWITCH_USER_ACCESS_TOKEN": ""}):
            self.assertFalse(self.intake.status()["ready"])
            self.assertFalse(self.intake.kick())
            self.assertIn("Client ID/Secret", self.intake.last_error)

    def test_eligible_clip_downloaded_only_via_official_client_and_queued(self):
        with patch("clipforge.twitch_oauth.refreshed_token", return_value="token") as refresh, \
             patch("clipforge.twitch_auto.download_clip",
                   return_value=self.store.incoming / "twitch-GoodClip42.mp4") as download:
            self.intake._work()
        refresh.assert_called_once()
        download.assert_called_once()
        args = download.call_args.args
        self.assertEqual(args[:5], ("GoodClip42", "111", "111", "twitch-client-id", "token"))
        self.assertEqual(args[5]["rights_status"], "owned")
        self.runtime.scan.assert_called_once()
        self.assertEqual(self.intake.processed, 1)

    def test_unlisted_broadcaster_never_downloaded(self):
        self.twitch.list_candidates = lambda: [self.other]
        with patch("clipforge.twitch_oauth.refreshed_token", return_value="token"), \
             patch("clipforge.twitch_auto.download_clip") as download:
            self.intake._work()
        download.assert_not_called()
        self.runtime.scan.assert_not_called()

    def test_grant_does_not_claim_unrelated_channel(self):
        ensure_owned_channel(self.root, "123456789")
        data = json.loads((self.root/"data"/"twitch_sources.json").read_text())
        self.assertEqual(data["broadcasters"][0]["id"], "123456789")
        self.assertEqual(data["broadcasters"][0]["rights_status"], "owned")


class AutoClipAutoReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ClipStore(Path(self.temp.name))
        self.bridge = AutoClipBridge(self.store)

    def test_bounded_queue_starts_only_one_worker(self):
        with patch.object(self.bridge, "available", return_value=True), \
             patch.object(self.bridge, "_source", return_value=Path("x.mp4")), \
             patch("clipforge.autoclip_bridge.threading.Thread") as worker:
            self.bridge.queue("a")
            self.bridge.queue("b")
            worker.assert_called_once()
            self.assertEqual(self.bridge.status()["pending"], 2)
            self.assertEqual(self.bridge.active, "a")
            self.assertEqual(self.bridge.jobs["b"]["status"], "queued")

    def test_autoclip_output_auto_imported_without_approval(self):
        src = Path(self.temp.name) / "incoming" / "source.mp4"
        src.write_bytes(b"fake-test-source")
        export = self.bridge.exports / "job-1" / "clip.mp4"
        def finished(*args, **kwargs):
            export.parent.mkdir(parents=True, exist_ok=True)
            export.write_bytes(b"fake-test-export")
            return SimpleNamespace(returncode=0)
        self.bridge.jobs["a"] = {"status": "queued", "suggestions": [], "imports": []}
        self.bridge.active = "a"
        item = {"input_path": str(src), "sha256": "",
                "rights_status": "owned", "creator": "Owner"}
        with patch.object(self.bridge, "_source", return_value=src), \
             patch.object(self.bridge, "_command", return_value=["autoclip"]), \
             patch.object(self.bridge, "_prepare_local_ai", return_value=[]), \
             patch("clipforge.autoclip_bridge.subprocess.run", side_effect=finished), \
             patch.object(self.bridge, "import_suggestion",
                          return_value={"clip_id": "review123", "status": "ready"}) as imp:
            self.bridge._run("a")
        imp.assert_called_once_with("a", 0)
        self.assertEqual(self.bridge.jobs["a"]["status"], "complete")
        self.assertEqual(self.bridge.jobs["a"]["imports"], ["review123"])
        self.assertFalse(any(j.get("status") == "approved" for j in self.bridge.jobs.values()))


if __name__ == "__main__":
    unittest.main()

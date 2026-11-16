"""Política de edição: AutoClip exclusivo, FFmpeg permitido somente como QA."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from clipforge.autoclip_bridge import AutoClipBridge
from clipforge.core import ClipStore, Runtime, render_clip


class ExclusiveEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ClipStore(Path(self.temp.name))
        self.source = self.store.incoming / "source.mp4"
        self.source.write_bytes(b"source owned by test")
        self.sidecar = self.store.incoming / "source.mp4.rights.json"
        self.sidecar.write_text(json.dumps({
            "creator": "Synthetic creator", "rights_status": "owned",
            "start_sec": 0, "duration_sec": 20
        }))
        self.source_info = {
            "format": {"duration": "40"},
            "streams": [
                {"codec_type": "video", "width": 640, "height": 360, "r_frame_rate": "30/1"},
                {"codec_type": "audio"}
            ]
        }
        self.export_info = {
            "format": {"duration": "20"},
            "streams": [
                {"codec_type": "video", "width": 1080, "height": 1920, "r_frame_rate": "30/1"},
                {"codec_type": "audio"}
            ]
        }
        self.probe = lambda path: self.source_info if Path(path).name == "source.mp4" else self.export_info
        with patch("clipforge.core.probe", side_effect=self.probe):
            self.clip = self.store.ingest(self.sidecar)

    def test_direct_legacy_renderer_blocked_by_default(self):
        self.store.update(self.clip["id"], status="queued")
        with patch.dict(os.environ, {"NEXUS_LEGACY_TEST_RENDER": "0"}):
            with self.assertRaisesRegex(RuntimeError, "somente AutoClip"):
                render_clip(self.store, self.clip["id"])
        self.assertFalse(list(self.store.output.glob("*.mp4")))

    def test_runtime_no_fallback_without_autoclip(self):
        with patch.dict(os.environ, {"AUTO_SCAN": "0", "AUTO_RENDER": "0",
                                     "TWITCH_ENABLED": "0", "AUTOCLIP_ENABLED": "0"}):
            runtime = Runtime(self.store.root)
            self.addCleanup(runtime.executor.shutdown, wait=True)
            with self.assertRaisesRegex(ValueError, "desativado"):
                runtime.queue(self.clip["id"])
            item = self.store.get(self.clip["id"])
            self.assertEqual("detected", item["status"])
            self.assertIsNone(item["output_path"])

    def test_production_queue_calls_real_bridge_not_ffmpeg(self):
        with patch.dict(os.environ, {"AUTO_SCAN": "0", "AUTO_RENDER": "0",
                                     "TWITCH_ENABLED": "0"}):
            runtime = Runtime(self.store.root)
            self.addCleanup(runtime.executor.shutdown, wait=True)
            with patch.object(runtime.autoclip_bridge, "queue", return_value={"status": "queued"}) as bridge, \\
                 patch("clipforge.core.render_clip") as legacy:
                self.assertTrue(runtime.queue(self.clip["id"]))
                bridge.assert_called_once_with(self.clip["id"])
                legacy.assert_not_called()
            self.assertEqual(self.store.get(self.clip["id"])["status"], "detected")

    def test_import_promotes_verified_autoclip_bytes_without_rerender(self):
        bridge = AutoClipBridge(self.store)
        candidate = bridge.exports / "job" / "final.mp4"
        candidate.parent.mkdir(parents=True)
        payload = b"exported ONLY by mocked AutoClip CLI"
        candidate.write_bytes(payload)
        bridge.jobs[self.clip["id"]] = {
            "status": "complete", "suggestions": ["job/final.mp4"]
        }
        with patch("clipforge.core.probe", side_effect=self.probe), \\
             patch("clipforge.autoclip_bridge.subprocess.run", return_value=SimpleNamespace(returncode=0)) as decode:
            result = bridge.import_suggestion(self.clip["id"], 0)
        self.assertTrue(result["created"])
        self.assertEqual(result["status"], "ready")
        item = self.store.get(result["clip_id"])
        self.assertEqual(Path(item["output_path"]).read_bytes(), payload)
        self.assertEqual(self.source.read_bytes(), b"source owned by test")
        self.assertEqual(hashlib.sha256(payload).hexdigest(), item["sha256"])
        self.assertEqual(self.store.get_edit(result["clip_id"])["qa"]["engine"], "autoclip")
        command = decode.call_args.args[0]
        self.assertEqual(command[0], "ffmpeg")
        self.assertEqual(command[-3:], ["-f", "null", "-"])

    def test_rejects_non_vertical_export_without_reencoding(self):
        bridge = AutoClipBridge(self.store)
        candidate = bridge.exports / "job" / "landscape.mp4"
        candidate.parent.mkdir(parents=True)
        candidate.write_bytes(b"invalid landscape result")
        bridge.jobs[self.clip["id"]] = {
            "status": "complete", "suggestions": ["job/landscape.mp4"]
        }
        with patch("clipforge.core.probe", return_value=self.source_info):
            with self.assertRaisesRegex(ValueError, "9:16"):
                bridge.import_suggestion(self.clip["id"], 0)
        self.assertFalse(list(self.store.output.glob("*.mp4")))


if __name__ == "__main__":
    unittest.main()

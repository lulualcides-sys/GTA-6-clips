import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

from clipforge.core import ClipStore
from clipforge.captions import CaptionService, cues_from_segments, to_srt, timestamp


class CaptionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ClipStore(Path(self.temp.name))
        self.cid = "abc123def456"
        self.video = self.store.output / f"{self.cid}.mp4"
        self.video.write_bytes(b"synthetic video with sound (mocked inference)")
        with self.store._db() as db:
            db.execute("""INSERT INTO clips
                (id,sha256,filename,creator,source_url,evidence,rights_status,
                input_path,output_path,start_sec,duration_sec,score,status,error,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self.cid,"a"*64,"owned.mp4","My test channel","","","owned",
                 str(self.store.incoming / "owned.mp4"),str(self.video),0,12,None,
                 "ready",None,"2026-11-13T00:00:00Z"))
            db.commit()
        self.service = CaptionService(self.store)
        self.addCleanup(self.service.stop)

    def fake_model(self, text="Bom dia, GTA!", start=0.2, end=2.7):
        words = [NS(start=start,end=start+0.5,word="Bom"),
                 NS(start=start+0.6,end=start+1,word="dia,"),
                 NS(start=start+1.1,end=end,word="GTA!")]
        return NS(transcribe=lambda *a,**kw: (
            [NS(start=start,end=end,text=text,words=words)], NS(language="pt")
        ))

    def test_srt_uses_real_word_timings(self):
        segments, _ = self.fake_model().transcribe()
        cues = cues_from_segments(segments,max_words=2)
        self.assertEqual(len(cues),2)
        self.assertEqual(cues[0][2],"Bom dia,")
        text = to_srt(cues)
        self.assertIn("00:00:00,200 --> 00:00:01,200",text)
        self.assertIn("GTA!",text)

    def test_clock_timestamp_rollover(self):
        self.assertEqual(timestamp(3661.005),"01:01:01,005")

    def test_opt_in_worker_writes_only_private_srt(self):
        digest = hashlib.sha256(self.video.read_bytes()).hexdigest()
        with patch("clipforge.captions.whisper_model",return_value=self.fake_model()):
            self.service._run(self.cid,digest,"base")
        state = self.service.status(self.cid)
        self.assertEqual(state["status"],"ready")
        self.assertEqual(state["language"],"pt")
        self.assertEqual(state["cues"],1)
        file = self.service.captions_file(self.cid)
        self.assertTrue(file.is_file())
        self.assertIn("Bom dia, GTA!",file.read_text())
        self.assertEqual(self.store.get(self.cid)["status"],"ready")

    def test_transcribe_never_invents_speech_when_no_segments(self):
        digest = hashlib.sha256(self.video.read_bytes()).hexdigest()
        model = NS(transcribe=lambda *args, **kwargs: ([], NS(language="pt")))
        with patch("clipforge.captions.whisper_model",return_value=model):
            self.service._run(self.cid,digest,"base")
        self.assertEqual(self.service.status(self.cid)["cues"],0)
        self.assertIsNone(self.service.captions_file(self.cid))

    def test_stale_srt_not_used_after_video_changes(self):
        digest = hashlib.sha256(self.video.read_bytes()).hexdigest()
        with patch("clipforge.captions.whisper_model",return_value=self.fake_model()):
            self.service._run(self.cid,digest,"base")
        self.video.write_bytes(b"another video content")
        self.assertEqual(self.service.status(self.cid)["status"],"stale")
        self.assertIsNone(self.service.captions_file(self.cid))

    def test_cannot_transcribe_unready_clip(self):
        self.store.update(self.cid,status="detected")
        with self.assertRaisesRegex(ValueError,"not ready"):
            self.service.queue(self.cid)

    def test_reject_model_outside_allowlist(self):
        with patch.dict(os.environ,{"WHISPER_MODEL":"../../secret"}):
            with self.assertRaisesRegex(ValueError,"Unsupported WHISPER_MODEL"):
                self.service.queue(self.cid)

    def test_missing_optional_package_fails_gracefully(self):
        digest = hashlib.sha256(self.video.read_bytes()).hexdigest()
        with patch("clipforge.captions.whisper_model",
                   side_effect=RuntimeError("faster-whisper not installed")):
            self.service._run(self.cid,digest,"base")
        self.assertEqual(self.service.status(self.cid)["status"],"failed")
        self.assertIn("faster-whisper",self.service.status(self.cid)["error"])

    def test_queued_jobs_are_single_flight(self):
        with patch.object(self.service.executor,"submit") as submit:
            self.assertTrue(self.service.queue(self.cid))
            self.assertFalse(self.service.queue(self.cid))
            submit.assert_called_once()

    def test_old_text_does_not_escape_srt(self):
        cues = [(0,1,"<script>alert(1)</script>\nmore words")]
        srt=to_srt(cues)
        self.assertNotIn("\nmore words",srt)
        self.assertIn("<script>",srt)  # plain text SRT; later HTML export escapes it


if __name__ == "__main__":
    unittest.main()

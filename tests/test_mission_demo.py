import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clipforge.core import Runtime


class SyntheticDemoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env=patch.dict(os.environ,{
            "ENABLE_SYNTHETIC_DEMO":"1",
            "AUTO_SCAN":"0", "AUTO_RENDER":"0",
            "TWITCH_ENABLED":"0", "TWITCH_CLIENT_ID":"",
            "TWITCH_CLIENT_SECRET":""
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.runtime=Runtime(Path(self.temp.name))
        self.addCleanup(self.runtime.executor.shutdown, wait=True)
        self.addCleanup(self.runtime.captions.stop)

    def test_opt_in_demo_default_is_disabled(self):
        self.runtime.demo.enabled=False
        with self.assertRaisesRegex(PermissionError,"disabled"):
            self.runtime.demo.start()

    def test_synthetic_pipeline_ingests_only_own_generated_media(self):
        def write_test_media(cmd, **kwargs):
            Path(cmd[-1]).write_bytes(b"synthetic-owned-video")
            return None
        with patch("clipforge.demo.subprocess.run",side_effect=write_test_media),\
             patch("clipforge.core.probe",return_value={
                 "format":{"duration":"12"},
                 "streams":[{"codec_type":"video","width":640,"height":360}]
             }),\
             patch.object(self.runtime,"queue",return_value=True) as queued:
            self.runtime.demo._generate(1)
        clips=self.runtime.store.all()
        self.assertEqual(len(clips),1)
        self.assertEqual(clips[0]["rights_status"],"owned")
        self.assertEqual(clips[0]["creator"],"GTA CLIPS — AMOSTRA SINTÉTICA")
        queued.assert_called_once_with(clips[0]["id"])
        rights=self.runtime.store.incoming/"mission-demo-1.mp4.rights.json"
        self.assertEqual(json.loads(rights.read_text())["rights_status"],"owned")
        self.assertFalse(self.runtime.demo.running)
        messages=[x["message"] for x in self.runtime.store.activity.recent()]
        self.assertTrue(any("Amostra própria" in x for x in messages))

    def test_demo_limit_is_bounded_to_three_clips(self):
        with self.runtime.store._db() as db:
            for index in range(1,4):
                db.execute("""INSERT INTO clips
                    (id,sha256,filename,creator,source_url,evidence,
                    rights_status,input_path,output_path,start_sec,duration_sec,
                    score,status,error,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (f"{index:012d}",str(index)*64,f"mission-demo-{index}.mp4",
                     "Synthetic","",None,"owned","/test",None,0,10,None,
                     "detected",None,"2026-11-13T00:00:00Z"))
            db.commit()
        with self.assertRaisesRegex(ValueError,"limit"):
            self.runtime.demo.start()

    def test_concurrent_demo_generation_is_rejected(self):
        self.runtime.demo.running=True
        with self.assertRaisesRegex(ValueError,"already"):
            self.runtime.demo.start()


if __name__ == "__main__":
    unittest.main()

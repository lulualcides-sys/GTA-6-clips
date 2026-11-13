import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clipforge.core import ClipStore, choose_highlight


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ClipStore(Path(self.temp.name))
        self.video = self.store.incoming / "source.mp4"
        self.video.write_bytes(b"synthetic-content")
        self.sidecar = self.store.incoming / "source.mp4.rights.json"
        self.meta = {"creator":"My Test Channel","rights_status":"owned","start_sec":5,"duration_sec":30}
        self.info = {"format":{"duration":"80"},"streams":[{"codec_type":"video"}]}

    def write_meta(self):
        self.sidecar.write_text(json.dumps(self.meta),encoding="utf-8")

    def test_rejects_permission_without_evidence(self):
        self.meta["rights_status"] = "permission_granted"
        self.write_meta()
        with patch("clipforge.core.probe",return_value=self.info):
            with self.assertRaisesRegex(ValueError,"Permission requires"):
                self.store.ingest(self.sidecar)

    def test_rejects_unlicensed_source(self):
        self.meta["rights_status"] = "unknown"
        self.write_meta()
        with patch("clipforge.core.probe",return_value=self.info):
            with self.assertRaisesRegex(ValueError,"Explicit rights"):
                self.store.ingest(self.sidecar)

    def test_ingest_deduplicates_sha256(self):
        self.write_meta()
        with patch("clipforge.core.probe",return_value=self.info):
            first = self.store.ingest(self.sidecar)
            second = self.store.ingest(self.sidecar)
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(len(self.store.all()),1)
        self.assertEqual(self.store.get(first["id"])["status"],"detected")

    def test_out_of_bounds_timestamp(self):
        self.meta.update(start_sec=65,duration_sec=30)
        self.write_meta()
        with patch("clipforge.core.probe",return_value=self.info):
            with self.assertRaisesRegex(ValueError,"Timestamp"):
                self.store.ingest(self.sidecar)

    def test_scan_returns_errors(self):
        self.sidecar.write_text("{bad",encoding="utf-8")
        result = self.store.scan()
        self.assertEqual(result["added"],[])
        self.assertEqual(len(result["errors"]),1)

    def test_heuristic_fallback(self):
        with patch("clipforge.core.subprocess.run",side_effect=OSError("missing ffmpeg")):
            self.assertEqual(choose_highlight(self.video,50,30),0)


if __name__ == "__main__":
    unittest.main()

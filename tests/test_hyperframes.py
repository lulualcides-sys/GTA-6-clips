import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clipforge.core import ClipStore
from clipforge.hyperframes import (
    MAX_SRT_BYTES, composition_html, export_composition, parse_srt, render_composition
)


class HyperFramesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = ClipStore(self.root)
        self.clip_id = "abcdef123456"
        self.media = self.store.output / (self.clip_id + ".mp4")
        self.media.write_bytes(b"synthetic-test-video")  # ffprobe is mocked
        with self.store._db() as db:
            db.execute(
                """INSERT INTO clips
                   (id,sha256,filename,creator,source_url,evidence,rights_status,
                    input_path,output_path,start_sec,duration_sec,score,status,error,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    self.clip_id, "a" * 64, "owned.mp4", "Streamer <Private>",
                    "https://clips.twitch.tv/example", "private-not-for-export",
                    "owned", str(self.root / "incoming/owned.mp4"),
                    str(self.media), 0, 12.0, None, "ready", None, "2026-11-13T00:00:00Z"
                ),
            )
            db.commit()
        self.info = {
            "format": {"duration": "12.00"},
            "streams": [{"codec_type": "video", "width": 1080, "height": 1920}]
        }

    def test_srt_parser_with_real_timestamps(self):
        srt = (
            "1\n00:00:00,200 --> 00:00:02,000\nPrimeiro lance\n\n"
            "2\n00:00:03,000 --> 00:00:14,000\nGanhamos!\n"
        )
        cues = parse_srt(srt, 12)
        self.assertEqual(len(cues), 2)
        self.assertAlmostEqual(cues[0][0], .2)
        self.assertEqual(cues[1][1], 9)

    def test_valid_export_is_self_contained_and_escapes_untrusted_text(self):
        with patch("clipforge.hyperframes.probe", return_value=self.info):
            directory = export_composition(self.store, self.clip_id,
                                           title='<script>alert("x")</script>')
        markup = (directory / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-composition-id="gta6-clips"', markup)
        self.assertIn('data-no-timeline="true"', markup)
        self.assertIn('data-duration="12.000"', markup)
        self.assertIn("&lt;script&gt;alert", markup)
        self.assertNotIn('<script>alert', markup)
        self.assertIn("Streamer &lt;Private&gt;", markup)
        self.assertTrue((directory / "source.mp4").is_file())
        self.assertTrue((directory / "style.css").is_file())
        metadata = json.loads((directory / "manifest.json").read_text())
        self.assertEqual(metadata["rights_status"], "owned")
        self.assertNotIn("evidence", metadata)
        self.assertFalse(metadata["rendered"])

    def test_export_srt_captions_and_cruel_html(self):
        srt = self.root / "captions.srt"
        srt.write_text(
            "1\n00:00:01,000 --> 00:00:03,000\n<script>not allowed</script>\n",
            encoding="utf-8",
        )
        with patch("clipforge.hyperframes.probe", return_value=self.info):
            directory = export_composition(self.store, self.clip_id, captions_file=srt)
        markup = (directory / "index.html").read_text()
        self.assertIn("caption-0", markup)
        self.assertIn("&lt;script&gt;", markup)
        self.assertNotIn("<script>not allowed", markup)
        meta = json.loads((directory / "manifest.json").read_text())
        self.assertEqual(meta["captions_count"], 1)

    def test_unready_clip_not_exportable(self):
        self.store.update(self.clip_id, status="failed")
        with self.assertRaisesRegex(ValueError, "ready"):
            export_composition(self.store, self.clip_id)

    def test_invalid_id_not_exportable(self):
        with self.assertRaisesRegex(ValueError, "clip ID"):
            export_composition(self.store, "../../secrets")

    def test_symlink_source_rejected(self):
        self.media.unlink()
        self.media.symlink_to(self.root / "outside.mp4")
        with self.assertRaisesRegex(ValueError, "missing"):
            export_composition(self.store, self.clip_id)

    def test_caption_outside_timeline_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            composition_html(4, "Creator", "GTA6", [(3, 4, "Nope")])

    def test_large_subtitle_rejected(self):
        with self.assertRaisesRegex(ValueError, "exceeds"):
            parse_srt("a" * (MAX_SRT_BYTES + 1), 20)

    def test_offline_render_refuses_missing_files(self):
        folder = self.root / "empty"
        folder.mkdir()
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            render_composition(folder)

    def test_export_metadata_does_not_change_approved_clip(self):
        self.store.update(self.clip_id, status="approved")
        with patch("clipforge.hyperframes.probe", return_value=self.info):
            export_composition(self.store, self.clip_id)
        self.assertEqual(self.store.get(self.clip_id)["status"], "approved")
        self.assertEqual(self.store.get(self.clip_id)["output_path"], str(self.media))


if __name__ == "__main__":
    unittest.main()
